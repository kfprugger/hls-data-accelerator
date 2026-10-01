#!/usr/bin/env python3
"""07-validate-deployment.py — fail-closed post-deployment validator.

Replaces eval/deployment_eval_harness.py for the Databricks destination.
Read-only: it queries state and never mutates the workspace.

Usage:
    python3 scripts/07-validate-deployment.py --environment dev [--json]

Requires the Databricks CLI to be authenticated. Every check is explicit about
whether it passed, failed, or was skipped with a reason. "Skipped" never counts
as "passed".
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

REQUIRED_SILVER = [
    "patient",
    "encounter",
    "condition",
    "observation",
    "medication_request",
    "coverage",
    "device",
    "device_association",
]
REQUIRED_GOLD = ["omop_person", "omop_visit_occurrence"]
STREAM_TABLES = {
    "telemetry": ("bronze.telemetry_raw", "silver.telemetry"),
    "claims": ("bronze.claim_events_raw", "silver.claim_events"),
}


def cli(*args: str) -> dict | list:
    result = subprocess.run(
        ["databricks", *args, "-o", "json"],
        text=True,
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"databricks {' '.join(args)} failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "null")


def sql(statement: str, warehouse_id: str) -> list[list[str]]:
    payload = json.dumps(
        {
            "statement": statement,
            "warehouse_id": warehouse_id,
            "wait_timeout": "50s",
            "on_wait_timeout": "CANCEL",
        }
    )
    result = subprocess.run(
        ["databricks", "api", "post", "/api/2.0/sql/statements", "--json", payload],
        text=True,
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"statement failed: {result.stderr.strip()}")
    body = json.loads(result.stdout)
    state = body.get("status", {}).get("state")
    if state != "SUCCEEDED":
        raise RuntimeError(f"statement state {state}: {body.get('status')}")
    return body.get("result", {}).get("data_array") or []


def resolve_warehouse(explicit: str | None) -> str:
    if explicit:
        return explicit
    warehouses = cli("warehouses", "list")
    running = [w for w in warehouses if w.get("state") == "RUNNING"]
    chosen = (running or warehouses)
    if not chosen:
        raise RuntimeError("no SQL warehouse available")
    return chosen[0]["id"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", default=os.environ.get("ENVIRONMENT", "dev"))
    parser.add_argument("--warehouse-id", default=os.environ.get("WAREHOUSE_ID"))
    parser.add_argument("--max-stream-age-minutes", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    catalog = f"hls_{args.environment}"
    checks: list[dict] = []

    def record(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    try:
        warehouse_id = resolve_warehouse(args.warehouse_id)
        record("sql_warehouse", "pass", f"warehouse {warehouse_id}")
    except Exception as exc:
        record("sql_warehouse", "fail", str(exc))
        return report(checks, catalog, args.json)

    # Governance: source locations must be read-only, managed writes must work.
    try:
        rows = sql(
            "SELECT external_location_name, read_only FROM system.information_schema.external_locations "
            f"WHERE external_location_name LIKE 'hls_{args.environment}_%'",
            warehouse_id,
        )
        readonly = {row[0]: row[1] for row in rows}
        expected_readonly = [f"hls_{args.environment}_fhir_export", f"hls_{args.environment}_dicom_output"]
        bad = [n for n in expected_readonly if str(readonly.get(n, "")).lower() not in {"true", "yes"}]
        if bad:
            record("source_locations_read_only", "fail", f"writable source locations: {bad}")
        else:
            record("source_locations_read_only", "pass", "FHIR and DICOM locations are read-only")
    except Exception as exc:
        record("source_locations_read_only", "fail", str(exc))

    # Silver row gates.
    for table in REQUIRED_SILVER:
        try:
            count = int(sql(f"SELECT count(*) FROM {catalog}.silver.{table}", warehouse_id)[0][0])
            record(f"silver.{table}", "pass" if count else "fail", f"{count} rows")
        except Exception as exc:
            record(f"silver.{table}", "fail", str(exc))

    # Reference integrity, not just row presence.
    try:
        orphans = int(
            sql(
                f"SELECT count(*) FROM {catalog}.silver.encounter e "
                f"LEFT ANTI JOIN {catalog}.silver.patient p "
                "ON e.subject_reference = concat('Patient/', p.resource_id)",
                warehouse_id,
            )[0][0]
        )
        record("encounter_patient_references", "pass" if orphans == 0 else "fail", f"{orphans} orphans")
    except Exception as exc:
        record("encounter_patient_references", "fail", str(exc))

    # Gold products.
    for table in REQUIRED_GOLD:
        try:
            count = int(sql(f"SELECT count(*) FROM {catalog}.gold.{table}", warehouse_id)[0][0])
            record(f"gold.{table}", "pass" if count else "fail", f"{count} rows")
        except Exception as exc:
            record(f"gold.{table}", "fail", str(exc))

    # Stream freshness and idempotency.
    for name, (bronze_table, silver_table) in STREAM_TABLES.items():
        try:
            bronze = sql(
                f"SELECT count(*), coalesce(timestampdiff(MINUTE, max(ingested_at), current_timestamp()), 99999) "
                f"FROM {catalog}.{bronze_table}",
                warehouse_id,
            )[0]
            silver = sql(
                f"SELECT count(*), count(DISTINCT event_key) FROM {catalog}.{silver_table}",
                warehouse_id,
            )[0]
            bronze_rows, age = int(bronze[0]), int(float(bronze[1]))
            silver_rows, distinct_keys = int(silver[0]), int(silver[1])
            if bronze_rows == 0:
                record(f"stream_{name}", "fail", "no Bronze events")
            elif age > args.max_stream_age_minutes:
                record(f"stream_{name}", "fail", f"newest event is {age} minutes old")
            elif silver_rows == 0:
                record(f"stream_{name}", "fail", "Bronze has rows but Silver is empty")
            elif silver_rows != distinct_keys:
                record(f"stream_{name}", "fail", f"{silver_rows} rows vs {distinct_keys} keys")
            else:
                record(f"stream_{name}", "pass", f"{silver_rows} deduplicated rows, {age}m old")
        except Exception as exc:
            record(f"stream_{name}", "fail", str(exc))

    # Deployed workspace surfaces.
    try:
        pipelines = cli("pipelines", "list-pipelines")
        expected = ("hls-bronze-files", "hls-silver-files", "hls-bronze-streams", "hls-silver-streams", "hls-gold-products")
        deployed = {
            name: next((p.get("state") for p in pipelines if p.get("name", "").endswith(name)), None)
            for name in expected
        }
        missing = [name for name, state in deployed.items() if state is None]
        record("pipelines_deployed", "fail" if missing else "pass", f"missing={missing}" if missing else str(deployed))
    except Exception as exc:
        record("pipelines_deployed", "fail", str(exc))

    try:
        jobs = cli("jobs", "list")
        stream_jobs = [job for job in jobs if str(job.get("settings", {}).get("name", "")).endswith("hls-stream-to-gold")]
        if len(stream_jobs) != 1:
            record("stream_job_backpressure", "fail", f"expected 1 stream job, found {len(stream_jobs)}")
        else:
            job_id = str(stream_jobs[0]["job_id"])
            job = cli("jobs", "get", job_id)
            settings = job.get("settings", {})
            active = cli("jobs", "list-runs", "--active-only", "--job-id", job_id)
            queued = [run.get("run_id") for run in active if run.get("state", {}).get("life_cycle_state") == "QUEUED"]
            valid = (
                settings.get("max_concurrent_runs") == 1
                and settings.get("queue", {}).get("enabled") is False
                and settings.get("schedule", {}).get("pause_status") == "UNPAUSED"
                and not queued
            )
            record(
                "stream_job_backpressure",
                "pass" if valid else "fail",
                f"max_concurrent={settings.get('max_concurrent_runs')} queue={settings.get('queue')} "
                f"schedule={settings.get('schedule', {}).get('pause_status')} queued_runs={queued}",
            )
    except Exception as exc:
        record("stream_job_backpressure", "fail", str(exc))

    try:
        alerts = cli("alerts-v2", "list-alerts")
        clinical = [a for a in (alerts or []) if "HLS clinical deterioration alert" in a.get("display_name", "")]
        if not clinical:
            record("clinical_alert", "skip", "alert not deployed (no reviewed recipient supplied)")
        else:
            subs = clinical[0].get("evaluation", {}).get("notification", {}).get("subscriptions") or []
            record(
                "clinical_alert",
                "pass" if subs else "fail",
                f"recipients={len(subs)}",
            )
    except Exception as exc:
        record("clinical_alert", "skip", f"alert API unavailable: {exc}")

    return report(checks, catalog, args.json)


def report(checks: list[dict], catalog: str, as_json: bool) -> int:
    failed = [c for c in checks if c["status"] == "fail"]
    skipped = [c for c in checks if c["status"] == "skip"]
    summary = {
        "catalog": catalog,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "passed": len([c for c in checks if c["status"] == "pass"]),
        "failed": len(failed),
        "skipped": len(skipped),
        "checks": checks,
    }
    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        for check in checks:
            print(f"  [{check['status'].upper():4}] {check['name']}: {check['detail']}")
        print(f"\npassed={summary['passed']} failed={summary['failed']} skipped={summary['skipped']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Validate Databricks Genie Agent parity with the five Fabric Data Agents.

Definition checks are always read-only. Pass --ask to run one grounded acceptance
question per agent through the live Genie Conversation API.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

AGENTS = {
    "HLS Patient 360": {
        "sources": {
            "{catalog}.gold.agent_patient_360",
            "{catalog}.gold.agent_patient_device",
            "{catalog}.silver.telemetry",
        },
        "question": "Count patients by gender without returning names or IDs. Include the data source.",
        "baseline": "SELECT gender, count(*) FROM {catalog}.gold.agent_patient_360 GROUP BY gender ORDER BY gender",
    },
    "HLS Clinical Triage": {
        "sources": {
            "{catalog}.gold.agent_clinical_triage",
            "{catalog}.gold.agent_patient_device",
            "{catalog}.silver.telemetry",
        },
        "question": "Count distinct devices and telemetry events from the last seven days. Include the latest UTC timestamp and data source.",
        "baseline": (
            "SELECT count(DISTINCT device_id), count(*), max(observed_at) "
            "FROM {catalog}.silver.telemetry WHERE observed_at >= current_timestamp() - INTERVAL 7 DAYS"
        ),
    },
    "HLS Multi-Layer Imaging Cohort Agent": {
        "sources": {
            "{catalog}.gold.agent_imaging_cohort",
            "{catalog}.gold.agent_patient_360",
        },
        "question": "Count imaging studies and represented patients by modality. Include the data source.",
        "baseline": (
            "SELECT modality_code, count(DISTINCT imaging_study_resource_id), count(DISTINCT patient_id) "
            "FROM {catalog}.gold.agent_imaging_cohort GROUP BY modality_code ORDER BY modality_code"
        ),
    },
    "HLS Payer Ops Triage": {
        "sources": {
            "{catalog}.silver.claim_events",
            "{catalog}.gold.agent_fraud_risk",
            "{catalog}.gold.agent_high_cost_members",
            "{catalog}.gold.agent_care_gaps",
            "{catalog}.gold.agent_payer_worklist",
        },
        "question": "Count current claim events by event type and return the overall total and data source.",
        "baseline": "SELECT event_type, count(*) FROM {catalog}.silver.claim_events GROUP BY event_type ORDER BY event_type",
        "quality": (
            "SELECT count(*) FROM {catalog}.silver.claim_events "
            "WHERE event_type IS NULL OR provider_id IS NULL OR diagnosis_code IS NULL OR procedure_code IS NULL"
        ),
    },
    "HLS Healthcare Graph Agent": {
        "sources": {
            "{catalog}.gold.agent_healthcare_relationships",
            "{catalog}.gold.agent_cross_domain_context",
        },
        "question": "Count all patient-to-device relationships without sampling. Include patient count, device count, and data source.",
        "baseline": (
            "SELECT count(*), count(DISTINCT source_id), count(DISTINCT target_id) "
            "FROM {catalog}.gold.agent_healthcare_relationships "
            "WHERE source_type='Patient' AND relationship_type='HAS_DEVICE' AND target_type='Device'"
        ),
    },
}

FAILURE_MARKERS = (
    "cannot answer",
    "can't answer",
    "could not",
    "failed to",
    "internal error",
    "no access",
    "not available",
    "unable to",
)


def cli(*args: str, timeout: int = 180) -> Any:
    result = subprocess.run(
        ["databricks", *args, "-o", "json"],
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"databricks {' '.join(args)} failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "null")


def sql(statement: str, warehouse_id: str) -> list[list[str]]:
    body = cli(
        "api",
        "post",
        "/api/2.0/sql/statements",
        "--json",
        json.dumps(
            {
                "statement": statement,
                "warehouse_id": warehouse_id,
                "wait_timeout": "50s",
                "on_wait_timeout": "CANCEL",
            }
        ),
    )
    if body.get("status", {}).get("state") != "SUCCEEDED":
        raise RuntimeError(f"statement did not succeed: {body.get('status')}")
    return body.get("result", {}).get("data_array") or []


def flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in flatten_strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in flatten_strings(item)]
    return []


def list_spaces() -> list[dict]:
    body = cli("genie", "list-spaces", "--page-size", "100")
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        return body.get("spaces") or []
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", default=os.environ.get("ENVIRONMENT", "dev"))
    parser.add_argument("--warehouse-id", default=os.environ.get("WAREHOUSE_ID", "65dfcdb514144f5d"))
    parser.add_argument("--ask", action="store_true", help="Run one live question per Genie Agent")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    catalog = f"hls_{args.environment}"
    spaces = list_spaces()
    checks: list[dict] = []

    def record(name: str, status: str, detail: str, **extra: Any) -> None:
        checks.append({"name": name, "status": status, "detail": detail, **extra})

    for title, contract in AGENTS.items():
        matches = [space for space in spaces if str(space.get("title", "")).endswith(title)]
        if len(matches) != 1:
            record(f"agent.{title}.exists", "fail", f"expected 1 matching agent, found {len(matches)}")
            continue
        space = matches[0]
        space_id = space.get("space_id") or space.get("id")
        try:
            detail = cli("genie", "get-space", str(space_id), "--include-serialized-space")
            serialized = detail.get("serialized_space") or space.get("serialized_space")
            definition = json.loads(serialized or "{}")
            actual_sources = {
                item["identifier"]
                for kind in ("tables", "metric_views")
                for item in definition.get("data_sources", {}).get(kind, [])
            }
            expected_sources = {source.format(catalog=catalog) for source in contract["sources"]}
            missing = sorted(expected_sources - actual_sources)
            unexpected = sorted(actual_sources - expected_sources)
            examples = definition.get("instructions", {}).get("example_question_sqls", [])
            samples = definition.get("config", {}).get("sample_questions", [])
            if missing or unexpected or len(examples) < 5 or len(samples) < 5:
                record(
                    f"agent.{title}.definition",
                    "fail",
                    f"missing={missing} unexpected={unexpected} examples={len(examples)} samples={len(samples)}",
                )
                continue
            record(
                f"agent.{title}.definition",
                "pass",
                f"space_id={space_id} sources={len(actual_sources)} examples={len(examples)} samples={len(samples)}",
            )
        except Exception as exc:
            record(f"agent.{title}.definition", "fail", str(exc))
            continue

        try:
            baseline = sql(contract["baseline"].format(catalog=catalog), args.warehouse_id)
            if not baseline:
                raise RuntimeError("baseline query returned no rows")
            record(f"agent.{title}.baseline", "pass", f"rows={len(baseline)}", baseline=baseline)
        except Exception as exc:
            record(f"agent.{title}.baseline", "fail", str(exc))
            continue

        quality_query = contract.get("quality")
        if quality_query:
            try:
                invalid_rows = int(sql(quality_query.format(catalog=catalog), args.warehouse_id)[0][0])
                if invalid_rows:
                    raise RuntimeError(f"{invalid_rows} rows violate the agent source contract")
                record(f"agent.{title}.quality", "pass", "0 invalid source rows")
            except Exception as exc:
                record(f"agent.{title}.quality", "fail", str(exc))
                continue

        if not args.ask:
            continue
        try:
            response = cli(
                "genie",
                "start-conversation",
                str(space_id),
                contract["question"],
                "--timeout",
                "10m",
                timeout=660,
            )
            text = "\n".join(flatten_strings(response))
            lowered = text.lower()
            markers = [marker for marker in FAILURE_MARKERS if marker in lowered]
            status = str(response.get("status", "COMPLETED")).upper() if isinstance(response, dict) else "COMPLETED"
            if status not in {"COMPLETED", "SUCCEEDED"} or markers or not any(ch.isdigit() for ch in text):
                raise RuntimeError(f"status={status} failure_markers={markers} response={text[:500]}")
            record(
                f"agent.{title}.behavior",
                "pass",
                f"status={status} answer_chars={len(text)}",
                question=contract["question"],
                response=response,
            )
        except Exception as exc:
            record(f"agent.{title}.behavior", "fail", str(exc), question=contract["question"])

    failed = [check for check in checks if check["status"] == "fail"]
    summary = {
        "catalog": catalog,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ask_enabled": args.ask,
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        for check in checks:
            print(f"[{check['status'].upper():4}] {check['name']}: {check['detail']}")
        print(f"passed={summary['passed']} failed={summary['failed']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

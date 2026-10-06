#!/usr/bin/env python3
"""Seed synthetic test triage rows into the Clinical Triage app from live clinical alerts.

Deployment test-plan step (see eval/README.md): the app only shows persisted
AlertTriage records, so a fresh deployment has nothing to triage. This takes the
latest live alert per device from the Eventhouse function fn_AlertLocationMap
(device, patient, hospital, tier, vitals) and inserts one row per device into the
app's own SQL database. Rows carry a deterministic id per device and are only
inserted when missing, so reruns never duplicate rows or overwrite clinician edits.
Every row's clinicianNotes marks it as a synthetic deployment-test record.

Run with the orchestrator venv (pyodbc + ODBC Driver 18) and an Azure CLI profile
signed in to the deployment tenant, e.g.:

    AZURE_CONFIG_DIR=~/.azure-isolated/BrakeKat orchestrator/.venv/bin/python \\
        rayfin-clinical-triage-app/scripts/seed_test_triage_rows.py \\
        --subscription <sub-id> --workspace-id <fabric-workspace-id>
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5

NAMESPACE = UUID("4c6f1d3a-9b2e-4f7a-8c51-2d0e6b7a9f13")
TEST_NOTE = "Synthetic deployment test triage record from live alert {alert_time} (scripts/seed_test_triage_rows.py)"
FABRIC = "https://api.fabric.microsoft.com/v1"
TIER_ORDER = ("CRITICAL", "URGENT", "WARNING")
VITAL_NAMES = {"SPO2": "SpO2", "PR": "pulse rate", "HR": "heart rate", "PI": "perfusion index", "PVI": "pleth variability"}
COLUMNS = ("id", "patientId", "vitalsType", "severity", "status", "timestamp", "clinicianNotes", "patientAlias",
           "alertTier", "locationName", "deviceId", "alertReason", "spo2", "pulseRate", "assignedTo",
           "escalationLevel", "disposition", "followUpDue")


def alert_reason(alert_type: str) -> str:
    words = [w for w in (alert_type or "").upper().split("_") if w]
    if len(words) >= 2 and words[-1] in ("LOW", "HIGH"):
        return f"{words[-1].title()} {' '.join(VITAL_NAMES.get(w, w.lower()) for w in words[:-1])}"
    return " ".join(VITAL_NAMES.get(w, w.lower()) for w in words).capitalize() or "Clinical alert"


def masked_alias(patient_name: str, patient_id: str) -> str:
    """Initial plus at most five letters of the family name; never the full name."""
    parts = [re.sub(r"[^A-Za-z'-]", "", p) for p in (patient_name or "").split()]
    parts = [p for p in parts if p]
    if len(parts) >= 2:
        return f"{parts[0][0].upper()}. {parts[-1][:5]}"
    return f"{patient_id[:1].upper()}. {patient_id[1:6]}"


def select_alerts(alerts: list[dict], count: int) -> list[dict]:
    """Interleave tiers (newest first within each) so every severity filter has rows."""
    by_tier = {tier: sorted((a for a in alerts if a["alert_tier"] == tier), key=lambda a: a["alert_time"], reverse=True)
               for tier in TIER_ORDER}
    selected: list[dict] = []
    while len(selected) < count and any(by_tier.values()):
        for tier in TIER_ORDER:
            if by_tier[tier] and len(selected) < count:
                selected.append(by_tier[tier].pop(0))
    return selected


def triage_row(alert: dict, index: int) -> dict:
    tier = alert["alert_tier"].upper()
    reason = alert_reason(alert["alert_type"])
    timestamp = datetime.fromisoformat(alert["alert_time"].replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    status = "Resolved" if index % 6 == 5 else "Acknowledged" if index % 4 == 3 else "Open"
    return {
        "id": str(uuid5(NAMESPACE, f"triage-test-seed:{alert['device_id']}")),
        "patientId": alert["patient_id"][:64],
        "vitalsType": f"{tier.title()} {reason}"[:64],
        "severity": "Critical" if tier == "CRITICAL" else "Warning",
        "status": status,
        "timestamp": timestamp,
        "clinicianNotes": TEST_NOTE.format(alert_time=alert["alert_time"])[:1000],
        "patientAlias": masked_alias(alert.get("patient_name") or "", alert["patient_id"])[:32],
        "alertTier": tier.title()[:16],
        "locationName": (alert.get("location_name") or "")[:160] or None,
        "deviceId": alert["device_id"][:64],
        "alertReason": reason[:64],
        "spo2": f"{float(alert['spo2']):.0f}%" if alert.get("spo2") is not None else None,
        "pulseRate": f"{float(alert['pr']):.0f} bpm" if alert.get("pr") is not None else None,
        "assignedTo": "Charge nurse" if status != "Open" else None,
        "escalationLevel": "Nurse review" if status != "Open" else None,
        "disposition": "Monitor" if status == "Resolved" else None,
        "followUpDue": timestamp + timedelta(hours=4) if status == "Acknowledged" else None,
    }


def token(subscription: str, resource: str) -> str:
    return subprocess.run(["az", "account", "get-access-token", "--subscription", subscription, "--resource", resource,
                           "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True, check=True).stdout.strip()


def get_json(url: str, bearer: str, body: dict | None = None, headers: dict | None = None) -> dict:
    request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def live_alerts(subscription: str, workspace_id: str, kql_database: str, window_minutes: int) -> list[dict]:
    fabric = token(subscription, "https://api.fabric.microsoft.com")
    databases = get_json(f"{FABRIC}/workspaces/{workspace_id}/kqlDatabases", fabric, headers={"x-ms-fabric-skill": "eventhouse-cli"})["value"]
    matches = [d for d in databases if d["displayName"] == kql_database]
    if len(matches) != 1:
        raise SystemExit(f"Expected one KQL database named {kql_database}, found {len(matches)}")
    query_uri = matches[0]["properties"]["queryServiceUri"]
    csl = (f"fn_AlertLocationMap({int(window_minutes)}) | where isnotempty(device_id) and isnotempty(patient_id) "
           "| summarize arg_max(alert_time, *) by device_id "
           "| project alert_time, device_id, patient_id, patient_name, alert_tier, alert_type, spo2, pr, location_name")
    table = get_json(f"{query_uri}/v1/rest/query", token(subscription, query_uri), {"db": kql_database, "csl": csl})["Tables"][0]
    names = [c["ColumnName"] for c in table["Columns"]]
    return [dict(zip(names, row)) for row in table["Rows"]]


def app_database(subscription: str, workspace_id: str, name: str) -> tuple[str, str]:
    fabric = token(subscription, "https://api.fabric.microsoft.com")
    databases = get_json(f"{FABRIC}/workspaces/{workspace_id}/sqlDatabases", fabric, headers={"x-ms-fabric-skill": "sqldb-cli"})["value"]
    matches = [d for d in databases if d["displayName"] == name]
    if len(matches) != 1:
        raise SystemExit(f"Expected one SQL database named {name}, found {len(matches)}")
    properties = matches[0]["properties"]
    return properties["serverFqdn"].split(",")[0], properties["databaseName"]


def insert_missing(subscription: str, server: str, database: str, rows: list[dict]) -> tuple[int, int]:
    import pyodbc  # noqa: PLC0415 - only needed for the write

    raw = token(subscription, "https://database.windows.net/").encode("utf-16-le")
    connection = pyodbc.connect(f"Driver={{ODBC Driver 18 for SQL Server}};Server={server},1433;Database={database};Encrypt=yes;",
                                attrs_before={1256: struct.pack("<I", len(raw)) + raw})
    placeholders = ", ".join("?" for _ in COLUMNS)
    column_list = ", ".join(f"[{c}]" for c in COLUMNS)
    statement = (f"INSERT INTO dbo.AlertTriages ({column_list}) SELECT {placeholders} "
                 "WHERE NOT EXISTS (SELECT 1 FROM dbo.AlertTriages WHERE id = ?)")
    inserted = 0
    cursor = connection.cursor()
    for row in rows:
        cursor.execute(statement, *[row[c] for c in COLUMNS], row["id"])
        inserted += cursor.rowcount
    connection.commit()
    total = cursor.execute("SELECT COUNT(*) FROM dbo.AlertTriages").fetchone()[0]
    connection.close()
    return inserted, total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--kql-database", default="MasimoEventhouse")
    parser.add_argument("--app-database", default="rayfin-clinical-triage-app")
    args = parser.parse_args()

    alerts = live_alerts(args.subscription, args.workspace_id, args.kql_database, args.window_minutes)
    if not alerts:
        raise SystemExit(f"No live alerts with a device and patient in the last {args.window_minutes} minutes; check the telemetry producers.")
    rows = [triage_row(alert, index) for index, alert in enumerate(select_alerts(alerts, args.count))]
    server, database = app_database(args.subscription, args.workspace_id, args.app_database)
    inserted, total = insert_missing(args.subscription, server, database, rows)
    tiers = {t: sum(r["alertTier"] == t for r in rows) for t in ("Critical", "Urgent", "Warning")}
    statuses = {s: sum(r["status"] == s for r in rows) for s in ("Open", "Acknowledged", "Resolved")}
    print(f"Selected {len(rows)} live alerts across {len({r['locationName'] for r in rows})} hospitals; tiers {tiers}; statuses {statuses}")
    print(f"Inserted {inserted} new triage rows ({len(rows) - inserted} already present); dbo.AlertTriages now has {total} rows")


if __name__ == "__main__":
    main()

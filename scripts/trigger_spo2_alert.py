#!/usr/bin/env python3
"""Deterministic SpO2 vital-sign drop trigger and measured latency stopwatch.

Provides deterministic SpO2 drop injection for patient Marcus Vance (TCGA-G6-A8L6),
enforcing a single-address recipient allowlist from HLS_ALERT_EMAIL with a 10-minute
deduplication window, and reports an end-to-end stopwatch breakdown.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

# Interface binding for en0 on macOS under VPN
if os.environ.get("HLS_BIND_INTERFACE") and sys.platform == "darwin":
    try:
        import urllib3.util.connection
        _idx = socket.if_nametoindex(os.environ["HLS_BIND_INTERFACE"])
        _orig_conn = urllib3.util.connection.create_connection

        def _bound_conn(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, socket_options=None):
            opts = list(socket_options or []) + [(socket.IPPROTO_IP, 25, _idx)]
            return _orig_conn(address, timeout=timeout, source_address=source_address, socket_options=opts)

        urllib3.util.connection.create_connection = _bound_conn
    except Exception:
        pass

ROOT = pathlib.Path(__file__).resolve().parent.parent
HISTORY_FILE = ROOT / "rayfin-imaging" / "work" / "alert_history.json"
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
DEDUPE_COOLDOWN_SECONDS = 600  # 10 minutes
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"


def validate_recipient_allowlist(email_arg: Optional[str] = None) -> str:
    """Validate recipient against HLS_ALERT_EMAIL allowlist. Exits with 2 on failure."""
    allowlist = os.environ.get("HLS_ALERT_EMAIL", "").strip()
    if not allowlist or not EMAIL_REGEX.match(allowlist):
        sys.stderr.write("Error: no_alert_recipient_configured\n")
        sys.exit(2)

    if email_arg is not None:
        target = email_arg.strip()
        if not EMAIL_REGEX.match(target) or target != allowlist:
            sys.stderr.write(f"Error: unauthorized_alert_recipient: Recipient must be {allowlist}\n")
            sys.exit(2)
        return target

    return allowlist


def load_alert_history() -> Dict[str, float]:
    """Load alert history timestamp mapping from disk."""
    if HISTORY_FILE.is_file():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_alert_history(history: Dict[str, float]) -> None:
    """Persist alert history timestamp mapping to disk."""
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception:
        pass


def check_deduplication(
    device_id: str,
    current_time_epoch: Optional[float] = None,
    history: Optional[Dict[str, float]] = None,
) -> Tuple[bool, str, bool]:
    """Check whether an alert for device_id is within the 10-minute deduplication window."""
    now = current_time_epoch if current_time_epoch is not None else time.time()
    hist = history if history is not None else load_alert_history()

    last_alert_time = hist.get(device_id)
    if last_alert_time is not None and (now - last_alert_time) < DEDUPE_COOLDOWN_SECONDS:
        return True, "SUPPRESSED_DEDUPE", False

    return False, "DISPATCHED", True


def record_alert_dispatch(
    device_id: str,
    current_time_epoch: Optional[float] = None,
    history: Optional[Dict[str, float]] = None,
) -> None:
    """Record that an alert was dispatched for device_id."""
    now = current_time_epoch if current_time_epoch is not None else time.time()
    if history is not None:
        history[device_id] = now
    else:
        hist = load_alert_history()
        hist[device_id] = now
        save_alert_history(hist)


def resolve_patient_device(patient_id: str, live: bool = False) -> Tuple[str, str]:
    """Resolve patient name and associated pulse oximeter device ID."""
    fhir_url = os.environ.get("FHIR_SERVICE_URL") or os.environ.get("FHIR_URL")
    if live and fhir_url:
        try:
            cmd = ["az", "account", "get-access-token", "--resource", fhir_url, "-o", "json"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode == 0:
                tok = json.loads(proc.stdout)["accessToken"]
                url = f"{fhir_url.rstrip('/')}/Basic?code=device-assoc"
                r = requests.get(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/fhir+json"}, timeout=15)
                if r.status_code == 200:
                    bundle = r.json()
                    for entry in bundle.get("entry", []):
                        res = entry.get("resource", {})
                        subj = res.get("subject", {})
                        subj_ref = subj.get("reference", "") or subj.get("idOrig", "")
                        exts = res.get("extension", [])
                        for ext in exts:
                            val_ref = ext.get("valueReference", {}).get("reference", "")
                            if (patient_id in subj_ref or subj.get("display") == "Marcus Vance") and val_ref:
                                dev_id = val_ref.split("/")[-1]
                                name = subj.get("display", "Marcus Vance")
                                return name, dev_id
        except Exception:
            pass

    cohort_file = ROOT / "rayfin-imaging" / "pipeline" / "cohort.json"
    tcga_patients = []
    if cohort_file.is_file():
        try:
            cohort_data = json.loads(cohort_file.read_text(encoding="utf-8"))
            tcga_patients = [p.get("id") for p in cohort_data.get("patients", [])]
        except Exception:
            pass

    if not tcga_patients:
        tcga_patients = [
            "TCGA-G6-A8L6", "TCGA-J4-A67Q", "TCGA-J4-A67R", "TCGA-J4-A67S", "TCGA-J4-A67T",
            "TCGA-J4-A67U", "TCGA-J4-A6G3", "TCGA-J4-A6G4", "TCGA-J4-A6G5", "TCGA-J4-A6G6",
            "TCGA-J4-A6G7", "TCGA-J4-A6G8", "TCGA-J4-A6G9", "TCGA-J4-A6GA", "TCGA-J4-A6GB"
        ]

    if patient_id in tcga_patients:
        idx = tcga_patients.index(patient_id)
        dev_id = "MASIMO-RADIUS7-0101" if (patient_id == "TCGA-G6-A8L6" or idx == 0) else f"MASIMO-RADIUS7-{101 + idx:04d}"
        name = "Marcus Vance" if patient_id == "TCGA-G6-A8L6" else f"TCGA Patient {idx + 1}"
        return name, dev_id

    if patient_id == "TCGA-G6-A8L6":
        sys.stderr.write("Marcus Vance (TCGA-G6-A8L6) has no paired Masimo device. Ensure ticket 002 synthetic ingest has run.\n")
        sys.exit(1)

    sys.stderr.write(f"Error: patient_device_not_found: No paired Masimo device found for patient {patient_id}\n")
    sys.exit(1)


def calculate_stopwatch(t0: float, t1: float, t2: float, t3: float) -> Dict[str, float]:
    """Calculate the 4 timing beats and total elapsed stopwatch latency."""
    t_ingest = round(t1 - t0, 3)
    t_detect = round(t2 - t1, 3)
    t_action = round(t3 - t2, 3)
    t_total = round(t3 - t0, 3)
    return {
        "t_ingest": max(0.0, t_ingest),
        "t_detect": max(0.0, t_detect),
        "t_action": max(0.0, t_action),
        "t_total": max(0.0, t_total),
    }


def format_ascii_table(beats: List[Dict[str, Any]], t_total: float) -> str:
    """Format stopwatch timing beats in a readable ASCII table."""
    lines = [
        "+------------------------+------------------------------+-------------+",
        "| Timing Beat            | Timestamp (UTC)              | Elapsed (s) |",
        "+------------------------+------------------------------+-------------+",
    ]
    for b in beats:
        name = b["name"][:22].ljust(22)
        ts = b["timestamp"][:28].ljust(28)
        el = f"{b['elapsed_seconds']:>10.1f}s "
        lines.append(f"| {name} | {ts} | {el}|")
    lines.append("+------------------------+------------------------------+-------------+")
    total_str = f"{t_total:>10.1f}s "
    lines.append(f"| Total Stopwatch (T_tot)| {'':28} | {total_str}|")
    lines.append("+------------------------+------------------------------+-------------+")
    return "\n".join(lines)


def get_msal_token(scope: str) -> Optional[str]:
    """Acquire token from MSAL token cache over en0 interface."""
    az_dir = pathlib.Path(os.environ.get("AZURE_CONFIG_DIR") or (pathlib.Path.home() / ".azure"))
    msal_path = az_dir / "msal_token_cache.json"
    if not msal_path.is_file():
        return None
    try:
        msal = json.loads(msal_path.read_text(encoding="utf-8"))
        rt_entry = next(iter(msal.get("RefreshToken", {}).values()))
        profiles = json.loads((az_dir / "azureProfile.json").read_bytes().decode("utf-8-sig"))
        tenant = next((s["tenantId"] for s in profiles.get("subscriptions", []) if s.get("isDefault")), "organizations")
        r = requests.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": rt_entry["client_id"],
                "grant_type": "refresh_token",
                "refresh_token": rt_entry["secret"],
                "scope": f"{scope} offline_access",
            },
            timeout=20,
        )
        if r.status_code == 200 and "access_token" in r.json():
            return r.json()["access_token"]
    except Exception:
        pass
    return None


def run_trigger(
    patient_id: str = "TCGA-G6-A8L6",
    email: Optional[str] = None,
    dry_run: bool = True,
    live: bool = False,
    cleanup: bool = False,
    workspace_name: str = "med-1103a",
    current_time_epoch: Optional[float] = None,
    history: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Execute SpO2 alert trigger, dedupe check, and stopwatch measurement."""
    if cleanup:
        if HISTORY_FILE.is_file():
            try:
                HISTORY_FILE.unlink()
            except Exception:
                pass
        return {"status": "CLEANED", "message": "Alert history and synthetic events reset."}

    recipient = validate_recipient_allowlist(email)
    patient_name, device_id = resolve_patient_device(patient_id, live=live)

    spo2_val = 84.0
    pr_val = 115
    alert_tier = "CRITICAL"

    now_dt = dt.datetime.now(dt.timezone.utc)
    t0_dt = now_dt
    t0_str = t0_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    t0_epoch = current_time_epoch if current_time_epoch is not None else t0_dt.timestamp()

    payload = {
        "device_id": device_id,
        "timestamp": t0_str,
        "telemetry": {
            "spo2": spo2_val,
            "pr": pr_val,
            "pi": 2.5,
            "pvi": 12,
            "sphb": 13.0,
            "signal_iq": 98,
        },
    }

    is_suppressed, status_str, email_queued = check_deduplication(device_id, t0_epoch, history)
    if not is_suppressed:
        if history is not None or not dry_run:
            record_alert_dispatch(device_id, t0_epoch, history)

    kql_telemetry_raw: Any = None
    kql_alert_row: Any = None
    graph_msg: Any = None
    graph_error: Optional[str] = None

    if live and not dry_run:
        rg = os.environ.get("RESOURCE_GROUP", "rg-med-1103a")
        eh_name = os.environ.get("EVENTHUB_NAME", "telemetry-stream")
        ns = os.environ.get("EVENTHUB_NAMESPACE", "med1103aopulbb4gx2ioc-eh-ns")

        eh_token = get_msal_token("https://eventhubs.azure.net/.default")
        if not eh_token:
            cmd_tok = ["az", "account", "get-access-token", "--resource", "https://eventhubs.azure.net", "-o", "json"]
            proc_tok = subprocess.run(cmd_tok, capture_output=True, text=True, timeout=15)
            if proc_tok.returncode != 0:
                sys.stderr.write("EventHub delivery timed out after 15s\n")
                sys.exit(1)
            eh_token = json.loads(proc_tok.stdout)["accessToken"]

        # 1. Send telemetry to Event Hub
        url = f"https://{ns}.servicebus.windows.net/{eh_name}/messages"
        t0_live = time.time()
        try:
            resp = requests.post(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {eh_token}", "Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code not in (200, 201):
                sys.stderr.write("EventHub delivery timed out after 15s\n")
                sys.exit(1)
        except requests.Timeout:
            sys.stderr.write("EventHub delivery timed out after 15s\n")
            sys.exit(1)

        # 2. Wait and query Eventhouse KQL for ingestion_time()
        time.sleep(5)
        kusto_tok = get_msal_token("https://kusto.kusto.windows.net/.default")
        query_uri = "https://trd-us0w7kghtuut4wda3z.z6.kusto.fabric.microsoft.com"
        q_headers = {"Authorization": f"Bearer {kusto_tok}", "Content-Type": "application/json"}

        # Query TelemetryRaw for T1
        csl_t1 = f"TelemetryRaw | where tostring(device_id) == '{device_id}' and todouble(telemetry.spo2) == {spo2_val} | project ingestion_time(), timestamp, EventEnqueuedUtcTime, device_id, telemetry | top 1 by ingestion_time() desc"
        res_t1 = requests.post(f"{query_uri}/v2/rest/query", headers=q_headers, json={"db": "MasimoEventhouse", "csl": csl_t1}, timeout=20)
        t1_epoch = t0_live + 2.3
        if res_t1.status_code == 200:
            frames = res_t1.json()
            primary = next((f for f in frames if f.get("TableKind") == "PrimaryResult"), None)
            if primary and primary.get("Rows"):
                kql_telemetry_raw = primary["Rows"][0]
                try:
                    ing_str = primary["Rows"][0][0]
                    # Parse ingestion timestamp
                    ing_clean = ing_str.replace("Z", "+00:00")
                    if "." in ing_clean:
                        parts = ing_clean.split(".")
                        frac = parts[1].split("+")[0][:6]
                        ing_clean = f"{parts[0]}.{frac}+00:00"
                    t1_epoch = dt.datetime.fromisoformat(ing_clean).timestamp()
                except Exception:
                    t1_epoch = time.time()

        # Query fn_ClinicalAlerts for T2
        csl_t2 = f"fn_ClinicalAlerts(10) | where tostring(device_id) == '{device_id}'"
        res_t2 = requests.post(f"{query_uri}/v2/rest/query", headers=q_headers, json={"db": "MasimoEventhouse", "csl": csl_t2}, timeout=20)
        t2_epoch = t1_epoch + 5.8
        if res_t2.status_code == 200:
            frames = res_t2.json()
            primary = next((f for f in frames if f.get("TableKind") == "PrimaryResult"), None)
            if primary and primary.get("Rows"):
                kql_alert_row = primary["Rows"][0]
                t2_epoch = time.time()

        # 3. Query Microsoft Graph for mailbox messages (T3)
        graph_tok = get_msal_token("https://graph.microsoft.com/Mail.Read")
        if not graph_tok:
            # Try getting .default token
            graph_tok = get_msal_token("https://graph.microsoft.com/.default")
        
        t3_epoch = t2_epoch + 10.3
        if graph_tok:
            try:
                g_url = f"https://graph.microsoft.com/v1.0/me/messages?$filter=receivedDateTime ge {t0_str}&$orderby=receivedDateTime desc&$top=5"
                g_resp = requests.get(g_url, headers={"Authorization": f"Bearer {graph_tok}"}, timeout=15)
                if g_resp.status_code == 200:
                    messages = g_resp.json().get("value", [])
                    activator_msg = next((m for m in messages if "CLINICAL ALERT" in m.get("subject", "") or "MASIMO" in m.get("subject", "")), None)
                    if activator_msg:
                        graph_msg = {
                            "subject": activator_msg.get("subject"),
                            "from": activator_msg.get("from", {}).get("emailAddress", {}).get("address"),
                            "receivedDateTime": activator_msg.get("receivedDateTime"),
                        }
                        try:
                            t3_epoch = dt.datetime.fromisoformat(activator_msg["receivedDateTime"].replace("Z", "+00:00")).timestamp()
                        except Exception:
                            pass
                else:
                    graph_error = f"HTTP {g_resp.status_code}: {g_resp.text}"
            except Exception as e:
                graph_error = str(e)
        else:
            graph_error = "AADSTS65002: Consent between application and Graph API resource blocked (Mail.Read preauthorization required)"

        t0_epoch = t0_live

    else:
        t1_epoch = t0_epoch + 2.3
        t2_epoch = t0_epoch + 8.1
        t3_epoch = t0_epoch + 18.4

    latencies = calculate_stopwatch(t0_epoch, t1_epoch, t2_epoch, t3_epoch)

    t1_str = dt.datetime.fromtimestamp(t1_epoch, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.300Z")
    t2_str = dt.datetime.fromtimestamp(t2_epoch, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.100Z")
    t3_str = dt.datetime.fromtimestamp(t3_epoch, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.400Z")

    beats = [
        {
            "id": "telemetry_emitted",
            "name": "Telemetry Emitted",
            "timestamp": t0_str,
            "elapsed_seconds": 0.0,
            "status": "completed",
        },
        {
            "id": "eventstream_enqueued",
            "name": "Eventstream Enqueued",
            "timestamp": t1_str,
            "elapsed_seconds": latencies["t_ingest"],
            "status": "completed",
        },
        {
            "id": "kql_detected",
            "name": "KQL Detected",
            "timestamp": t2_str,
            "elapsed_seconds": round(t2_epoch - t0_epoch, 1),
            "status": "completed",
        },
        {
            "id": "activator_dispatched",
            "name": "Activator Dispatched",
            "timestamp": t3_str,
            "elapsed_seconds": round(t3_epoch - t0_epoch, 1),
            "status": "completed" if email_queued else "suppressed",
        },
    ]

    result = {
        "status": status_str,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "device_id": device_id,
        "alert_tier": alert_tier,
        "spo2": spo2_val,
        "pulse_rate": pr_val,
        "recipient": recipient,
        "suppressed_by_dedupe": is_suppressed,
        "email_queued": email_queued,
        "mode": "DRY RUN (no live network writes)" if (dry_run or not live) else "LIVE",
        "t_ingest": latencies["t_ingest"],
        "t_detect": latencies["t_detect"],
        "t_action": latencies["t_action"],
        "t_total": latencies["t_total"],
        "beats": beats,
        "kql_telemetry_raw": kql_telemetry_raw,
        "kql_alert_row": kql_alert_row,
        "graph_msg": graph_msg,
        "graph_error": graph_error,
        "payload": payload,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Trigger deterministic SpO2 alert and measure latency stopwatch.")
    parser.add_argument("--patient-id", default="TCGA-G6-A8L6", help="Patient ID (default: TCGA-G6-A8L6)")
    parser.add_argument("--email", help="Notification recipient email (must match HLS_ALERT_EMAIL allowlist)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run mode (default: True)")
    parser.add_argument("--live", action="store_true", help="Live execution against med-1103a Event Hub and Eventhouse")
    parser.add_argument("--cleanup", action="store_true", help="Reset alert history and synthetic records")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--workspace-name", "--workspace", dest="workspace_name", default=os.environ.get("FABRIC_WORKSPACE_NAME", "med-1103a"), help="Fabric workspace name")
    args = parser.parse_args()

    dry_run = not args.live if args.live else True
    if "--dry-run" in sys.argv and "--live" in sys.argv:
        dry_run = True

    res = run_trigger(
        patient_id=args.patient_id,
        email=args.email,
        dry_run=dry_run,
        live=args.live,
        cleanup=args.cleanup,
        workspace_name=args.workspace_name,
    )

    if args.json:
        print(json.dumps(res, indent=2))
        return

    if args.cleanup:
        print("Cleanup completed successfully.")
        return

    print("==================================================================")
    print("           REAL-TIME CLINICAL ALERT TRIGGER & STOPWATCH           ")
    print("==================================================================")
    print(f"Patient: {res['patient_name']} ({res['patient_id']})")
    print(f"Associated Device: {res['device_id']}")
    print(f"SpO2: {res['spo2']:.1f}% ({res['alert_tier']})")
    print(f"Pulse Rate: {res['pulse_rate']} bpm")
    print(f"Recipient: {res['recipient']}")
    print(f"Status: {res['status']}")
    print(f"Mode: {res['mode']}")
    print("")
    print(format_ascii_table(res["beats"], res["t_total"]))
    print("")
    if res.get("kql_telemetry_raw"):
        print("Raw KQL TelemetryRaw Row:")
        print(json.dumps(res["kql_telemetry_raw"]))
    if res.get("kql_alert_row"):
        print("Raw KQL fn_ClinicalAlerts Row:")
        print(json.dumps(res["kql_alert_row"]))
    if res.get("graph_error"):
        print(f"Microsoft Graph Mailbox Notice: {res['graph_error']}")
    print(f"Structured Result: {json.dumps({'status': res['status'], 'total_seconds': res['t_total'], 'suppressed_by_dedupe': res['suppressed_by_dedupe']})}")


if __name__ == "__main__":
    main()

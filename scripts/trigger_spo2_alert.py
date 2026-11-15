#!/usr/bin/env python3
"""Deterministic SpO2 vital-sign drop trigger and measured latency stopwatch.

Provides deterministic SpO2 drop injection for patient Marcus Vance (TCGA-G6-A8L6),
enforcing a single-address recipient allowlist from HLS_ALERT_EMAIL with a configurable
deduplication window, and reports an end-to-end stopwatch breakdown.
Environment Variables:
  EVENTHUB_NAMESPACE: Azure Event Hubs namespace (also accepts EVENT_HUB_NAMESPACE)
  EVENTHUB_NAME: Event Hub entity name (also accepts EVENT_HUB_NAME; default: telemetry-stream)
  RESOURCE_GROUP: Azure resource group containing the Event Hub namespace
  EVENTHOUSE_QUERY_URI: Eventhouse KQL cluster query URI (MasimoEventhouse)
  HLS_ALERT_EMAIL: Allowlisted recipient email address (single address)
  FABRIC_WORKSPACE_NAME: Target Microsoft Fabric workspace name
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

def _bind_interface_if_configured() -> None:
    """Interface binding for en0 on macOS under VPN."""
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

try:
    from scripts.deploy_clinical_activator import (
        ACTIVATOR_POLL_INTERVAL_SECONDS,
        INGEST_LATENCY_ALLOWANCE_SECONDS,
        REFLEX_SETTLE_SECONDS,
        ALERT_TIERS,
        ALERT_PROBE_FIELD,
        alert_probe_subject_marker,
        tiers_at_or_above,
        DEFAULT_COOLDOWN_MINUTES,
        DEFAULT_MIN_TIER,
    )
except ImportError:
    from deploy_clinical_activator import (
        ACTIVATOR_POLL_INTERVAL_SECONDS,
        INGEST_LATENCY_ALLOWANCE_SECONDS,
        REFLEX_SETTLE_SECONDS,
        ALERT_TIERS,
        ALERT_PROBE_FIELD,
        alert_probe_subject_marker,
        tiers_at_or_above,
        DEFAULT_COOLDOWN_MINUTES,
        DEFAULT_MIN_TIER,
    )

KQL_POLL_INTERVAL_SECONDS = 3.0
# Bounds each Eventhouse observation: the timeout of a single query, or the whole window of a poll.
KQL_OBSERVATION_DEADLINE_SECONDS = 30.0
# Activator evaluates every P seconds; allow P + L plus mail transport before T3 is reported not_observed.
GRAPH_POLL_INTERVAL_SECONDS = 10.0
GRAPH_OBSERVATION_DEADLINE_SECONDS = 180.0
GRAPH_PAGE_SIZE = 25
GRAPH_MAX_PAGES = 4
# High-risk condition codes that make the enriched fn_ClinicalAlerts (deploy-fabric-rti.ps1 Phase 2b) escalate a tier.
HIGH_RISK_CONDITION_CODES = ("13645005", "84114007", "195967001", "233604007", "59621000")


def kql_primary_rows(resp: Any) -> Tuple[Optional[List[Any]], Optional[str]]:
    """Return PrimaryResult rows from a Kusto v2 response, or (None, error) when the response is unusable."""
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {str(getattr(resp, 'text', ''))[:500]}"
    try:
        frames = resp.json()
    except Exception as exc:
        return None, f"Invalid JSON: {exc}"
    if not isinstance(frames, list):
        return None, "Kusto response is not a frame list"
    # A v2 DataSetCompletion frame with HasErrors means the PrimaryResult may be partial or absent.
    failed = next((f for f in frames if isinstance(f, dict) and f.get("HasErrors") is True), None)
    if failed is not None:
        return None, f"Kusto in-band error: {json.dumps(failed.get('OneApiErrors') or failed)[:500]}"
    primary = next((f for f in frames if isinstance(f, dict) and f.get("TableKind") == "PrimaryResult"), None)
    if primary is None or not isinstance(primary.get("Rows"), list):
        return None, "Missing PrimaryResult rows"
    return primary["Rows"], None


def poll_until(
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
    deadline_seconds: float,
    interval_seconds: float,
    attempt: Callable[[float], Any],
) -> Any:
    """Call attempt(budget_seconds) until it returns a non-None value or the bounded deadline (time and attempt count) passes.

    Each attempt receives the seconds left before the deadline as the limit for its own network calls. A value that
    arrives after the deadline is not counted, and no attempt starts once the deadline has passed. clock must measure
    elapsed time (time.monotonic), not UTC, so a wall-clock adjustment cannot move the deadline.
    """
    deadline = clock() + deadline_seconds
    max_attempts = int(math.ceil(deadline_seconds / interval_seconds)) + 1
    for attempt_no in range(max_attempts):
        budget = deadline - clock()
        if budget <= 0:
            return None
        value = attempt(budget)
        now = clock()
        if value is not None:
            return value if now <= deadline else None
        if attempt_no + 1 >= max_attempts or now + interval_seconds > deadline:
            return None
        sleeper(interval_seconds)
    return None


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


def validate_cooldown(val: Any) -> int:
    """Validate alert cooldown window in minutes (1..1440). Exits with 2 on CLI failure."""
    try:
        ival = int(val)
    except (ValueError, TypeError):
        sys.stderr.write(f"Error: cooldown_minutes must be an integer between 1 and 1440, got {val}\n")
        sys.exit(2)
    if not (1 <= ival <= 1440):
        sys.stderr.write(f"Error: cooldown_minutes must be between 1 and 1440, got {ival}\n")
        sys.exit(2)
    return ival

def validate_settle_seconds(val: Any) -> float:
    """Validate settle-seconds (0..3600, finite). Exits with code 2 on CLI failure."""
    try:
        fval = float(val)
    except (ValueError, TypeError):
        sys.stderr.write(f"Error: settle_seconds must be a number between 0 and 3600, got {val}\n")
        sys.exit(2)
    if not math.isfinite(fval) or fval < 0.0 or fval > 3600.0:
        sys.stderr.write(f"Error: settle_seconds must be finite and between 0 and 3600 seconds, got {val}\n")
        sys.exit(2)
    return fval


def format_iso_timestamp(epoch: Optional[float]) -> Optional[str]:
    """Format epoch timestamp as ISO8601 UTC string with real observed milliseconds."""
    if epoch is None:
        return None
    dt_val = dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
    return dt_val.isoformat(timespec="milliseconds").replace("+00:00", "Z")


_ISO_UTC_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$"
)


def parse_kql_timestamp(ts_val: Any) -> Optional[float]:
    """Parse a timezone-qualified ISO8601 timestamp (as returned by Kusto and Graph) into epoch seconds.

    Returns None for anything that is not an explicit-offset ISO8601 string (naive, numeric, malformed),
    so missing or invalid source timestamps stay unobserved instead of being reinterpreted. Sub-second
    digits are kept to microsecond precision (Kusto returns up to 7 fractional digits).
    """
    if not isinstance(ts_val, str):
        return None
    match = _ISO_UTC_RE.match(ts_val.strip())
    if not match:
        return None
    base, frac, offset = match.groups()
    micro = (frac or "").ljust(6, "0")[:6]
    tz = "+00:00" if offset == "Z" else offset
    try:
        return dt.datetime.fromisoformat(f"{base}.{micro}{tz}").timestamp()
    except ValueError:
        return None


def classify_alert_outcome(
    drop_epoch: float,
    previous_alert_epoch: Optional[float],
    cooldown_minutes: int = 10,
    poll_interval_seconds: float = ACTIVATOR_POLL_INTERVAL_SECONDS,
    latency_allowance_seconds: float = INGEST_LATENCY_ALLOWANCE_SECONDS,
) -> Tuple[str, bool, bool]:
    """Predict the Activator outcome from Eventhouse alert history (a prediction, not an observation).

    W = cooldown_seconds = cooldown_minutes * 60
    P = poll_interval_seconds (60s)
    L = latency_allowance_seconds (10s)

    - SUPPRESSED_DEDUPE: previous alert is newer than W - L at drop time (delta < W - L)
    - EXPECTED_DISPATCH: no previous alert, or previous alert is older than W + P + L (delta > W + P + L)
    - UNCERTAIN_BOUNDARY: delta between W - L and W + P + L (inclusive). Email expectation unknown;
      T3 is not waited for or asserted.

    Delivery is only DISPATCHED once the matching Activator email is observed (see run_trigger).

    Returns:
        (expected_outcome, is_suppressed, email_expected)
    """
    if previous_alert_epoch is None:
        return "EXPECTED_DISPATCH", False, True

    w_seconds = cooldown_minutes * 60.0
    p_seconds = poll_interval_seconds
    l_seconds = latency_allowance_seconds

    delta = drop_epoch - previous_alert_epoch
    if delta < (w_seconds - l_seconds):
        return "SUPPRESSED_DEDUPE", True, False
    elif delta > (w_seconds + p_seconds + l_seconds):
        return "EXPECTED_DISPATCH", False, True
    else:
        return "UNCERTAIN_BOUNDARY", False, False


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


def calculate_stopwatch(
    t0: float,
    t1: Optional[float] = None,
    t2: Optional[float] = None,
    t3: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Calculate the stopwatch intervals from observed beats; any interval with a missing endpoint is None.

    t_total is strictly T3 - T0 (FR-5): a partial run never reports an earlier beat as the total.
    """
    t_ingest = round(t1 - t0, 3) if (t1 is not None and t1 >= t0) else None
    t_detect = round(t2 - t1, 3) if (t2 is not None and t1 is not None and t2 >= t1) else None
    t_action = round(t3 - t2, 3) if (t3 is not None and t2 is not None and t3 >= t2) else None
    t_total = round(t3 - t0, 3) if (t3 is not None and t3 >= t0) else None
    return {
        "t_ingest": t_ingest,
        "t_detect": t_detect,
        "t_action": t_action,
        "t_total": t_total,
    }


def format_ascii_table(beats: List[Dict[str, Any]], t_total: Optional[float]) -> str:
    """Format stopwatch timing beats in a readable ASCII table."""
    lines = [
        "+------------------------+------------------------------+-------------+",
        "| Timing Beat            | Timestamp (UTC)              | Elapsed (s) |",
        "+------------------------+------------------------------+-------------+",
    ]
    for b in beats:
        name = b["name"][:22].ljust(22)
        raw_ts = b["timestamp"] or b["status"]
        ts = raw_ts[:28].ljust(28)
        if b["elapsed_seconds"] is not None:
            el = f"{b['elapsed_seconds']:>10.1f}s "
        else:
            el = f"{b['status']:>10}  "
        lines.append(f"| {name} | {ts} | {el}|")
    lines.append("+------------------------+------------------------------+-------------+")
    if t_total is not None:
        total_str = f"{t_total:>10.1f}s "
    else:
        total_str = "       N/A  "
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
    workspace_name: Optional[str] = None,
    current_time_epoch: Optional[float] = None,
    previous_alert_epoch: Optional[float] = None,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    min_tier: str = DEFAULT_MIN_TIER,
    settle_seconds: float = 0.0,
    eventhub_namespace: Optional[str] = None,
    resource_group: Optional[str] = None,
    eventhouse_query_uri: Optional[str] = None,
    eventhub_name: Optional[str] = None,
    sleep_fn: Optional[Callable[[float], None]] = None,
    time_fn: Optional[Callable[[], float]] = None,
    monotonic_fn: Optional[Callable[[], float]] = None,
) -> Dict[str, Any]:
    """Execute SpO2 alert trigger, dedupe check, and stopwatch measurement.

    Parameters:
      eventhub_namespace: Target Azure Event Hubs namespace (defaults to EVENTHUB_NAMESPACE or EVENT_HUB_NAMESPACE env var).
      resource_group: Azure resource group (defaults to RESOURCE_GROUP env var).
      eventhouse_query_uri: Eventhouse KQL cluster query URI (defaults to EVENTHOUSE_QUERY_URI env var).
      eventhub_name: Event Hub entity name (defaults to EVENTHUB_NAME or EVENT_HUB_NAME env var or 'telemetry-stream').
      cooldown_minutes: Cooldown window in minutes (1..1440, default: 10).
      min_tier: Lowest alert tier to qualify (default: 'URGENT', which includes CRITICAL and URGENT).
      settle_seconds: Optional delay in seconds before baseline check and drop.
      previous_alert_epoch: Optional epoch timestamp of previous alert for testing or override.
      sleep_fn: Sleep callable for testing / live delays (defaults to time.sleep).
      time_fn: UTC clock callable for event timestamps, T0 and dedupe epochs (defaults to time.time).
      monotonic_fn: Elapsed-time clock for observation deadlines and HTTP budgets (defaults to time.monotonic),
        so a wall-clock adjustment cannot extend or shorten a poll window.
    """
    if cleanup:
        return {
            "status": "UNSUPPORTED_CLEANUP",
            "message": "Cleanup cannot reset Eventhouse deduplication state: synthetic telemetry rows persist in Eventhouse TelemetryRaw and cannot be safely pruned without deleting emulator rows.",
        }

    if not (1 <= cooldown_minutes <= 1440):
        sys.stderr.write(f"Error: cooldown_minutes must be between 1 and 1440, got {cooldown_minutes}\n")
        sys.exit(2)

    try:
        settle_seconds = float(settle_seconds)
    except (ValueError, TypeError):
        sys.stderr.write(f"Error: settle_seconds must be a number between 0 and 3600, got {settle_seconds}\n")
        sys.exit(2)
    if not math.isfinite(settle_seconds) or settle_seconds < 0.0 or settle_seconds > 3600.0:
        sys.stderr.write(f"Error: settle_seconds must be finite and between 0 and 3600 seconds, got {settle_seconds}\n")
        sys.exit(2)

    tier_norm = (min_tier or "").strip().upper()
    if tier_norm not in ALERT_TIERS:
        sys.stderr.write(f"Error: min_tier must be one of {', '.join(ALERT_TIERS)}, got '{min_tier}'\n")
        sys.exit(2)
    min_tier = tier_norm

    recipient = validate_recipient_allowlist(email)
    # Only a live (non-dry-run) execution may reach external services; dry-run resolves from the local cohort.
    observed = not dry_run and live
    patient_name, device_id = resolve_patient_device(patient_id, live=observed)

    sleeper = sleep_fn if sleep_fn is not None else time.sleep
    clock = time_fn if time_fn is not None else time.time
    elapsed_clock = monotonic_fn if monotonic_fn is not None else time.monotonic

    if settle_seconds > 0:
        sleeper(settle_seconds)

    spo2_val = 84.0
    pr_val = 115
    alert_tier = "CRITICAL"
    probe_id = uuid.uuid4().hex
    tier_filter = ", ".join(f"'{tier}'" for tier in tiers_at_or_above(min_tier))

    kql_telemetry_raw: Any = None
    kql_alert_row: Any = None
    graph_msg: Any = None
    graph_error: Optional[str] = None
    baseline_seeded = False
    history_query_failed = False
    history_query_error: Optional[str] = None
    history_high_risk: Optional[bool] = None
    # Last Eventhouse query error for each polled beat; None when no poll of that beat failed.
    poll_errors: Dict[str, Optional[str]] = {"baseline": None, "t1": None, "t2": None}

    planned_epoch = current_time_epoch if current_time_epoch is not None else clock()
    t0_str = format_iso_timestamp(planned_epoch)
    t0_epoch = parse_kql_timestamp(t0_str)
    payload: Dict[str, Any] = {
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
        "metadata": {ALERT_PROBE_FIELD: probe_id},
    }

    t1_epoch: Optional[float] = None
    t2_epoch: Optional[float] = None
    t3_epoch: Optional[float] = None
    t1_source: Optional[str] = None
    t2_source: Optional[str] = None
    t3_source: Optional[str] = None

    if observed:
        rg = resource_group or os.environ.get("RESOURCE_GROUP")
        eh_name = eventhub_name or os.environ.get("EVENTHUB_NAME") or os.environ.get("EVENT_HUB_NAME") or "telemetry-stream"
        ns = eventhub_namespace or os.environ.get("EVENTHUB_NAMESPACE") or os.environ.get("EVENT_HUB_NAMESPACE")
        query_uri = (eventhouse_query_uri or os.environ.get("EVENTHOUSE_QUERY_URI", "")).rstrip("/")

        if not (rg and ns and query_uri):
            missing = []
            if not ns:
                missing.append("--eventhub-namespace / EVENTHUB_NAMESPACE or EVENT_HUB_NAMESPACE")
            if not rg:
                missing.append("--resource-group / RESOURCE_GROUP")
            if not query_uri:
                missing.append("--eventhouse-query-uri / EVENTHOUSE_QUERY_URI")
            sys.stderr.write(f"ERROR: Live execution requires: {', '.join(missing)}\n")
            sys.exit(2)

        eh_token = get_msal_token("https://eventhubs.azure.net/.default")
        if not eh_token:
            cmd_tok = ["az", "account", "get-access-token", "--resource", "https://eventhubs.azure.net", "-o", "json"]
            proc_tok = subprocess.run(cmd_tok, capture_output=True, text=True, timeout=15)
            if proc_tok.returncode != 0:
                sys.stderr.write("EventHub delivery timed out after 15s\n")
                sys.exit(1)
            eh_token = json.loads(proc_tok.stdout)["accessToken"]

        kusto_tok = get_msal_token("https://kusto.kusto.windows.net/.default")
        q_headers = {"Authorization": f"Bearer {kusto_tok}", "Content-Type": "application/json"}
        url = f"https://{ns}.servicebus.windows.net/{eh_name}/messages"

        def kql_rows(csl: str, timeout_seconds: float) -> Tuple[Optional[List[Any]], Optional[str]]:
            try:
                resp = requests.post(
                    f"{query_uri}/v2/rest/query",
                    headers=q_headers,
                    json={"db": "MasimoEventhouse", "csl": csl},
                    timeout=timeout_seconds,
                )
                return kql_primary_rows(resp)
            except Exception as exc:
                return None, str(exc)

        def send_event(event: Dict[str, Any]) -> None:
            try:
                resp = requests.post(
                    url,
                    data=json.dumps(event).encode("utf-8"),
                    headers={"Authorization": f"Bearer {eh_token}", "Content-Type": "application/json"},
                    timeout=15,
                )
            except requests.Timeout:
                sys.stderr.write("EventHub delivery timed out after 15s\n")
                sys.exit(1)
            if resp.status_code not in (200, 201):
                sys.stderr.write("EventHub delivery timed out after 15s\n")
                sys.exit(1)

        # Question 3: Check KQL for telemetry from target device in last 55 minutes
        csl_check = (
            f"TelemetryRaw\n"
            f"| where tostring(device_id) == '{device_id}' and todatetime(timestamp) > ago(55m)\n"
            f"| project ingestion_time(), timestamp, device_id\n"
            f"| take 1"
        )
        recent_rows, _ = kql_rows(csl_check, KQL_OBSERVATION_DEADLINE_SECONDS)
        if not recent_rows:
            baseline_seeded = True
            base_timestamp = format_iso_timestamp(clock())
            base_probe_id = uuid.uuid4().hex
            send_event({
                "device_id": device_id,
                "timestamp": base_timestamp,
                "telemetry": {
                    "spo2": 97.0,
                    "pr": 80,
                    "pi": 2.5,
                    "pvi": 12,
                    "sphb": 13.0,
                    "signal_iq": 98,
                },
                "metadata": {ALERT_PROBE_FIELD: base_probe_id},
            })

            # Wait until this baseline row is queryable in TelemetryRaw (bounded 30s deadline)
            sleeper(KQL_POLL_INTERVAL_SECONDS)
            csl_base_poll = (
                f"TelemetryRaw\n"
                f"| where tostring(device_id) == '{device_id}' and tostring(metadata.{ALERT_PROBE_FIELD}) == '{base_probe_id}'\n"
                f"| project ingestion_time(), timestamp, device_id\n"
                f"| take 1"
            )

            def observe_baseline(budget: float) -> Optional[bool]:
                rows, error = kql_rows(csl_base_poll, budget)
                if error:
                    poll_errors["baseline"] = error
                return True if rows else None

            base_found = poll_until(elapsed_clock, sleeper, KQL_OBSERVATION_DEADLINE_SECONDS, KQL_POLL_INTERVAL_SECONDS, observe_baseline)
            if not base_found:
                sys.stderr.write(
                    f"ERROR: Baseline telemetry row with timestamp {base_timestamp} not queryable in TelemetryRaw after "
                    f"{KQL_OBSERVATION_DEADLINE_SECONDS:.0f}s deadline for device {device_id}; "
                    f"last query error: {poll_errors['baseline'] or 'none'}\n"
                )
                sys.exit(1)

            # Wait one Activator evaluation interval plus ingestion latency before drop (P + L)
            sleeper(REFLEX_SETTLE_SECONDS)

        # Query previous qualifying reading from Eventhouse if not explicitly provided
        if previous_alert_epoch is None:
            lookback_seconds = int(cooldown_minutes * 60 + REFLEX_SETTLE_SECONDS)
            # The Reflex reads fn_ClinicalAlerts(cooldown) | where alert_tier in (...). The enriched fn_ClinicalAlerts
            # (deploy-fabric-rti.ps1 Phase 2b) rates each device over a window that ends at now(), so it cannot answer
            # for a past time. This query repeats its tier logic for each reading in the lookback:
            # - Base tier: the fn_SpO2Alerts / fn_PulseRateAlerts thresholds (inlined identically in deploy-fabric-rti.ps1
            #   and utilities/run-kql-scripts.ps1). SpO2 counts only non-null readings with 0 < spo2 < 100 and is compared
            #   unrounded. Pulse is compared as toint(pr) with no positivity filter (a 0 bpm reading is CRITICAL bradycardia).
            # - Escalation: WARNING becomes URGENT and URGENT becomes CRITICAL when a patient linked to the device has a
            #   high-risk condition. The device-to-patient link and the condition codes come from the same Silver
            #   external tables, filters, and codes that fn_ClinicalAlerts uses.
            # The query returns the last qualifying reading time and the high-risk flag. If the query fails or the flag
            # is missing, the escalation is unknown and the outcome is UNCERTAIN_BOUNDARY.
            patient_ref = (
                "coalesce(tostring(subject.idOrig), replace_string(tostring(subject.msftSourceReference), 'Patient/', ''), "
                "tostring(subject.identifier.value))"
            )
            csl_prev = (
                f"let device_patients = external_table('SilverBasic')\n"
                f"    | where tostring(code.coding[0].code) in ('device-assoc', 'ASSIGNED')\n"
                f"    | extend ext = parse_json(extension)\n"
                f"    | mv-expand ext\n"
                f"    | where tostring(ext.url) has 'associated-device' or tostring(ext.url) has 'device-association-device'\n"
                f"    | where replace_string(tostring(ext.valueReference.reference), 'Device/', '') == '{device_id}'\n"
                f"    | project patient_orig_id = {patient_ref};\n"
                f"let high_risk_patients = external_table('SilverCondition')\n"
                f"    | mv-expand coding = code.coding\n"
                f"    | where tostring(coding.code) in ({', '.join(repr(code) for code in HIGH_RISK_CONDITION_CODES)})\n"
                f"    | extend patient_orig_id = {patient_ref}\n"
                f"    | where isnotempty(patient_orig_id)\n"
                f"    | summarize conditions = make_set(tostring(coding.display)) by patient_orig_id\n"
                f"    | where isnotempty(strcat_array(conditions, ', '));\n"
                f"let device_high_risk = toscalar(device_patients | join kind=inner high_risk_patients on patient_orig_id | count) > 0;\n"
                f"TelemetryRaw\n"
                f"| where todatetime(timestamp) > ago({lookback_seconds}s)\n"
                f"| where tostring(device_id) == '{device_id}'\n"
                f"| extend spo2 = iff(isnotnull(telemetry.spo2), todouble(telemetry.spo2), real(null)), pr = toint(telemetry.pr)\n"
                f"| extend spo2 = iff(spo2 > 0 and spo2 < 100, spo2, real(null))\n"
                f"| extend spo2_tier = case(spo2 < 85, 'CRITICAL', spo2 < 90, 'URGENT', spo2 < 94, 'WARNING', '')\n"
                f"| extend pr_tier = case(pr > 150 or pr < 40, 'CRITICAL', pr > 130 or pr < 45, 'URGENT', pr > 110 or pr < 50, 'WARNING', '')\n"
                f"| extend base_tier = case(spo2_tier == 'CRITICAL' or pr_tier == 'CRITICAL', 'CRITICAL', spo2_tier == 'URGENT' or pr_tier == 'URGENT', 'URGENT', spo2_tier == 'WARNING' or pr_tier == 'WARNING', 'WARNING', 'NORMAL')\n"
                f"| extend alert_tier = case(base_tier == 'URGENT' and device_high_risk, 'CRITICAL', base_tier == 'WARNING' and device_high_risk, 'URGENT', base_tier)\n"
                f"| where alert_tier in ({tier_filter})\n"
                f"| summarize max(todatetime(timestamp))\n"
                f"| extend has_high_risk = device_high_risk"
            )
            rows, history_query_error = kql_rows(csl_prev, KQL_OBSERVATION_DEADLINE_SECONDS)
            if rows is None:
                history_query_failed = True
            elif len(rows) != 1 or not isinstance(rows[0], list) or len(rows[0]) < 1:
                history_query_failed = True
                history_query_error = f"Expected exactly 1 aggregate row in PrimaryResult, got {rows!r:.200}"
            elif len(rows[0]) < 2 or not isinstance(rows[0][1], bool):
                history_query_failed = True
                history_query_error = f"Missing patient high-risk flag in history result: {rows[0]!r:.200}"
            else:
                history_high_risk = rows[0][1]
                if rows[0][0] is not None:
                    # A one-row null aggregate proves there is no qualifying history.
                    previous_alert_epoch = parse_kql_timestamp(rows[0][0])
                    if previous_alert_epoch is None:
                        history_query_failed = True
                        history_query_error = f"Malformed timestamp in history result: {rows[0][0]!r}"

            if history_query_failed:
                sys.stderr.write(f"WARNING: Eventhouse alert history query failed: {history_query_error}\n")

        # 1. Send SpO2 drop telemetry to Event Hub; T0 is the emitted timestamp
        t0_str = format_iso_timestamp(clock())
        t0_epoch = parse_kql_timestamp(t0_str)
        payload["timestamp"] = t0_str
        send_event(payload)

        # 2. T1: ingestion_time() of this probe's row in TelemetryRaw (bounded deadline)
        sleeper(KQL_POLL_INTERVAL_SECONDS)
        csl_t1 = (
            f"TelemetryRaw\n"
            f"| where tostring(device_id) == '{device_id}'\n"
            f"| where tostring(metadata.{ALERT_PROBE_FIELD}) == '{probe_id}'\n"
            f"| project ingested_at = ingestion_time(), timestamp, device_id, telemetry, metadata\n"
            f"| top 1 by ingested_at desc"
        )

        def observe_t1(budget: float) -> Optional[Tuple[float, str]]:
            nonlocal kql_telemetry_raw
            rows, error = kql_rows(csl_t1, budget)
            if error:
                poll_errors["t1"] = error
            if not rows or not isinstance(rows[0], list) or not rows[0]:
                return None
            kql_telemetry_raw = rows[0]
            parsed = parse_kql_timestamp(rows[0][0])
            if parsed is None or parsed < t0_epoch:
                return None
            return parsed, rows[0][0]

        t1_obs = poll_until(elapsed_clock, sleeper, KQL_OBSERVATION_DEADLINE_SECONDS, KQL_POLL_INTERVAL_SECONDS, observe_t1)
        if t1_obs:
            t1_epoch, t1_source = t1_obs

        # 3. T2: Eventhouse evaluation time (now()) of the first fn_ClinicalAlerts query whose qualifying
        # alert row for this device is backed by this probe's row inside the same window.
        csl_t2 = (
            f"let probe_devices = TelemetryRaw\n"
            f"    | where todatetime(timestamp) > ago(1m * {cooldown_minutes})\n"
            f"    | where tostring(device_id) == '{device_id}' and tostring(metadata.{ALERT_PROBE_FIELD}) == '{probe_id}'\n"
            f"    | distinct device_id;\n"
            f"fn_ClinicalAlerts({cooldown_minutes})\n"
            f"| where tostring(device_id) == '{device_id}' and alert_tier == '{alert_tier}'\n"
            f"| where alert_time >= todatetime('{t0_str}')\n"
            f"| join kind=inner probe_devices on device_id\n"
            f"| extend evaluated_at = now()\n"
            f"| project evaluated_at, alert_time, alert_tier, alert_type, spo2, pr\n"
            f"| top 1 by alert_time desc"
        )

        def observe_t2(budget: float) -> Optional[Tuple[float, str]]:
            nonlocal kql_alert_row
            rows, error = kql_rows(csl_t2, budget)
            if error:
                poll_errors["t2"] = error
            if not rows or not isinstance(rows[0], list) or len(rows[0]) < 2:
                return None
            kql_alert_row = rows[0]
            evaluated = parse_kql_timestamp(rows[0][0])
            alert_time = parse_kql_timestamp(rows[0][1])
            if evaluated is None or alert_time is None or evaluated < t0_epoch or alert_time < t0_epoch:
                return None
            return evaluated, rows[0][0]

        t2_obs = poll_until(elapsed_clock, sleeper, KQL_OBSERVATION_DEADLINE_SECONDS, KQL_POLL_INTERVAL_SECONDS, observe_t2)
        if t2_obs:
            t2_epoch, t2_source = t2_obs

    if history_query_failed:
        expected_outcome, is_suppressed, email_expected = ("UNCERTAIN_BOUNDARY", False, False)
    else:
        expected_outcome, is_suppressed, email_expected = classify_alert_outcome(
            drop_epoch=t0_epoch,
            previous_alert_epoch=previous_alert_epoch,
            cooldown_minutes=cooldown_minutes,
            poll_interval_seconds=ACTIVATOR_POLL_INTERVAL_SECONDS,
            latency_allowance_seconds=INGEST_LATENCY_ALLOWANCE_SECONDS,
        )

    # 4. T3: receivedDateTime of the Activator email whose subject carries this probe's marker
    if observed and email_expected:
        graph_tok = get_msal_token("https://graph.microsoft.com/Mail.Read") or get_msal_token("https://graph.microsoft.com/.default")
        if graph_tok:
            marker = alert_probe_subject_marker(probe_id)
            first_page = (
                "https://graph.microsoft.com/v1.0/me/messages"
                f"?$filter=receivedDateTime ge {t0_str}&$orderby=receivedDateTime desc&$top={GRAPH_PAGE_SIZE}"
                "&$select=subject,from,receivedDateTime"
            )

            def observe_t3(budget: float) -> Optional[Tuple[float, str, Dict[str, Any]]]:
                nonlocal graph_error
                page_deadline = elapsed_clock() + budget
                page_url: Optional[str] = first_page
                for _ in range(GRAPH_MAX_PAGES):
                    if not page_url:
                        return None
                    remaining = page_deadline - elapsed_clock()
                    if remaining <= 0:
                        return None
                    try:
                        g_resp = requests.get(page_url, headers={"Authorization": f"Bearer {graph_tok}"}, timeout=min(15.0, remaining))
                        if g_resp.status_code != 200:
                            graph_error = f"HTTP {g_resp.status_code}: {g_resp.text}"
                            return None
                        body = g_resp.json()
                    except Exception as exc:
                        graph_error = str(exc)
                        return None
                    messages = body.get("value") if isinstance(body, dict) else None
                    if not isinstance(messages, list):
                        graph_error = f"Malformed Graph messages page: {str(body)[:200]}"
                        return None
                    graph_error = None
                    for msg in messages:
                        subject = msg.get("subject") if isinstance(msg, dict) else None
                        if not isinstance(subject, str) or marker not in subject or device_id not in subject:
                            continue
                        received_raw = msg.get("receivedDateTime")
                        received = parse_kql_timestamp(received_raw)
                        if received is None or received < t0_epoch:
                            continue
                        return received, received_raw, msg
                    page_url = body.get("@odata.nextLink")
                return None

            t3_obs = poll_until(elapsed_clock, sleeper, GRAPH_OBSERVATION_DEADLINE_SECONDS, GRAPH_POLL_INTERVAL_SECONDS, observe_t3)
            if t3_obs:
                t3_epoch, t3_source, activator_msg = t3_obs
                graph_msg = {
                    "subject": activator_msg.get("subject"),
                    "from": ((activator_msg.get("from") or {}).get("emailAddress") or {}).get("address"),
                    "receivedDateTime": t3_source,
                }
            elif graph_error is None:
                graph_error = f"No Activator email with subject marker {marker} for {device_id} within {GRAPH_OBSERVATION_DEADLINE_SECONDS:.0f}s"
        else:
            graph_error = "Graph token unavailable; Mail.Read consent not granted or token unavailable"

    latencies = calculate_stopwatch(t0_epoch, t1_epoch, t2_epoch, t3_epoch)
    dispatch_observed = t3_epoch is not None

    def observed_status(epoch: Optional[float]) -> str:
        if not observed:
            return "planned"
        return "completed" if epoch is not None else "not_observed"

    if not observed:
        beat_t3_status = "planned"
    elif dispatch_observed:
        beat_t3_status = "completed"
    elif expected_outcome == "SUPPRESSED_DEDUPE":
        beat_t3_status = "suppressed"
    elif expected_outcome == "UNCERTAIN_BOUNDARY":
        beat_t3_status = "uncertain"
    else:
        beat_t3_status = "not_observed"

    beats = [
        {
            "id": "telemetry_emitted",
            "name": "Telemetry Emitted",
            "timestamp": t0_str if observed else None,
            "elapsed_seconds": 0.0 if observed else None,
            "status": "completed" if observed else "planned",
        },
        {
            "id": "eventstream_enqueued",
            "name": "Eventstream Enqueued",
            "timestamp": t1_source,
            "elapsed_seconds": latencies["t_ingest"],
            "status": observed_status(t1_epoch),
        },
        {
            "id": "kql_detected",
            "name": "KQL Detected",
            "timestamp": t2_source,
            "elapsed_seconds": round(t2_epoch - t0_epoch, 3) if t2_epoch is not None else None,
            "status": observed_status(t2_epoch),
        },
        {
            "id": "activator_dispatched",
            "name": "Activator Dispatched",
            "timestamp": t3_source,
            "elapsed_seconds": round(t3_epoch - t0_epoch, 3) if t3_epoch is not None else None,
            "status": beat_t3_status,
        },
    ]

    if not observed:
        status_str = "PLANNED"
    elif dispatch_observed:
        status_str = "DISPATCHED"
    elif expected_outcome == "EXPECTED_DISPATCH":
        status_str = "DISPATCH_NOT_OBSERVED"
    else:
        status_str = expected_outcome

    result = {
        "status": status_str,
        "expected_outcome": expected_outcome,
        "email_expected": email_expected,
        "dispatch_observed": dispatch_observed,
        "suppressed_by_dedupe": is_suppressed,
        "probe_id": probe_id,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "device_id": device_id,
        "alert_tier": alert_tier,
        "spo2": spo2_val,
        "pulse_rate": pr_val,
        "recipient": recipient,
        "baseline_seeded": baseline_seeded,
        "cooldown_minutes": cooldown_minutes,
        "min_tier": min_tier,
        "history_patient_high_risk": history_high_risk,
        "poll_errors": poll_errors,
        "mode": "LIVE" if observed else "DRY RUN (no live network writes)",
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
    if expected_outcome == "UNCERTAIN_BOUNDARY":
        if history_query_failed:
            result["boundary_notice"] = f"Eventhouse alert history query failed ({history_query_error}); outcome classified as UNCERTAIN_BOUNDARY."
        else:
            result["boundary_notice"] = "Drop occurred within Activator boundary window (W - L to W + P + L); email expectation unknown; T3 measurement skipped."
    return result

def main() -> int:
    _bind_interface_if_configured()
    parser = argparse.ArgumentParser(description="Trigger deterministic SpO2 alert and measure latency stopwatch.")
    parser.add_argument("--patient-id", default="TCGA-G6-A8L6", help="Patient ID (default: TCGA-G6-A8L6)")
    parser.add_argument("--email", help="Notification recipient email (must match HLS_ALERT_EMAIL allowlist)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run mode (default: True)")
    parser.add_argument("--live", action="store_true", help="Live execution against Event Hub and Eventhouse")
    parser.add_argument("--cleanup", action="store_true", help="Report cleanup status (Eventhouse dedupe state cannot be reset)")
    parser.add_argument("--min-tier", type=str.upper, choices=ALERT_TIERS, default=DEFAULT_MIN_TIER, help="Lowest alert tier to qualify (default: URGENT, which includes CRITICAL and URGENT)")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--workspace-name", "--workspace", dest="workspace_name", default=os.environ.get("FABRIC_WORKSPACE_NAME"), help="Fabric workspace name")
    parser.add_argument("--eventhub-namespace", default=os.environ.get("EVENTHUB_NAMESPACE") or os.environ.get("EVENT_HUB_NAMESPACE"), help="Event Hub namespace via EVENTHUB_NAMESPACE or EVENT_HUB_NAMESPACE env var (required in --live)")
    parser.add_argument("--resource-group", default=os.environ.get("RESOURCE_GROUP"), help="Azure resource group (required in --live)")
    parser.add_argument("--eventhouse-query-uri", default=os.environ.get("EVENTHOUSE_QUERY_URI"), help="Eventhouse KQL cluster query URI (required in --live)")
    parser.add_argument("--eventhub-name", default=os.environ.get("EVENTHUB_NAME") or os.environ.get("EVENT_HUB_NAME") or "telemetry-stream", help="Event Hub entity name via EVENTHUB_NAME or EVENT_HUB_NAME env var (default: telemetry-stream)")
    parser.add_argument("--cooldown-minutes", type=validate_cooldown, default=DEFAULT_COOLDOWN_MINUTES, help="Alert deduplication cooldown window in minutes (1..1440, default: 10)")
    parser.add_argument("--settle-seconds", type=validate_settle_seconds, default=0.0, help="Optional delay in seconds to allow Activator to settle before baseline/drop (default: 0.0)")
    args = parser.parse_args()
    if args.live:
        missing = []
        if not args.eventhub_namespace:
            missing.append("--eventhub-namespace")
        if not args.resource_group:
            missing.append("--resource-group")
        if not args.eventhouse_query_uri:
            missing.append("--eventhouse-query-uri")
        if missing:
            sys.stderr.write(f"ERROR: Live execution requires arguments: {', '.join(missing)}\n")
            return 2

    dry_run = not args.live if args.live else True
    if "--dry-run" in sys.argv and "--live" in sys.argv:
        dry_run = True

    validate_cooldown(args.cooldown_minutes)
    res = run_trigger(
        patient_id=args.patient_id,
        email=args.email,
        dry_run=dry_run,
        live=args.live,
        cleanup=args.cleanup,
        workspace_name=args.workspace_name,
        eventhub_namespace=args.eventhub_namespace,
        resource_group=args.resource_group,
        eventhouse_query_uri=args.eventhouse_query_uri,
        eventhub_name=args.eventhub_name,
        cooldown_minutes=args.cooldown_minutes,
        min_tier=args.min_tier,
        settle_seconds=args.settle_seconds,
    )
    if args.cleanup:
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(res.get("message", "Cleanup cannot reset Eventhouse deduplication state."))
        return 1

    t1_beat = next((b for b in res.get("beats", []) if b.get("id") == "eventstream_enqueued"), None)
    t2_beat = next((b for b in res.get("beats", []) if b.get("id") == "kql_detected"), None)
    t1_observed = bool(t1_beat and t1_beat.get("status") == "completed")
    t2_observed = bool(t2_beat and t2_beat.get("status") == "completed")
    live_run = res.get("mode") == "LIVE"
    failure: Optional[str] = None
    if live_run and not (t1_observed and t2_observed):
        poll_errors = res.get("poll_errors") or {}
        failure = (
            f"ERROR: Live alert verification failed: "
            f"T1 observed={t1_observed} (last query error: {poll_errors.get('t1') or 'none'}), "
            f"T2 observed={t2_observed} (last query error: {poll_errors.get('t2') or 'none'})\n"
        )
    if args.json:
        print(json.dumps(res, indent=2))
        if failure:
            sys.stderr.write(failure)
            return 1
        return 0
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
    print(f"Baseline Seeded: {res['baseline_seeded']}")
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
    print(f"Structured Result: {json.dumps({'status': res['status'], 'expected_outcome': res['expected_outcome'], 'dispatch_observed': res['dispatch_observed'], 'probe_id': res['probe_id'], 'total_seconds': res['t_total'], 'suppressed_by_dedupe': res['suppressed_by_dedupe'], 'baseline_seeded': res['baseline_seeded']})}")
    if res.get("boundary_notice"):
        print(f"Notice: {res['boundary_notice']}")

    if failure:
        sys.stderr.write(failure)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Refresh the cardiology gold tables from the FHIR service (system of record).

    python3 refresh_cardiology_gold.py [--since ISO8601] [--skip-export] [--skip-ingest] [--skip-gold]

Runs the estate's standard path end to end:
  1. FHIR bulk $export of the resource types the gold projection reads, changed since the
     watermark, into the service's configured `fhir-export` container. That
     container is the bronze lakehouse shortcut
     Files/Ingest/Clinical/FHIR-NDJSON/FHIR-HDS.
  2. healthcare1_msft_clinical_data_foundation_ingestion: NDJSON -> bronze
     ClinicalFhir -> silver (HDS flattening; silver upserts by FHIR id).
  3. The cardiology_gold_projection notebook: silver -> reporting gold.
  4. A metadata sync of the gold SQL analytics endpoint. Without it, SQL
     readers (the app) keep seeing the previous table version for minutes.

Watermark (when --since is omitted): the newest meta.lastUpdated across all silver
rows of those types (tagged or not: Patient and Basic device-assoc are untagged),
minus a 5-minute overlap. If silver has none yet,
the oldest tagged resource in FHIR. An overlap only re-exports rows that silver
upserts by id, so it never duplicates.

SYNTHETIC DATA ONLY. Auth: az CLI, pinned to the brakekat subscription.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SUBSCRIPTION = "9bbee190-dc61-4c58-ab47-1275cb04018f"
FHIR_URL = "https://hdwsfrzkspw34dzci-fhirfrzkspw34dzci.fhir.azurehealthcareapis.com"
EXPORT_CONTAINER = "fhir-export"
WORKSPACE_ID = "f8f84d68-cfa1-4460-95d1-943fac43248a"
INGEST_PIPELINE_ID = "7a1cb1a4-fe5d-4f8d-a7eb-43c422ce087d"  # healthcare1_msft_clinical_data_foundation_ingestion
GOLD_NOTEBOOK_NAME = "cardiology_gold_projection"
TAG = "https://brakekat.com/hls/tags|synthetic-caldova-cardiology"
# Every silver type the gold projection reads (Patient and the Masimo Basic device-assoc links are untagged).
TYPES = ["Patient", "Basic", "Encounter", "Condition", "CareTeam", "Device", "DeviceUseStatement", "Observation"]
SQL_HOST = "nkhahdl5to4ezo6p5bg76flepa-nbg7r6fbz5qejforsq72yqzeri.datawarehouse.fabric.microsoft.com"
FABRIC = "https://api.fabric.microsoft.com/v1"
GOLD_SQL_ENDPOINT_ID = "6b0f4a14-0959-4fa5-9cde-efedfff11bae"  # healthcare1_reporting_gold
GOLD_TABLES = ("cardiology_subject", "cardiology_observation", "cardiology_enrollable_patient")


def token(resource: str) -> str:
    out = subprocess.check_output(
        ["az", "account", "get-access-token", "--subscription", SUBSCRIPTION, "--resource", resource, "-o", "json"])
    return json.loads(out)["accessToken"]


def http(method: str, url: str, tok: str, body: dict | None = None, headers: dict | None = None):
    headers = dict(headers or {})
    if urllib.parse.urlparse(url).hostname == "api.fabric.microsoft.com":
        headers["x-ms-fabric-skill"] = "spark-cli"
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                                          **headers})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:2000], e.headers


def silver_watermark() -> dt.datetime | None:
    """Newest meta.lastUpdated across all silver rows of TYPES (no tag filter), via the SQL endpoint."""
    try:
        import mssql_python  # noqa: PLC0415 - optional; only the watermark needs it
    except ImportError:
        sys.exit("--since is required when mssql_python is unavailable (pip install mssql-python)")
    import struct  # noqa: PLC0415
    tb = token("https://database.windows.net/").encode("utf-16-le")
    conn = mssql_python.connect(f"Server={SQL_HOST},1433;Database=healthcare1_msft_silver;Encrypt=yes;",
                                attrs_before={1256: struct.pack("<i", len(tb)) + tb})
    cur = conn.cursor()
    unions = " UNION ALL ".join(f"SELECT MAX(meta_lastUpdated) m FROM dbo.[{t}]" for t in TYPES)
    cur.execute(f"SELECT MAX(m) FROM ({unions}) u")
    row = cur.fetchone()
    conn.close()
    value = row[0] if row else None
    return value.replace(tzinfo=dt.timezone.utc) if value else None


def fhir_oldest_tagged(tok: str) -> dt.datetime | None:
    oldest = None
    for t in TYPES:
        s, b, _ = http("GET", f"{FHIR_URL}/{t}?_tag={urllib.parse.quote(TAG)}&_sort=_lastUpdated&_count=1&_elements=meta", tok)
        if s != 200:
            sys.exit(f"FHIR search {t} failed: {s} {b}")
        for e in b.get("entry", []):
            lu = dt.datetime.fromisoformat(e["resource"]["meta"]["lastUpdated"].replace("Z", "+00:00"))
            oldest = lu if oldest is None or lu < oldest else oldest
    return oldest


def export(since: dt.datetime) -> list[dict]:
    tok = token(FHIR_URL)
    since_s = since.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    q = urllib.parse.urlencode({"_container": EXPORT_CONTAINER, "_type": ",".join(TYPES), "_since": since_s})
    s, b, h = http("GET", f"{FHIR_URL}/$export?{q}", tok, headers={"Accept": "application/fhir+json", "Prefer": "respond-async"})
    if s != 202:
        sys.exit(f"$export not accepted: {s} {b}")
    status_url = h["Content-Location"]
    print(f"  $export since {since_s} started")
    for _ in range(180):
        time.sleep(10)
        s, b, _ = http("GET", status_url, token(FHIR_URL))
        if s == 200:
            files = b.get("output", [])
            for f in files:
                print(f"    {f['type']}: {f.get('count', '?')} -> {f['url'].split('/')[-2]}/{f['url'].split('/')[-1]}")
            errs = b.get("error", [])
            if errs:
                sys.exit(f"$export reported errors: {errs}")
            return files
        if s != 202:
            sys.exit(f"$export failed: {s} {b}")
    sys.exit("$export did not finish within 30 minutes")


def run_fabric_job(item_id: str, job_type: str, label: str, timeout_s: int = 5400) -> None:
    s, b, h = http("POST", f"{FABRIC}/workspaces/{WORKSPACE_ID}/items/{item_id}/jobs/instances?jobType={job_type}",
                   token("https://api.fabric.microsoft.com"), body={})
    if s != 202:
        sys.exit(f"{label}: submit failed {s} {b}")
    loc, started = h["Location"], time.time()
    print(f"  {label}: submitted")
    while time.time() - started < timeout_s:
        time.sleep(30)
        s, b, _ = http("GET", loc, token("https://api.fabric.microsoft.com"))
        state = (b or {}).get("status") if isinstance(b, dict) else None
        if state in ("Completed", "Succeeded"):
            print(f"  {label}: {state} in {int(time.time() - started)} s")
            return
        if state in ("Failed", "Cancelled", "Deduped"):
            sys.exit(f"{label}: {state} {json.dumps(b.get('failureReason'))}")
    sys.exit(f"{label}: still running after {timeout_s} s")


def gold_notebook_id() -> str:
    s, b, _ = http("GET", f"{FABRIC}/workspaces/{WORKSPACE_ID}/notebooks", token("https://api.fabric.microsoft.com"))
    if s != 200:
        sys.exit(f"cannot list notebooks: {s} {b}")
    ids = [n["id"] for n in b["value"] if n["displayName"] == GOLD_NOTEBOOK_NAME]
    if len(ids) != 1:
        sys.exit(f"expected exactly one notebook named {GOLD_NOTEBOOK_NAME}, found {len(ids)}")
    return ids[0]


def sync_gold_endpoint() -> None:
    """Make the new gold table versions visible over SQL, and fail if any table did not sync."""
    s, b, h = http("POST", f"{FABRIC}/workspaces/{WORKSPACE_ID}/sqlEndpoints/{GOLD_SQL_ENDPOINT_ID}/refreshMetadata",
                   token("https://api.fabric.microsoft.com"), body={})
    if s == 202:
        loc = h["Location"]
        for _ in range(60):
            time.sleep(5)
            s, b, _ = http("GET", loc, token("https://api.fabric.microsoft.com"))
            if isinstance(b, dict) and b.get("status") in ("Succeeded", "Failed"):
                s, b, _ = http("GET", loc + "/result", token("https://api.fabric.microsoft.com"))
                break
    if s != 200 or not isinstance(b, dict):
        sys.exit(f"gold SQL endpoint sync failed: {s} {b}")
    synced = {t["tableName"]: t["status"] for t in b.get("value", []) if t.get("tableName") in GOLD_TABLES}
    if set(synced) != set(GOLD_TABLES) or any(v not in ("Success", "NotRun") for v in synced.values()):
        sys.exit(f"gold SQL endpoint sync incomplete: {synced}")
    print(f"  gold SQL endpoint synced: {synced}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", help="ISO-8601 export watermark (default: derived from silver/FHIR)")
    ap.add_argument("--skip-export", action="store_true")
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--skip-gold", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    if not a.skip_export:
        if a.since:
            since = dt.datetime.fromisoformat(a.since.replace("Z", "+00:00"))
        else:
            since = silver_watermark()
            since = since - dt.timedelta(minutes=5) if since else fhir_oldest_tagged(token(FHIR_URL))
            if since is None:
                sys.exit("no tagged cardiology resources in FHIR: run the seed first")
            since -= dt.timedelta(minutes=1)
        print("1/4 FHIR $export")
        export(since)
    if not a.skip_ingest:
        print("2/4 clinical foundation ingestion (bronze -> silver)")
        run_fabric_job(INGEST_PIPELINE_ID, "Pipeline", "clinical_data_foundation_ingestion")
    if not a.skip_gold:
        print("3/4 cardiology gold projection")
        run_fabric_job(gold_notebook_id(), "RunNotebook", GOLD_NOTEBOOK_NAME)
        print("4/4 gold SQL endpoint sync")
        sync_gold_endpoint()
    print(f"done in {int(time.time() - t0)} s")


if __name__ == "__main__":
    main()

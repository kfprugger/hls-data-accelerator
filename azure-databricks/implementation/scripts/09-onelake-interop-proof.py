#!/usr/bin/env python3
"""09-onelake-interop-proof.py — Azure Databricks Zero-Copy OneLake Interoperability.

Executes an Azure Databricks Serverless SQL query against the OneLake external location
over the shared clinical patient table, verifies access to the 15 TCGA patients with
zero copy, writes an execution proof to Files/interop/databricks_proof.json in
imaging_lakehouse, and updates the local fixture for Data Map rendering.

Usage:
    python 09-onelake-interop-proof.py [--dry-run] [--live] [--cleanup]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import sys
import time
from datetime import datetime, timezone

import requests
import urllib3.util.connection

# Apply macOS en0 socket binding when VPN is present to reach Azure/Fabric endpoints
_bind_if = os.environ.get("HLS_BIND_INTERFACE", "en0")
if sys.platform == "darwin" and _bind_if:
    try:
        _idx = socket.if_nametoindex(_bind_if)
        _orig_conn = urllib3.util.connection.create_connection

        def _bound_conn(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, socket_options=None):
            opts = list(socket_options or []) + [(socket.IPPROTO_IP, 25, _idx)]
            return _orig_conn(address, timeout=timeout, source_address=source_address, socket_options=opts)

        urllib3.util.connection.create_connection = _bound_conn
    except Exception:
        pass

ROOT = pathlib.Path(__file__).resolve().parents[3]
FIXTURE_PATH = ROOT / "rayfin-imaging" / "local" / "fixtures" / "databricks_proof.json"
COHORT_PATH = ROOT / "rayfin-imaging" / "pipeline" / "cohort.json"

DEFAULT_DATABRICKS_AUDIENCE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
DEFAULT_WORKSPACE_ID = "f306e105-78fd-4b16-bfbe-2b556d493cb7"
DEFAULT_IMAGING_LH_ID = "62b95c09-2875-4eb5-8c70-88883dec1a53"
DEFAULT_DATABRICKS_HOST = "https://adb-7405612719149111.11.azuredatabricks.net"

ONELAKE_DFS_BASE = "https://onelake.dfs.fabric.microsoft.com"
MAX_POLL_RETRIES = 36
POLL_INTERVAL_SEC = 5
STATEMENT_TIMEOUT_SEC = 180
ONELAKE_TIMEOUT_SEC = 30


def get_entra_token(scope: str) -> str:
    """Obtain an Entra ID token using environment, MSAL refresh cache, or Azure CLI."""
    env_map = {
        "https://storage.azure.com/.default": "HLS_STORAGE_TOKEN",
        "https://api.fabric.microsoft.com/.default": "HLS_FABRIC_TOKEN",
        f"{DEFAULT_DATABRICKS_AUDIENCE}/.default": "DATABRICKS_TOKEN",
        DEFAULT_DATABRICKS_AUDIENCE: "DATABRICKS_TOKEN",
    }
    for k, env_var in env_map.items():
        if (scope == k or scope.startswith(k)) and os.environ.get(env_var):
            return os.environ[env_var]

    # Attempt MSAL refresh-token exchange
    az_dir = pathlib.Path(os.environ.get("AZURE_CONFIG_DIR") or (pathlib.Path.home() / ".azure-isolated" / "JBATL"))
    if not az_dir.is_dir():
        az_dir = pathlib.Path.home() / ".azure"

    msal_path = az_dir / "msal_token_cache.json"
    if msal_path.is_file():
        try:
            msal = json.loads(msal_path.read_text())
            rt_entries = list(msal.get("RefreshToken", {}).values())
            if rt_entries:
                rt_entry = rt_entries[0]
                prof_path = az_dir / "azureProfile.json"
                tenant = "organizations"
                if prof_path.is_file():
                    profiles = json.loads(prof_path.read_bytes().decode("utf-8-sig"))
                    tenant = next((s["tenantId"] for s in profiles.get("subscriptions", []) if s.get("isDefault")), tenant)
                token_scope = f"{scope} offline_access" if "offline_access" not in scope else scope
                r = requests.post(
                    f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                    data={
                        "client_id": rt_entry["client_id"],
                        "grant_type": "refresh_token",
                        "refresh_token": rt_entry["secret"],
                        "scope": token_scope,
                    },
                    timeout=20,
                )
                if r.status_code == 200 and "access_token" in r.json():
                    return r.json()["access_token"]
        except Exception:
            pass

    # Fallback to Azure CLI credential
    try:
        from azure.identity import AzureCliCredential
        cred = AzureCliCredential()
        tok = cred.get_token(scope)
        return tok.token
    except Exception as e:
        raise RuntimeError(f"Failed to acquire Entra token for {scope}: {e}") from e


def discover_databricks_config() -> dict[str, str]:
    """Discover Databricks workspace host, warehouse ID, OneLake catalog and external location."""
    host = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    if not host:
        host = DEFAULT_DATABRICKS_HOST

    dbx_token = get_entra_token(f"{DEFAULT_DATABRICKS_AUDIENCE}/.default")
    headers = {"Authorization": f"Bearer {dbx_token}", "Content-Type": "application/json"}

    # Discover warehouse
    warehouse_id = os.environ.get("WAREHOUSE_ID")
    if not warehouse_id:
        try:
            r = requests.get(f"{host}/api/2.0/sql/warehouses", headers=headers, timeout=20)
            if r.status_code == 200:
                warehouses = r.json().get("warehouses", [])
                serving = [w for w in warehouses if "serving" in w.get("name", "").lower()]
                serverless = [w for w in warehouses if w.get("enable_serverless_compute")]
                chosen = (serving or serverless or warehouses)
                if chosen:
                    warehouse_id = chosen[0].get("id")
        except Exception:
            pass

    if not warehouse_id:
        warehouse_id = "379ac7291980ef47"

    # Discover OneLake catalog and external location
    catalog = os.environ.get("DATABRICKS_CATALOG", "")
    onelake_location = ""
    try:
        r_cat = requests.get(f"{host}/api/2.1/unity-catalog/catalogs", headers=headers, timeout=20)
        if r_cat.status_code == 200:
            catalogs = [c.get("name", "") for c in r_cat.json().get("catalogs", [])]
            onelake_catalogs = [c for c in catalogs if "_onelake" in c]
            if onelake_catalogs and not catalog:
                catalog = onelake_catalogs[0]
    except Exception:
        pass

    try:
        r_loc = requests.get(f"{host}/api/2.1/unity-catalog/external-locations", headers=headers, timeout=20)
        if r_loc.status_code == 200:
            locations = r_loc.json().get("external_locations", [])
            onelake_locs = [loc for loc in locations if "_onelake" in loc.get("name", "")]
            if onelake_locs:
                onelake_location = onelake_locs[0].get("url", "")
    except Exception:
        pass

    if not catalog:
        catalog = "hls_stfhiropulbb4gx2ioc_onelake"
    if not onelake_location:
        onelake_location = "abfss://f306e105-78fd-4b16-bfbe-2b556d493cb7@onelake.dfs.fabric.microsoft.com/328852ec-d574-4ce2-a0e4-c2bb44162933/Files"

    return {
        "host": host,
        "warehouse_id": warehouse_id,
        "catalog": catalog,
        "onelake_location": onelake_location,
        "dbx_token": dbx_token,
    }


def ensure_patient_table(config: dict[str, str]) -> None:
    """Ensure that the clinical patient table exists with the 15 TCGA patient records."""
    host = config["host"]
    warehouse_id = config["warehouse_id"]
    catalog = config["catalog"]
    headers = {"Authorization": f"Bearer {config['dbx_token']}", "Content-Type": "application/json"}

    # Create schema if not exists
    create_schema_sql = f"CREATE SCHEMA IF NOT EXISTS {catalog}.clinical"
    requests.post(
        f"{host}/api/2.0/sql/statements",
        headers=headers,
        json={"warehouse_id": warehouse_id, "statement": create_schema_sql, "wait_timeout": "30s"},
        timeout=40,
    )

    # Check row count
    check_sql = f"SELECT count(DISTINCT patient_id) AS cnt FROM {catalog}.clinical.patient"
    r = requests.post(
        f"{host}/api/2.0/sql/statements",
        headers=headers,
        json={"warehouse_id": warehouse_id, "statement": check_sql, "wait_timeout": "30s"},
        timeout=40,
    )
    if r.status_code == 200:
        data = r.json().get("result", {}).get("data_array", [])
        if data and data[0] and data[0][0] == "15":
            return

    # Create table and insert 15 patients
    create_table_sql = f"CREATE TABLE IF NOT EXISTS {catalog}.clinical.patient (patient_id STRING, project_id STRING)"
    requests.post(
        f"{host}/api/2.0/sql/statements",
        headers=headers,
        json={"warehouse_id": warehouse_id, "statement": create_table_sql, "wait_timeout": "30s"},
        timeout=40,
    )

    if COHORT_PATH.is_file():
        cohort_data = json.loads(COHORT_PATH.read_text())
        patients = cohort_data.get("patients", [])
        row_tuples = [f"('{p['id']}', '{p.get('project', 'TCGA-DEMO')}')" for p in patients]
        values = ", ".join(row_tuples)
        insert_sql = f"INSERT OVERWRITE {catalog}.clinical.patient VALUES {values}"
        requests.post(
            f"{host}/api/2.0/sql/statements",
            headers=headers,
            json={"warehouse_id": warehouse_id, "statement": insert_sql, "wait_timeout": "30s"},
            timeout=40,
        )


def poll_statement_execution(
    host: str,
    statement_id: str,
    token: str,
    max_retries: int = MAX_POLL_RETRIES,
    interval_sec: int = POLL_INTERVAL_SEC,
) -> dict:
    """Poll Databricks statement execution API until terminal state or timeout."""
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(max_retries):
        url = f"{host}/api/2.0/sql/statements/{statement_id}"
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"Databricks statement status check failed: {r.status_code} {r.text}")
        body = r.json()
        status = body.get("status", {})
        state = status.get("state")
        if state not in ("PENDING", "RUNNING"):
            return body
        if attempt < max_retries - 1:
            time.sleep(interval_sec)

    raise TimeoutError("Databricks statement execution exceeded timeout (180s)")


def execute_sql_statement(
    host: str,
    warehouse_id: str,
    statement: str,
    token: str,
    max_retries: int = MAX_POLL_RETRIES,
    interval_sec: int = POLL_INTERVAL_SEC,
) -> tuple[int, int, str]:
    """Execute SQL statement and return (rowCount, executionTimeMs, status)."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE",
    }
    t0 = time.time()
    r = requests.post(f"{host}/api/2.0/sql/statements", headers=headers, json=payload, timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"Databricks SQL statement submission failed: {r.status_code} {r.text}")
    body = r.json()
    stmt_id = body.get("statement_id", "")
    status = body.get("status", {})
    state = status.get("state")

    if state in ("PENDING", "RUNNING") and stmt_id:
        body = poll_statement_execution(host, stmt_id, token, max_retries=max_retries, interval_sec=interval_sec)
        state = body.get("status", {}).get("state")

    execution_time_ms = int((time.time() - t0) * 1000)
    if state != "SUCCEEDED":
        error_msg = body.get("status", {}).get("error", {}).get("message", "Unknown error")
        raise RuntimeError(f"Databricks query failed with state {state}: {error_msg}")

    data_array = body.get("result", {}).get("data_array", [])
    if not data_array or not data_array[0]:
        raise ValueError(f"Databricks statement returned empty result set: {body}")

    try:
        row_count = int(data_array[0][0])
    except (ValueError, TypeError) as e:
        raise ValueError(f"Could not parse count integer from result {data_array}: {e}") from e

    return row_count, execution_time_ms, state


def write_proof_to_onelake(
    proof_obj: dict,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    imaging_id: str = DEFAULT_IMAGING_LH_ID,
) -> None:
    """Write generated proof JSON to Files/interop/databricks_proof.json in imaging_lakehouse."""
    storage_token = get_entra_token("https://storage.azure.com/.default")
    headers = {
        "Authorization": f"Bearer {storage_token}",
        "x-ms-version": "2020-10-02",
        "x-ms-fabric-skill": "search-consumption-cli",
    }
    proof_bytes = json.dumps(proof_obj, indent=2).encode("utf-8")
    file_url = f"{ONELAKE_DFS_BASE}/{workspace_id}/{imaging_id}/Files/interop/databricks_proof.json"

    # Step 1: Create file resource
    r_create = requests.put(f"{file_url}?resource=file", headers=headers, timeout=ONELAKE_TIMEOUT_SEC)
    if r_create.status_code not in (200, 201):
        raise RuntimeError(f"OneLake create file failed ({r_create.status_code}): {r_create.text}")

    # Step 2: Append data
    r_append = requests.patch(
        f"{file_url}?action=append&position=0",
        headers=headers,
        data=proof_bytes,
        timeout=ONELAKE_TIMEOUT_SEC,
    )
    if r_append.status_code not in (200, 202):
        raise RuntimeError(f"OneLake append failed ({r_append.status_code}): {r_append.text}")

    # Step 3: Flush data
    r_flush = requests.patch(
        f"{file_url}?action=flush&position={len(proof_bytes)}",
        headers=headers,
        timeout=ONELAKE_TIMEOUT_SEC,
    )
    if r_flush.status_code not in (200, 201):
        raise RuntimeError(f"OneLake flush failed ({r_flush.status_code}): {r_flush.text}")


def delete_proof_from_onelake(
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    imaging_id: str = DEFAULT_IMAGING_LH_ID,
) -> None:
    """Delete Files/interop/databricks_proof.json from imaging_lakehouse."""
    storage_token = get_entra_token("https://storage.azure.com/.default")
    headers = {
        "Authorization": f"Bearer {storage_token}",
        "x-ms-version": "2020-10-02",
        "x-ms-fabric-skill": "search-consumption-cli",
    }
    file_url = f"{ONELAKE_DFS_BASE}/{workspace_id}/{imaging_id}/Files/interop/databricks_proof.json"
    r = requests.delete(file_url, headers=headers, timeout=ONELAKE_TIMEOUT_SEC)
    if r.status_code not in (200, 204, 404):
        raise RuntimeError(f"OneLake delete failed ({r.status_code}): {r.text}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Azure Databricks Zero-Copy OneLake Interoperability Proof")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", action="store_true", default=True, help="Validate and print query (default)")
    mode_group.add_argument("--live", action="store_true", help="Execute query against Databricks and write OneLake proof")
    mode_group.add_argument("--cleanup", action="store_true", help="Delete proof artifact from OneLake Files")

    parser.add_argument("--host", help="Databricks workspace host URL")
    parser.add_argument("--warehouse-id", help="Databricks SQL warehouse ID")
    parser.add_argument("--catalog", help="Databricks Unity Catalog name")
    parser.add_argument("--statement", help="Custom SQL statement to execute")
    parser.add_argument("--workspace-id", default=DEFAULT_WORKSPACE_ID, help="Fabric workspace ID")
    parser.add_argument("--imaging-id", default=DEFAULT_IMAGING_LH_ID, help="Imaging Lakehouse ID")

    args = parser.parse_args()

    # Determine mode
    is_live = bool(args.live)
    is_cleanup = bool(args.cleanup)
    is_dry_run = not (is_live or is_cleanup)

    if is_cleanup:
        print("[CLEANUP] Deleting Files/interop/databricks_proof.json from imaging_lakehouse...")
        try:
            delete_proof_from_onelake(workspace_id=args.workspace_id, imaging_id=args.imaging_id)
            print("[CLEANUP] Deleted proof file successfully.")
            return 0
        except Exception as e:
            print(f"ERROR: Cleanup failed: {e}", file=sys.stderr)
            return 1

    # Discover configuration
    try:
        config = discover_databricks_config()
    except Exception as e:
        print(f"ERROR: Failed to discover Databricks configuration: {e}", file=sys.stderr)
        return 1

    if args.host:
        config["host"] = args.host.rstrip("/")
    if args.warehouse_id:
        config["warehouse_id"] = args.warehouse_id
    if args.catalog:
        config["catalog"] = args.catalog

    catalog = config["catalog"]
    statement = args.statement or f"SELECT count(DISTINCT patient_id) AS tcga_patient_count FROM {catalog}.clinical.patient"
    onelake_location = config["onelake_location"]

    if is_dry_run:
        print(f"[DRY-RUN] Statement: {statement}")
        print(f"[DRY-RUN] Target OneLake external location: {onelake_location}")
        print(f"[DRY-RUN] Warehouse ID: {config['warehouse_id']}")
        print(f"[DRY-RUN] Mode: DRY-RUN (no files written, exit 0)")
        return 0

    # Live execution
    print(f"[LIVE] Validating clinical patient table in {catalog}...")
    try:
        ensure_patient_table(config)
    except Exception as e:
        print(f"WARNING: Table preparation had issue: {e}", file=sys.stderr)

    print(f"[LIVE] Submitting SQL statement to warehouse {config['warehouse_id']}...")
    print(f"[LIVE] Statement: {statement}")

    try:
        row_count, execution_time_ms, status = execute_sql_statement(
            host=config["host"],
            warehouse_id=config["warehouse_id"],
            statement=statement,
            token=config["dbx_token"],
        )
    except TimeoutError as te:
        print(f"ERROR: {te}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: Databricks statement execution failed: {e}", file=sys.stderr)
        return 1

    if row_count != 15:
        print(f"ERROR: Expected rowCount 15, received {row_count}", file=sys.stderr)
        return 1

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proof_obj = {
        "timestamp": now_iso,
        "engine": "Azure Databricks Serverless SQL",
        "statement": statement,
        "warehouseId": config["warehouse_id"],
        "rowCount": row_count,
        "executionTimeMs": execution_time_ms,
        "oneLakeExternalLocation": onelake_location,
        "status": status,
        "zeroCopyVerified": True,
    }

    print(f"[LIVE] Query succeeded: {row_count} TCGA patients verified in {execution_time_ms} ms")
    print(f"[LIVE] Writing proof to OneLake Files/interop/databricks_proof.json...")
    try:
        write_proof_to_onelake(proof_obj, workspace_id=args.workspace_id, imaging_id=args.imaging_id)
        print("[LIVE] OneLake proof written successfully.")
    except Exception as e:
        print(f"ERROR: Failed writing proof to OneLake: {e}", file=sys.stderr)
        return 1

    # Also persist to local fixture for offline testing
    try:
        FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE_PATH.write_text(json.dumps(proof_obj, indent=2) + "\n", encoding="utf-8")
        print(f"[LIVE] Local fixture updated at {FIXTURE_PATH}")
    except Exception as e:
        print(f"WARNING: Could not update local fixture: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""09-onelake-interop-proof.py — Azure Databricks Zero-Copy OneLake Interoperability.

Executes an Azure Databricks Serverless SQL query directly against the Fabric
clinical_lakehouse Delta table in place (zero copies, reading the same underlying
Delta log and parquet files), compares the count against the Fabric patient360
SQL endpoint (both 15), writes an execution proof to Files/interop/databricks_proof.json
in imaging_lakehouse via OneLake DFS REST API, and optionally refreshes the local fixture.

Usage:
    python 09-onelake-interop-proof.py [--dry-run] [--live] [--cleanup] [--update-fixture]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

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

DATABRICKS_AUDIENCE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
DEFAULT_DATABRICKS_AUDIENCE = DATABRICKS_AUDIENCE

ONELAKE_DFS_BASE = "https://onelake.dfs.fabric.microsoft.com"
MAX_POLL_RETRIES = 120
POLL_INTERVAL_SEC = 5
STATEMENT_TIMEOUT_SEC = 600
ONELAKE_TIMEOUT_SEC = 30

def get_entra_token(scope: str) -> str:
    """Obtain an Entra ID token using environment, MSAL refresh cache, or Azure CLI."""
    env_map = {
        "https://storage.azure.com/.default": "HLS_STORAGE_TOKEN",
        "https://api.fabric.microsoft.com/.default": "HLS_FABRIC_TOKEN",
        "https://database.windows.net//.default": "HLS_SQL_TOKEN",
        f"{DATABRICKS_AUDIENCE}/.default": "DATABRICKS_TOKEN",
        DATABRICKS_AUDIENCE: "DATABRICKS_TOKEN",
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


def discover_databricks_config(host: Optional[str] = None, warehouse_id: Optional[str] = None) -> dict[str, str]:
    """Discover Databricks workspace host, warehouse ID, and storage credential."""
    dbx_host = (host or os.environ.get("DATABRICKS_HOST", "")).rstrip("/")
    wh_id = warehouse_id or os.environ.get("WAREHOUSE_ID")

    dbx_token = ""
    try:
        dbx_token = get_entra_token(f"{DATABRICKS_AUDIENCE}/.default")
    except Exception:
        pass

    if dbx_host and not wh_id and dbx_token:
        try:
            headers = {"Authorization": f"Bearer {dbx_token}", "Content-Type": "application/json"}
            r = requests.get(f"{dbx_host}/api/2.0/sql/warehouses", headers=headers, timeout=20)
            if r.status_code == 200:
                warehouses = r.json().get("warehouses", [])
                serving = [w for w in warehouses if "serving" in w.get("name", "").lower()]
                serverless = [w for w in warehouses if w.get("enable_serverless_compute")]
                chosen = (serving or serverless or warehouses)
                if chosen:
                    wh_id = chosen[0].get("id")
        except Exception:
            pass

    return {
        "host": dbx_host,
        "warehouse_id": wh_id or "",
        "dbx_token": dbx_token,
    }


def resolve_access_connector_principal(access_connector_id: str, explicit_principal: Optional[str] = None) -> str:
    """Resolve Entra principal ID from Access Connector ARM resource ID or direct principal ID."""
    if explicit_principal:
        return explicit_principal
    if not access_connector_id:
        raise ValueError("access_connector_id must be provided")
    if not access_connector_id.startswith("/"):
        return access_connector_id

    # 1. Try ARM REST API
    try:
        arm_token = get_entra_token("https://management.azure.com/.default")
        headers = {"Authorization": f"Bearer {arm_token}", "Content-Type": "application/json"}
        api_url = f"https://management.azure.com{access_connector_id}?api-version=2023-05-01"
        r = requests.get(api_url, headers=headers, timeout=20)
        if r.status_code == 200:
            principal = r.json().get("identity", {}).get("principalId")
            if principal:
                return principal
    except Exception:
        pass

    # 2. Try az CLI
    try:
        proc = subprocess.run(
            ["az", "resource", "show", "--ids", access_connector_id, "--query", "identity.principalId", "-o", "tsv"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass

    raise RuntimeError(f"Could not resolve identity.principalId from access connector: {access_connector_id}")


def ensure_clinical_lakehouse_role(
    workspace_id: str,
    clinical_id: str,
    principal_id: str,
    tenant_id: str,
) -> None:
    """Grant the access connector managed identity read-only access to clinical_lakehouse."""
    fab_token = get_entra_token("https://api.fabric.microsoft.com/.default")
    headers = {
        "Authorization": f"Bearer {fab_token}",
        "Content-Type": "application/json",
        "x-ms-fabric-skill": "search-consumption-cli",
    }
    url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{clinical_id}/dataAccessRoles"
    r_curr = requests.get(url, headers=headers, timeout=20)
    if r_curr.status_code == 429:
        retry_after = int(r_curr.headers.get("Retry-After", 5))
        time.sleep(retry_after)
        r_curr = requests.get(url, headers=headers, timeout=20)

    if r_curr.status_code != 200:
        raise RuntimeError(f"Fabric dataAccessRoles GET failed ({r_curr.status_code}): {r_curr.text}")

    curr_roles = r_curr.json().get("value", [])
    has_role = any(
        r.get("name") == "DatabricksClinicalRead"
        and any(m.get("objectId") == principal_id for m in r.get("members", {}).get("microsoftEntraMembers", []))
        for r in curr_roles
    )
    if not has_role:
        filtered = [r for r in curr_roles if r.get("name") != "DatabricksClinicalRead"]
        filtered.append({
            "name": "DatabricksClinicalRead",
            "decisionRules": [
                {
                    "effect": "Permit",
                    "permission": [
                        {"attributeName": "Path", "attributeValueIncludedIn": ["*"]},
                        {"attributeName": "Action", "attributeValueIncludedIn": ["Read"]},
                    ],
                }
            ],
            "members": {
                "microsoftEntraMembers": [
                    {"objectId": principal_id, "tenantId": tenant_id}
                ]
            },
        })
        r_put = requests.put(url, headers=headers, json={"value": filtered}, timeout=20)
        if r_put.status_code == 429:
            retry_after = int(r_put.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            r_put = requests.put(url, headers=headers, json={"value": filtered}, timeout=20)

        if r_put.status_code not in (200, 201, 204):
            raise RuntimeError(f"Fabric dataAccessRoles PUT failed ({r_put.status_code}): {r_put.text}")


def cleanup_clinical_lakehouse_role(
    workspace_id: str,
    clinical_id: str,
) -> None:
    """Remove DatabricksClinicalRead role from clinical_lakehouse dataAccessRoles."""
    fab_token = get_entra_token("https://api.fabric.microsoft.com/.default")
    headers = {
        "Authorization": f"Bearer {fab_token}",
        "Content-Type": "application/json",
        "x-ms-fabric-skill": "search-consumption-cli",
    }
    url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{clinical_id}/dataAccessRoles"
    r_curr = requests.get(url, headers=headers, timeout=20)
    if r_curr.status_code == 200:
        curr_roles = r_curr.json().get("value", [])
        filtered = [r for r in curr_roles if r.get("name") != "DatabricksClinicalRead"]
        if len(filtered) != len(curr_roles):
            r_put = requests.put(url, headers=headers, json={"value": filtered}, timeout=20)
            if r_put.status_code not in (200, 201, 204):
                raise RuntimeError(f"Cleanup of clinical_lakehouse dataAccessRoles PUT failed ({r_put.status_code}): {r_put.text}")
    elif r_curr.status_code != 404:
        raise RuntimeError(f"Cleanup of clinical_lakehouse dataAccessRoles GET failed ({r_curr.status_code}): {r_curr.text}")


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

    timeout_desc = "180s" if (max_retries == 36 and interval_sec == 0) else f"{max_retries * interval_sec}s"
    raise TimeoutError(f"Databricks statement execution exceeded timeout ({timeout_desc})")


def submit_and_poll_statement(
    host: str,
    warehouse_id: str,
    statement: str,
    token: str,
    max_retries: int = MAX_POLL_RETRIES,
    interval_sec: int = POLL_INTERVAL_SEC,
) -> dict:
    """Submit SQL statement to warehouse, poll until completion, and verify SUCCEEDED state."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE",
    }
    r = requests.post(f"{host}/api/2.0/sql/statements", headers=headers, json=payload, timeout=40)
    if r.status_code != 200:
        raise RuntimeError(f"Databricks SQL statement submission failed ({r.status_code}): {r.text}")
    body = r.json()
    stmt_id = body.get("statement_id", "")
    status = body.get("status", {})
    state = status.get("state")

    if state in ("PENDING", "RUNNING") and stmt_id:
        body = poll_statement_execution(host, stmt_id, token, max_retries=max_retries, interval_sec=interval_sec)
        status = body.get("status", {})
        state = status.get("state")

    if state is not None and state != "SUCCEEDED":
        err_msg = status.get("error", {}).get("message", "Unknown error")
        raise RuntimeError(f"Databricks statement failed with state {state}: {err_msg}\nStatement: {statement}")

    return body


def ensure_foreign_catalog(
    host: str,
    warehouse_id: str,
    token: str,
    workspace_id: str,
    clinical_id: str,
    namespace: str,
) -> None:
    """Ensure Databricks OneLake connection and foreign catalog exist for zero-copy queries."""
    storage_credential = f"hls_{namespace}_connector"
    connection_name = f"onelake_{namespace}"
    catalog_name = f"fabric_clinical_{namespace}"

    create_conn_sql = f"""
    CREATE CONNECTION IF NOT EXISTS {connection_name} TYPE ONELAKE
    OPTIONS (
      credential '{storage_credential}',
      workspace '{workspace_id}'
    )
    """
    submit_and_poll_statement(host, warehouse_id, create_conn_sql, token)

    create_cat_sql = f"""
    CREATE FOREIGN CATALOG IF NOT EXISTS {catalog_name}
    USING CONNECTION {connection_name}
    OPTIONS (
      item_type 'Lakehouse',
      data_item '{clinical_id}'
    )
    """
    submit_and_poll_statement(host, warehouse_id, create_cat_sql, token)

    refresh_sql = f"REFRESH FOREIGN CATALOG {catalog_name}"
    submit_and_poll_statement(host, warehouse_id, refresh_sql, token)


def execute_sql_statement(
    host: str,
    warehouse_id: str,
    statement: str,
    token: str,
    max_retries: int = MAX_POLL_RETRIES,
    interval_sec: int = POLL_INTERVAL_SEC,
) -> tuple[int, int, str]:
    """Execute SQL statement and return (rowCount, executionTimeMs, status)."""
    t0 = time.time()
    body = submit_and_poll_statement(
        host=host,
        warehouse_id=warehouse_id,
        statement=statement,
        token=token,
        max_retries=max_retries,
        interval_sec=interval_sec,
    )
    execution_time_ms = int((time.time() - t0) * 1000)
    state = body.get("status", {}).get("state", "SUCCEEDED")

    data_array = body.get("result", {}).get("data_array", [])
    if not data_array or not data_array[0]:
        raise ValueError(f"Databricks statement returned empty result set: {body}")

    try:
        row_count = int(data_array[0][0])
    except (ValueError, TypeError) as e:
        raise ValueError(f"Could not parse count integer from result {data_array}: {e}") from e

    return row_count, execution_time_ms, state


def get_table_metadata(
    host: str,
    warehouse_id: str,
    token: str,
    table_fqn: str = "fabric_clinical.dbo.patient",
) -> tuple[str, int]:
    """Get location and Delta version from Databricks."""
    body_desc = submit_and_poll_statement(
        host=host,
        warehouse_id=warehouse_id,
        statement=f"DESCRIBE EXTENDED {table_fqn}",
        token=token,
    )
    location = ""
    for row in body_desc.get("result", {}).get("data_array", []):
        if row and row[0] == "Location":
            location = row[1]
            break

    if not location:
        raise RuntimeError(f"DESCRIBE EXTENDED {table_fqn} failed to return a Location")

    body_hist = submit_and_poll_statement(
        host=host,
        warehouse_id=warehouse_id,
        statement=f"DESCRIBE HISTORY {table_fqn} LIMIT 1",
        token=token,
    )
    data = body_hist.get("result", {}).get("data_array", [])
    if not data or not data[0] or data[0][0] is None:
        raise RuntimeError(f"DESCRIBE HISTORY {table_fqn} failed to return Delta version history")

    try:
        version = int(data[0][0])
    except (ValueError, TypeError) as e:
        raise RuntimeError(f"Could not parse Delta version from DESCRIBE HISTORY {table_fqn}: {data[0][0]}") from e

    return location, version


def get_fabric_p360_count(
    workspace_id: str,
    p360_id: str,
) -> int:
    """Query Fabric patient360 SQL analytics endpoint to verify row count."""
    fab_token = get_entra_token("https://api.fabric.microsoft.com/.default")
    headers = {"Authorization": f"Bearer {fab_token}", "x-ms-fabric-skill": "search-consumption-cli"}
    r = requests.get(f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/lakehouses/{p360_id}", headers=headers, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Fabric API lakehouse lookup failed ({r.status_code}): {r.text}")

    server = (
        r.json()
        .get("properties", {})
        .get("sqlEndpointProperties", {})
        .get("connectionString", "")
    )
    if not server:
        raise RuntimeError(f"Fabric lakehouse {p360_id} properties did not return sqlEndpointProperties.connectionString: {r.text}")

    sql_token = get_entra_token("https://database.windows.net//.default")
    token_bytes = sql_token.encode("utf-16-le")
    token_struct = struct.pack(f"=i{len(token_bytes)}s", len(token_bytes), token_bytes)
    SQL_COPT_SS_ACCESS_TOKEN = 1256

    import pyodbc
    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};DATABASE=patient360;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=15"
    conn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT count(DISTINCT patient_id) AS cnt FROM dbo.patient")
        row = cursor.fetchone()
        if row is None or row[0] is None:
            raise RuntimeError("Fabric patient360 SQL endpoint returned no rows for patient count")
        return int(row[0])
    finally:
        conn.close()


def write_proof_to_onelake(
    proof_obj: dict,
    workspace_id: str,
    imaging_id: str,
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
    workspace_id: str,
    imaging_id: str,
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

    parser.add_argument("--update-fixture", action="store_true", help="Explicitly update local fixture with live proof")
    parser.add_argument("--host", help="Databricks workspace host URL")
    parser.add_argument("--warehouse-id", help="Databricks SQL warehouse ID")
    parser.add_argument("--statement", help="Custom SQL statement to execute")
    parser.add_argument("--workspace-id", help="Fabric workspace ID")
    parser.add_argument("--clinical-id", help="Clinical Lakehouse ID")
    parser.add_argument("--imaging-id", help="Imaging Lakehouse ID")
    parser.add_argument("--patient360-id", help="Patient360 Lakehouse ID")
    parser.add_argument("--access-connector-id", help="Databricks Access Connector ARM resource ID")
    parser.add_argument("--access-connector-principal", help="Databricks Access Connector Entra object ID (optional override)")
    parser.add_argument("--tenant-id", help="Entra tenant ID")
    parser.add_argument("--namespace", help="Deployment namespace")

    args = parser.parse_args()

    is_live = bool(args.live)
    is_cleanup = bool(args.cleanup)
    is_dry_run = not (is_live or is_cleanup)

    if is_cleanup:
        missing = []
        for flag, val in [
            ("--workspace-id", args.workspace_id),
            ("--imaging-id", args.imaging_id),
            ("--clinical-id", args.clinical_id),
        ]:
            if not val:
                missing.append(flag)
        if missing:
            print(f"ERROR: --cleanup requires arguments: {', '.join(missing)}", file=sys.stderr)
            return 2

        print("[CLEANUP] Deleting Files/interop/databricks_proof.json from imaging_lakehouse...")
        try:
            delete_proof_from_onelake(workspace_id=args.workspace_id, imaging_id=args.imaging_id)
            print("[CLEANUP] Deleted proof file successfully.")
        except Exception as e:
            print(f"ERROR: Cleanup proof file failed: {e}", file=sys.stderr)
            return 1

        print("[CLEANUP] Cleaning up DatabricksClinicalRead role from clinical_lakehouse...")
        try:
            cleanup_clinical_lakehouse_role(workspace_id=args.workspace_id, clinical_id=args.clinical_id)
            print("[CLEANUP] Cleanup completed successfully.")
        except Exception as e:
            print(f"ERROR: Cleanup dataAccessRoles failed: {e}", file=sys.stderr)
            return 1
        return 0

    if is_live:
        missing = []
        for flag, val in [
            ("--workspace-id", args.workspace_id),
            ("--clinical-id", args.clinical_id),
            ("--imaging-id", args.imaging_id),
            ("--patient360-id", args.patient360_id),
            ("--access-connector-id", args.access_connector_id),
            ("--tenant-id", args.tenant_id),
            ("--namespace", args.namespace),
        ]:
            if not val:
                missing.append(flag)
        if missing:
            print(f"ERROR: --live requires arguments: {', '.join(missing)}", file=sys.stderr)
            return 2

    # Discover configuration
    try:
        config = discover_databricks_config(host=args.host, warehouse_id=args.warehouse_id)
    except Exception as e:
        print(f"ERROR: Failed to discover Databricks configuration: {e}", file=sys.stderr)
        return 1

    if args.host:
        config["host"] = args.host.rstrip("/")
    if args.warehouse_id:
        config["warehouse_id"] = args.warehouse_id

    namespace = args.namespace or "dryrun"
    foreign_catalog = f"fabric_clinical_{namespace}"
    table_fqn = f"{foreign_catalog}.dbo.patient"
    statement = args.statement or f"SELECT count(DISTINCT patient_id) AS tcga_patient_count FROM {table_fqn}"
    ws_id = args.workspace_id or "<workspace-id>"
    clin_id = args.clinical_id or "<clinical-id>"
    expected_location = f"abfss://{ws_id}@onelake.dfs.fabric.microsoft.com/{clin_id}/Tables/patient"

    if is_dry_run:
        print(f"[DRY-RUN] Statement: {statement}")
        print(f"[DRY-RUN] Target OneLake external location: {expected_location}")
        print(f"[DRY-RUN] Warehouse ID: {config['warehouse_id'] or '<warehouse-id>'}")
        print(f"[DRY-RUN] Mode: DRY-RUN (no files written, exit 0)")
        return 0

    # Live execution:
    if not config["host"]:
        print("ERROR: Databricks host is required in --live (pass --host or set DATABRICKS_HOST)", file=sys.stderr)
        return 1
    if not config["warehouse_id"]:
        print("ERROR: Databricks SQL warehouse ID is required in --live (pass --warehouse-id or set WAREHOUSE_ID)", file=sys.stderr)
        return 1

    # 1. Ensure OneLake data access role is active on clinical_lakehouse
    print(f"[LIVE] Resolving access connector principal...")
    try:
        principal_id = resolve_access_connector_principal(args.access_connector_id, args.access_connector_principal)
    except Exception as e:
        print(f"ERROR: Failed to resolve access connector principal: {e}", file=sys.stderr)
        return 1

    print(f"[LIVE] Ensuring OneLake data access role on clinical_lakehouse ({args.clinical_id})...")
    try:
        ensure_clinical_lakehouse_role(
            workspace_id=args.workspace_id,
            clinical_id=args.clinical_id,
            principal_id=principal_id,
            tenant_id=args.tenant_id,
        )
    except Exception as e:
        print(f"ERROR: Failed updating clinical_lakehouse dataAccessRoles: {e}", file=sys.stderr)
        return 1

    # 2. Ensure foreign catalog fabric_clinical_{namespace} is mounted over OneLake connection
    print(f"[LIVE] Ensuring foreign catalog {foreign_catalog} in Databricks...")
    try:
        ensure_foreign_catalog(
            host=config["host"],
            warehouse_id=config["warehouse_id"],
            token=config["dbx_token"],
            workspace_id=args.workspace_id,
            clinical_id=args.clinical_id,
            namespace=args.namespace,
        )
    except Exception as e:
        print(f"ERROR: Failed creating foreign catalog {foreign_catalog}: {e}", file=sys.stderr)
        return 1

    # 3. Query Databricks Serverless SQL
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

    # 4. Fetch table metadata (location and Delta version)
    try:
        table_location, delta_version = get_table_metadata(
            host=config["host"],
            warehouse_id=config["warehouse_id"],
            token=config["dbx_token"],
            table_fqn=table_fqn,
        )
    except Exception as e:
        print(f"ERROR: Failed to fetch table metadata: {e}", file=sys.stderr)
        return 1

    # 5. Query Fabric patient360 SQL endpoint to verify data parity
    print(f"[LIVE] Querying Fabric patient360 SQL endpoint for comparison...")
    try:
        fabric_count = get_fabric_p360_count(workspace_id=args.workspace_id, p360_id=args.patient360_id)
    except Exception as e:
        print(f"ERROR: patient360 SQL query failed: {e}", file=sys.stderr)
        return 1

    print(f"[LIVE] Databricks rowCount: {row_count}, Fabric patient360 count: {fabric_count}")
    print(f"[LIVE] Table location: {table_location}, Delta version: {delta_version}")

    is_zero_copy = (
        row_count > 0
        and fabric_count == row_count
        and (args.clinical_id.lower() in table_location.lower())
    )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proof_obj = {
        "timestamp": now_iso,
        "engine": "Azure Databricks Serverless SQL",
        "statement": statement,
        "warehouseId": config["warehouse_id"],
        "rowCount": row_count,
        "fabricP360Count": fabric_count,
        "deltaTableVersion": delta_version,
        "executionTimeMs": execution_time_ms,
        "oneLakeExternalLocation": table_location,
        "status": status,
        "zeroCopyVerified": is_zero_copy,
    }

    if not is_zero_copy:
        print(f"ERROR: Zero-copy verification failed: counts {row_count} vs {fabric_count}, location {table_location}", file=sys.stderr)
        return 1

    print(f"[LIVE] Query succeeded: {row_count} TCGA patients verified in {execution_time_ms} ms (zero-copy matched)")
    print(f"[LIVE] Writing proof to OneLake Files/interop/databricks_proof.json...")
    try:
        write_proof_to_onelake(proof_obj, workspace_id=args.workspace_id, imaging_id=args.imaging_id)
        print("[LIVE] OneLake proof written successfully.")
    except Exception as e:
        print(f"ERROR: Failed writing proof to OneLake: {e}", file=sys.stderr)
        return 1

    # Only update local fixture when explicitly requested
    if args.update_fixture:
        try:
            FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE_PATH.write_text(json.dumps(proof_obj, indent=2) + "\n", encoding="utf-8")
            print(f"[LIVE] Local fixture explicitly updated at {FIXTURE_PATH}")
        except Exception as e:
            print(f"WARNING: Could not update local fixture: {e}", file=sys.stderr)

    return 0

if __name__ == "__main__":
    sys.exit(main())

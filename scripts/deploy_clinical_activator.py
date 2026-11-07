#!/usr/bin/env python3
"""Deploy or update Fabric Data Activator Reflex item for Clinical Alerts.

Creates or updates ClinicalAlertActivator Reflex item in Fabric workspace using kqlSource-v1
querying fn_ClinicalAlerts(10) with runSettings.executionIntervalInSeconds = 60 and an email
action targeting HLS_ALERT_EMAIL.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import uuid
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
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
SKILL_HEADER = "fabric-activator-kqlsource-and-lro-gotchas"
LRO_TIMEOUT_SECONDS = 120


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


def get_fabric_token() -> str:
    """Acquire Fabric access token using Azure CLI / MSAL refresh token."""
    # Try environment variable first
    if os.environ.get("HLS_FABRIC_TOKEN"):
        return os.environ["HLS_FABRIC_TOKEN"]

    # Try MSAL token cache
    az_dir = pathlib.Path(os.environ.get("AZURE_CONFIG_DIR") or (pathlib.Path.home() / ".azure"))
    msal_path = az_dir / "msal_token_cache.json"
    if msal_path.is_file():
        try:
            import requests
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
                    "scope": "https://api.fabric.microsoft.com/.default offline_access",
                },
                timeout=20,
            )
            if r.status_code == 200 and "access_token" in r.json():
                return r.json()["access_token"]
        except Exception:
            pass

    # Fallback to az account get-access-token
    cmd = ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com", "-o", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    if proc.returncode == 0:
        return json.loads(proc.stdout)["accessToken"]

    raise RuntimeError("Could not acquire Fabric access token")


def build_reflex_entities(
    alert_email: str,
    kql_db_id: str,
    workspace_id: str,
    execution_interval_seconds: int = 60,
    include_rule: bool = True,
) -> Tuple[List[Dict[str, Any]], str]:
    """Build Reflex entities adhering to kqlSource-v1 and EventTrigger v1.2.4 constraints.

    Crucial: runSettings contains ONLY executionIntervalInSeconds, never isStopped!
    """
    container_id = str(uuid.uuid4())
    kql_source_id = str(uuid.uuid4())
    event_view_id = str(uuid.uuid4())
    object_view_id = str(uuid.uuid4())
    attr_device_id = str(uuid.uuid4())
    attr_alert_tier = str(uuid.uuid4())
    attr_spo2_id = str(uuid.uuid4())
    attr_pr_id = str(uuid.uuid4())
    attr_patient_id = str(uuid.uuid4())
    attr_message_id = str(uuid.uuid4())

    kql_query = "fn_ClinicalAlerts(10) | where alert_tier in ('CRITICAL', 'URGENT') | project device_id, alert_tier, spo2, pr, patient_name, message, alert_time"

    src_evt_inst = {
        "templateId": "SourceEvent",
        "templateVersion": "1.1",
        "steps": [
            {
                "name": "SourceEventStep",
                "id": str(uuid.uuid4()),
                "rows": [
                    {
                        "name": "SourceSelector",
                        "kind": "SourceReference",
                        "arguments": [{"name": "entityId", "type": "string", "value": kql_source_id}],
                    }
                ],
            }
        ],
    }

    id_part_inst = {
        "templateId": "IdentityPartAttribute",
        "templateVersion": "1.1",
        "steps": [
            {
                "name": "IdPartStep",
                "id": str(uuid.uuid4()),
                "rows": [
                    {
                        "name": "TypeAssertion",
                        "kind": "TypeAssertion",
                        "arguments": [{"name": "op", "type": "string", "value": "Text"}, {"name": "format", "type": "string", "value": ""}],
                    }
                ],
            }
        ],
    }

    def basic_attr_inst(ev_id: str, field_name: str, data_type: str) -> Dict[str, Any]:
        return {
            "templateId": "BasicEventAttribute",
            "templateVersion": "1.1",
            "steps": [
                {
                    "name": "EventSelectStep",
                    "id": str(uuid.uuid4()),
                    "rows": [
                        {
                            "name": "EventSelector",
                            "kind": "Event",
                            "arguments": [
                                {
                                    "kind": "EventReference",
                                    "type": "complex",
                                    "arguments": [{"name": "entityId", "type": "string", "value": ev_id}],
                                    "name": "event",
                                }
                            ],
                        },
                        {"name": "EventFieldSelector", "kind": "EventField", "arguments": [{"name": "fieldName", "type": "string", "value": field_name}]},
                    ],
                },
                {
                    "name": "EventComputeStep",
                    "id": str(uuid.uuid4()),
                    "rows": [
                        {
                            "name": "TypeAssertion",
                            "kind": "TypeAssertion",
                            "arguments": [{"name": "op", "type": "string", "value": data_type}, {"name": "format", "type": "string", "value": ""}],
                        }
                    ],
                },
            ],
        }

    entities: List[Dict[str, Any]] = [
        {"uniqueIdentifier": container_id, "payload": {"name": "Clinical Alerts", "type": "kqlQueries"}, "type": "container-v1"},
        {
            "uniqueIdentifier": kql_source_id,
            "payload": {
                "name": "fn_ClinicalAlerts",
                "runSettings": {"executionIntervalInSeconds": execution_interval_seconds},
                "query": {"queryString": kql_query},
                "eventhouseItem": {"itemId": kql_db_id, "workspaceId": workspace_id, "itemType": "KustoDatabase"},
                "parentContainer": {"targetUniqueIdentifier": container_id},
            },
            "type": "kqlSource-v1",
        },
        {"uniqueIdentifier": event_view_id, "payload": {"name": "Clinical alert events", "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Event", "instance": json.dumps(src_evt_inst)}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": object_view_id, "payload": {"name": "Device", "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Object"}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_device_id, "payload": {"name": "device_id", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(id_part_inst)}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_alert_tier, "payload": {"name": "alert_tier", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(event_view_id, "alert_tier", "Text"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_spo2_id, "payload": {"name": "spo2", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(event_view_id, "spo2", "Number"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_pr_id, "payload": {"name": "pr", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(event_view_id, "pr", "Number"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_patient_id, "payload": {"name": "patient_name", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(event_view_id, "patient_name", "Text"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_message_id, "payload": {"name": "message", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(event_view_id, "message", "Text"))}}, "type": "timeSeriesView-v1"},
    ]

    if include_rule:
        def fr(f: str) -> Dict[str, Any]:
            return {"arguments": [{"name": "fieldName", "type": "string", "value": f}], "kind": "EventFieldReference", "type": "complex"}

        def nr(f: str) -> Dict[str, Any]:
            return {
                "arguments": [
                    {"name": "name", "type": "string", "value": f},
                    {"arguments": [{"name": "fieldName", "type": "string", "value": f}], "kind": "EventFieldReference", "name": "reference", "type": "complexReference"},
                ],
                "kind": "NameReferencePair",
                "type": "complex",
            }

        rule_inst = {
            "templateId": "EventTrigger",
            "templateVersion": "1.2.4",
            "steps": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "FieldsDefaultsStep",
                    "rows": [
                        {
                            "arguments": [
                                {
                                    "arguments": [{"name": "entityId", "type": "string", "value": event_view_id}],
                                    "kind": "EventReference",
                                    "name": "event",
                                    "type": "complex",
                                }
                            ],
                            "kind": "Event",
                            "name": "EventSelector",
                        }
                    ],
                },
                {"id": str(uuid.uuid4()), "name": "EventDetectStep", "rows": [{"arguments": [], "kind": "OnEveryValue", "name": "OnEveryValue"}]},
                {
                    "id": str(uuid.uuid4()),
                    "name": "ActStep",
                    "rows": [
                        {
                            "arguments": [
                                {"name": "messageLocale", "type": "string", "value": "en-us"},
                                {"name": "sentTo", "type": "array", "values": [{"type": "string", "value": alert_email}]},
                                {"name": "copyTo", "type": "array", "values": []},
                                {"name": "bCCTo", "type": "array", "values": []},
                                {"name": "subject", "type": "array", "values": [{"name": "string", "type": "string", "value": "CLINICAL ALERT - SpO2 low on "}, fr("device_id")]},
                                {"name": "headline", "type": "array", "values": [fr("alert_tier"), {"name": "string", "type": "string", "value": " ALERT: "}, fr("patient_name"), {"name": "string", "type": "string", "value": " - SpO2 "}, fr("spo2")]},
                                {"name": "optionalMessage", "type": "array", "values": [{"name": "string", "type": "string", "value": "SpO2: "}, fr("spo2"), {"name": "string", "type": "string", "value": "% | PR: "}, fr("pr"), {"name": "string", "type": "string", "value": " bpm | "}, fr("message")]},
                                {"name": "additionalInformation", "type": "array", "values": [nr("device_id"), nr("alert_tier"), nr("spo2"), nr("pr"), nr("patient_name"), nr("message")]},
                            ],
                            "kind": "EmailMessage",
                            "name": "EmailBinding",
                        }
                    ],
                },
            ],
        }

        rule_entity = {
            "uniqueIdentifier": str(uuid.uuid4()),
            "payload": {
                "name": "Clinical alert events alert",
                "parentContainer": {"targetUniqueIdentifier": container_id},
                "definition": {
                    "type": "Rule",
                    "instance": json.dumps(rule_inst),
                    "settings": {"shouldRun": True, "shouldApplyRuleOnUpdate": True},
                },
            },
            "type": "timeSeriesView-v1",
        }
        entities.append(rule_entity)

    json_str = json.dumps(entities)
    b64_str = base64.b64encode(json_str.encode("utf-8")).decode("ascii")
    return entities, b64_str


def poll_lro(op_id: str, token: str, deadline_seconds: int = LRO_TIMEOUT_SECONDS) -> None:
    """Poll Fabric long running operation until Succeeded or Timeout."""
    import requests
    start = time.time()
    url = f"{FABRIC_API_BASE}/operations/{op_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "x-ms-fabric-skill": SKILL_HEADER,
    }
    while time.time() - start < deadline_seconds:
        interval = min(3.0, max(0.01, deadline_seconds / 5.0))
        time.sleep(interval)
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status")
                if status == "Succeeded":
                    return
                if status in ("Failed", "Cancelled"):
                    raise RuntimeError(f"Fabric LRO {op_id} ended with status: {status}")
        except requests.RequestException:
            pass

    sys.stderr.write(f"Operation timed out after {deadline_seconds}s (Operation ID: {op_id})\n")
    raise TimeoutError(f"Reflex LRO {op_id} did not reach Succeeded within {deadline_seconds} seconds")


def deploy_activator(
    workspace_name: str = "med-1103a",
    email: Optional[str] = None,
    dry_run: bool = True,
    cleanup: bool = False,
) -> Dict[str, Any]:
    """Idempotently deploy or update ClinicalAlertActivator Reflex item."""
    # FR-2: Allowlist check before any network call
    recipient = validate_recipient_allowlist(email)

    reflex_name = "ClinicalAlertActivator"

    if dry_run:
        # Build planned entities and verify schema
        dummy_ws = "f306e105-78fd-4b16-bfbe-2b556d493cb7"
        dummy_kql = "00000000-0000-0000-0000-000000000001"
        entities, b64_payload = build_reflex_entities(recipient, dummy_kql, dummy_ws, execution_interval_seconds=60, include_rule=True)
        return {
            "status": "PLAN_READY",
            "mode": "DRY RUN (no live network writes)",
            "reflex_name": reflex_name,
            "recipient": recipient,
            "execution_interval_seconds": 60,
            "source": "fn_ClinicalAlerts(10)",
            "entity_count": len(entities),
            "payload_bytes": len(b64_payload),
        }

    # Live deployment
    import requests
    token = get_fabric_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-ms-fabric-skill": SKILL_HEADER,
    }

    # 1. Resolve workspace ID
    ws_resp = requests.get(f"{FABRIC_API_BASE}/workspaces", headers=headers, timeout=20)
    ws_resp.raise_for_status()
    workspaces = ws_resp.json().get("value", [])
    ws = next((w for w in workspaces if w.get("displayName") == workspace_name), None)
    if not ws:
        raise RuntimeError(f"Workspace '{workspace_name}' not found")
    ws_id = ws["id"]

    # 2. Discover KQL Database
    kql_resp = requests.get(f"{FABRIC_API_BASE}/workspaces/{ws_id}/kqlDatabases", headers=headers, timeout=20)
    kql_resp.raise_for_status()
    kql_dbs = kql_resp.json().get("value", [])
    kql_db = next((k for k in kql_dbs if "masimo" in k.get("displayName", "").lower()), None)
    if not kql_db and kql_dbs:
        kql_db = kql_dbs[0]
    if not kql_db:
        raise RuntimeError(f"No KQL Database found in workspace '{workspace_name}'")
    kql_db_id = kql_db["id"]

    # 3. Check for existing Reflex
    items_resp = requests.get(f"{FABRIC_API_BASE}/workspaces/{ws_id}/items?type=Reflex", headers=headers, timeout=20)
    items_resp.raise_for_status()
    items = items_resp.json().get("value", [])
    existing = next((i for i in items if i.get("displayName") == reflex_name), None)

    if cleanup:
        if existing:
            del_resp = requests.delete(f"{FABRIC_API_BASE}/workspaces/{ws_id}/items/{existing['id']}", headers=headers, timeout=20)
            return {"status": "DELETED", "reflex_id": existing["id"]}
        return {"status": "NOT_FOUND", "message": "Reflex item did not exist"}

    reflex_id = existing["id"] if existing else None

    # Step 1: Create Reflex with data pipeline if not existing
    if not reflex_id:
        _, no_rule_b64 = build_reflex_entities(recipient, kql_db_id, ws_id, execution_interval_seconds=60, include_rule=False)
        create_payload = {
            "displayName": reflex_name,
            "description": f"Clinical alert activator: emails {recipient} on CRITICAL/URGENT alerts from fn_ClinicalAlerts(10).",
            "type": "Reflex",
            "definition": {"parts": [{"path": "ReflexEntities.json", "payload": no_rule_b64, "payloadType": "InlineBase64"}]},
        }
        create_resp = requests.post(f"{FABRIC_API_BASE}/workspaces/{ws_id}/items", headers=headers, json=create_payload, timeout=30)
        if create_resp.status_code == 201:
            reflex_id = create_resp.json().get("id")
        elif create_resp.status_code == 202:
            op_id = create_resp.headers.get("x-ms-operation-id")
            if op_id:
                poll_lro(op_id, token)
            # Find created item
            for _ in range(12):
                time.sleep(3)
                refresh_resp = requests.get(f"{FABRIC_API_BASE}/workspaces/{ws_id}/items?type=Reflex", headers=headers, timeout=20)
                if refresh_resp.status_code == 200:
                    found = next((i for i in refresh_resp.json().get("value", []) if i.get("displayName") == reflex_name), None)
                    if found:
                        reflex_id = found["id"]
                        break
        else:
            raise RuntimeError(f"Reflex creation failed with HTTP {create_resp.status_code}: {create_resp.text}")

    if not reflex_id:
        raise RuntimeError("Reflex was not created or resolved")

    # Step 2: Update definition to add EventTrigger rule
    time.sleep(2)
    _, full_b64 = build_reflex_entities(recipient, kql_db_id, ws_id, execution_interval_seconds=60, include_rule=True)
    update_payload = {"definition": {"parts": [{"path": "ReflexEntities.json", "payload": full_b64, "payloadType": "InlineBase64"}]}}
    upd_resp = requests.post(f"{FABRIC_API_BASE}/workspaces/{ws_id}/items/{reflex_id}/updateDefinition", headers=headers, json=update_payload, timeout=30)
    if upd_resp.status_code not in (200, 202):
        raise RuntimeError(f"Reflex updateDefinition failed with HTTP {upd_resp.status_code}: {upd_resp.text}")

    if upd_resp.status_code == 202:
        op_id = upd_resp.headers.get("x-ms-operation-id")
        if op_id:
            poll_lro(op_id, token)

    return {
        "status": "DEPLOYED",
        "reflex_id": reflex_id,
        "reflex_name": reflex_name,
        "workspace_id": ws_id,
        "kql_db_id": kql_db_id,
        "recipient": recipient,
        "execution_interval_seconds": 60,
    }


def main():
    parser = argparse.ArgumentParser(description="Deploy or update ClinicalAlertActivator Reflex item.")
    parser.add_argument("--workspace-name", "--workspace", dest="workspace_name", default=os.environ.get("FABRIC_WORKSPACE_NAME", "med-1103a"), help="Fabric workspace name")
    parser.add_argument("--email", help="Notification recipient email (must match HLS_ALERT_EMAIL allowlist)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Dry run mode (validates without deployment)")
    parser.add_argument("--live", action="store_true", help="Live deployment against Fabric workspace")
    parser.add_argument("--cleanup", action="store_true", help="Delete ClinicalAlertActivator Reflex item")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    # Dry-run if explicitly requested or if not --live
    dry_run = args.dry_run or (not args.live and not args.cleanup)

    res = deploy_activator(
        workspace_name=args.workspace_name,
        email=args.email,
        dry_run=dry_run,
        cleanup=args.cleanup,
    )

    if args.json:
        print(json.dumps(res, indent=2))
        return

    print("==================================================================")
    print("           FABRIC CLINICAL ALERT ACTIVATOR DEPLOYMENT             ")
    print("==================================================================")
    print(f"Status: {res.get('status')}")
    print(f"Reflex Name: {res.get('reflex_name')}")
    if res.get("reflex_id"):
        print(f"Reflex ID: {res.get('reflex_id')}")
    print(f"Recipient: {res.get('recipient')}")
    print(f"Execution Interval: {res.get('execution_interval_seconds')}s")
    print(f"Mode: {res.get('mode', 'LIVE')}")


if __name__ == "__main__":
    main()

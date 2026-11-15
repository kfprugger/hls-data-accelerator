#!/usr/bin/env python3
"""Deploy or update Fabric Data Activator Reflex item for Clinical Alerts.

Creates or updates ClinicalAlertActivator Reflex item in Fabric workspace using kqlSource-v1
querying fn_ClinicalAlerts with Microsoft Learn Method 2 stateful alerting (Device object grouping,
alert_active transition BecomesGreaterThan 0), runSettings.executionIntervalInSeconds = 60, and
an email action targeting HLS_ALERT_EMAIL with a configurable cooldown window (default 10 minutes)
and a configurable lowest alert tier (default URGENT, which emails CRITICAL and URGENT alerts).
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
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
SKILL_HEADER = "activator-cli"
LRO_TIMEOUT_SECONDS = 300
ALERT_TIERS = ("CRITICAL", "URGENT", "WARNING")  # most severe first
ACTIVATOR_POLL_INTERVAL_SECONDS = 60.0  # P: Reflex executionIntervalInSeconds
INGEST_LATENCY_ALLOWANCE_SECONDS = 10.0  # L: Eventstream ingestion and indexing latency allowance
REFLEX_SETTLE_SECONDS = ACTIVATOR_POLL_INTERVAL_SECONDS + INGEST_LATENCY_ALLOWANCE_SECONDS  # P + L = 70.0s
DEFAULT_COOLDOWN_MINUTES = 10
DEFAULT_MIN_TIER = "URGENT"
ALERT_PROBE_FIELD = "alert_probe_id"  # TelemetryRaw.metadata key carrying a per-trigger correlation id
ALERT_PROBE_SUBJECT_OPEN = "[probe "
ALERT_PROBE_SUBJECT_CLOSE = "]"


def alert_probe_subject_marker(probe_id: str) -> str:
    """Exact subject fragment the Activator email renders for a probe id."""
    return f"{ALERT_PROBE_SUBJECT_OPEN}{probe_id}{ALERT_PROBE_SUBJECT_CLOSE}"


def tiers_at_or_above(min_tier: str) -> Tuple[str, ...]:
    """Return the alert tiers at or above min_tier, most severe first."""
    tier = (min_tier or "").strip().upper()
    if tier not in ALERT_TIERS:
        raise ValueError(f"min_tier must be one of {', '.join(ALERT_TIERS)}; got {min_tier!r}")
    return ALERT_TIERS[: ALERT_TIERS.index(tier) + 1]

def validate_cooldown(val: Any) -> int:
    """Validate alert cooldown window in minutes (1..1440). Exits with 2 on CLI failure."""
    try:
        ival = int(val)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(f"Cooldown must be an integer between 1 and 1440, got '{val}'")
    if not (1 <= ival <= 1440):
        raise argparse.ArgumentTypeError(f"Cooldown must be between 1 and 1440 minutes, got {ival}")
    return ival


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

    raise RuntimeError(f"Could not acquire Fabric access token: az exited {proc.returncode}: {proc.stderr.strip()}")


def build_reflex_entities(
    alert_email: str,
    kql_db_id: str,
    workspace_id: str,
    execution_interval_seconds: int = int(ACTIVATOR_POLL_INTERVAL_SECONDS),
    include_rule: bool = True,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    min_tier: str = DEFAULT_MIN_TIER,
) -> Tuple[List[Dict[str, Any]], str]:
    """Build Reflex entities adhering to kqlSource-v1 and AttributeTrigger v1.2.4 constraints.

    Crucial: runSettings contains ONLY executionIntervalInSeconds, never isStopped!
    Stateful alerting (Method 2):
      - kqlSource returns one row per device with alert_active (1 = alert, 0 = normal/recovered)
      - Activator groups by Device (device_id)
      - AttributeTrigger fires when alert_active BecomesGreaterThan 0 (EachTime)
    """
    container_id = str(uuid.uuid4())
    kql_source_id = str(uuid.uuid4())
    event_view_id = str(uuid.uuid4())
    split_event_id = str(uuid.uuid4())
    object_view_id = str(uuid.uuid4())
    attr_device_id = str(uuid.uuid4())
    attr_device_id_val = str(uuid.uuid4())
    attr_alert_active = str(uuid.uuid4())
    attr_alert_tier = str(uuid.uuid4())
    attr_spo2_id = str(uuid.uuid4())
    attr_pr_id = str(uuid.uuid4())
    attr_patient_id = str(uuid.uuid4())
    attr_message_id = str(uuid.uuid4())
    attr_alert_time_id = str(uuid.uuid4())
    attr_probe_id = str(uuid.uuid4())

    if not (1 <= cooldown_minutes <= 1440):
        raise ValueError(f"cooldown_minutes must be between 1 and 1440; got {cooldown_minutes}")

    roster_lookback = max(60, cooldown_minutes + 10)
    tier_filter = ", ".join(f"'{tier}'" for tier in tiers_at_or_above(min_tier))
    kql_query = (
        f"let roster = TelemetryRaw\n"
        f"    | where todatetime(timestamp) > ago({roster_lookback}m)\n"
        f"    | distinct device_id;\n"
        f"let alerts = fn_ClinicalAlerts({cooldown_minutes})\n"
        f"    | where alert_tier in ({tier_filter})\n"
        f"    | summarize arg_max(alert_time, *) by device_id;\n"
        f"let probes = TelemetryRaw\n"
        f"    | where todatetime(timestamp) > ago({cooldown_minutes}m)\n"
        f"    | extend probe_id = tostring(metadata.{ALERT_PROBE_FIELD}), probe_time = todatetime(timestamp)\n"
        f"    | where isnotempty(probe_id)\n"
        f"    | summarize arg_max(probe_time, probe_id) by device_id;\n"
        f"roster\n"
        f"| join kind=leftouter alerts on device_id\n"
        f"| join kind=leftouter probes on device_id\n"
        f"| extend alert_active = iff(isnotempty(alert_tier), 1, 0)\n"
        f"| project\n"
        f"    device_id,\n"
        f"    alert_active,\n"
        f"    alert_tier = coalesce(alert_tier, 'NORMAL'),\n"
        f"    spo2 = coalesce(spo2, 0.0),\n"
        f"    pr = coalesce(pr, 0),\n"
        f"    patient_name = coalesce(patient_name, ''),\n"
        f"    message = coalesce(message, 'Normal'),\n"
        f"    {ALERT_PROBE_FIELD} = coalesce(probe_id, 'none'),\n"
        f"    alert_time = coalesce(alert_time, now())"
    )

    src_evt_inst = {
        "templateId": "SourceEvent",
        "templateVersion": "1.2.4",
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
    split_evt_inst = {
        "templateId": "SplitEvent",
        "templateVersion": "1.2.4",
        "steps": [
            {
                "name": "SplitEventStep",
                "id": str(uuid.uuid4()),
                "rows": [
                    {
                        "name": "EventSelector",
                        "kind": "Event",
                        "arguments": [
                            {
                                "kind": "EventReference",
                                "type": "complex",
                                "arguments": [{"name": "entityId", "type": "string", "value": event_view_id}],
                                "name": "event",
                            }
                        ],
                    },
                    {
                        "name": "FieldIdMapping",
                        "kind": "FieldIdMapping",
                        "arguments": [
                            {"name": "fieldName", "type": "string", "value": "device_id"},
                            {
                                "kind": "AttributeReference",
                                "type": "complex",
                                "arguments": [{"name": "entityId", "type": "string", "value": attr_device_id}],
                                "name": "idPart",
                            },
                        ],
                    },
                    {
                        "name": "SplitEventOptions",
                        "kind": "EventOptions",
                        "arguments": [{"name": "isAuthoritative", "type": "boolean", "value": True}],
                    },
                ],
            }
        ],
    }


    id_part_inst = {
        "templateId": "IdentityPartAttribute",
        "templateVersion": "1.2.4",
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
            "templateVersion": "1.2.4",
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
        {"uniqueIdentifier": split_event_id, "payload": {"name": "SplitEvent", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Event", "instance": json.dumps(split_evt_inst)}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_device_id, "payload": {"name": "device_id", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(id_part_inst)}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_device_id_val, "payload": {"name": "device_id_val", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(split_event_id, "device_id", "Text"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_alert_active, "payload": {"name": "alert_active", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(split_event_id, "alert_active", "Number"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_alert_tier, "payload": {"name": "alert_tier", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(split_event_id, "alert_tier", "Text"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_spo2_id, "payload": {"name": "spo2", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(split_event_id, "spo2", "Number"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_pr_id, "payload": {"name": "pr", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(split_event_id, "pr", "Number"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_patient_id, "payload": {"name": "patient_name", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(split_event_id, "patient_name", "Text"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_message_id, "payload": {"name": "message", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(split_event_id, "message", "Text"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_alert_time_id, "payload": {"name": "alert_time", "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(split_event_id, "alert_time", "Text"))}}, "type": "timeSeriesView-v1"},
        {"uniqueIdentifier": attr_probe_id, "payload": {"name": ALERT_PROBE_FIELD, "parentObject": {"targetUniqueIdentifier": object_view_id}, "parentContainer": {"targetUniqueIdentifier": container_id}, "definition": {"type": "Attribute", "instance": json.dumps(basic_attr_inst(split_event_id, ALERT_PROBE_FIELD, "Text"))}}, "type": "timeSeriesView-v1"},
    ]

    if include_rule:
        def ar(entity_id: str) -> Dict[str, Any]:
            return {
                "kind": "AttributeReference",
                "type": "complex",
                "arguments": [{"name": "entityId", "type": "string", "value": entity_id}],
            }

        def anr(name: str, entity_id: str) -> Dict[str, Any]:
            return {
                "kind": "NameReferencePair",
                "type": "complex",
                "arguments": [
                    {"name": "name", "type": "string", "value": name},
                    {
                        "kind": "AttributeReference",
                        "name": "reference",
                        "type": "complexReference",
                        "arguments": [{"name": "entityId", "type": "string", "value": entity_id}],
                    },
                ],
            }

        rule_inst = {
            "templateId": "AttributeTrigger",
            "templateVersion": "1.2.4",
            "steps": [
                {
                    "id": str(uuid.uuid4()),
                    "name": "ScalarSelectStep",
                    "rows": [
                        {
                            "name": "AttributeSelector",
                            "kind": "Attribute",
                            "arguments": [
                                {
                                    "kind": "AttributeReference",
                                    "name": "attribute",
                                    "type": "complex",
                                    "arguments": [{"name": "entityId", "type": "string", "value": attr_alert_active}],
                                }
                            ],
                        }
                    ],
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "ScalarDetectStep",
                    "rows": [
                        {
                            "name": "NumberBecomes",
                            "kind": "NumberBecomes",
                            "arguments": [
                                {"name": "op", "type": "string", "value": "BecomesGreaterThan"},
                                {"name": "value", "type": "number", "value": 0},
                            ],
                        },
                        {
                            "name": "OccurrenceOption",
                            "kind": "EachTime",
                            "arguments": [],
                        },
                    ],
                },
                {
                    "id": str(uuid.uuid4()),
                    "name": "ActStep",
                    "rows": [
                        {
                            "name": "EmailBinding",
                            "kind": "EmailMessage",
                            "arguments": [
                                {"name": "messageLocale", "type": "string", "value": "en-us"},
                                {"name": "sentTo", "type": "array", "values": [{"type": "string", "value": alert_email}]},
                                {"name": "copyTo", "type": "array", "values": []},
                                {"name": "bCCTo", "type": "array", "values": []},
                                {
                                    "name": "subject",
                                    "type": "array",
                                    "values": [
                                        {"name": "string", "type": "string", "value": "CLINICAL ALERT - SpO2 low on "},
                                        ar(attr_device_id_val),
                                        {"name": "string", "type": "string", "value": f" {ALERT_PROBE_SUBJECT_OPEN}"},
                                        ar(attr_probe_id),
                                        {"name": "string", "type": "string", "value": ALERT_PROBE_SUBJECT_CLOSE},
                                    ],
                                },
                                {
                                    "name": "headline",
                                    "type": "array",
                                    "values": [
                                        ar(attr_alert_tier),
                                        {"name": "string", "type": "string", "value": " ALERT: "},
                                        ar(attr_patient_id),
                                        {"name": "string", "type": "string", "value": " - SpO2 "},
                                        ar(attr_spo2_id),
                                    ],
                                },
                                {
                                    "name": "optionalMessage",
                                    "type": "array",
                                    "values": [
                                        {"name": "string", "type": "string", "value": "SpO2: "},
                                        ar(attr_spo2_id),
                                        {"name": "string", "type": "string", "value": "% | PR: "},
                                        ar(attr_pr_id),
                                        {"name": "string", "type": "string", "value": " bpm | "},
                                        ar(attr_message_id),
                                    ],
                                },
                                {
                                    "name": "additionalInformation",
                                    "type": "array",
                                    "values": [
                                        anr("device_id", attr_device_id_val),
                                        anr("alert_tier", attr_alert_tier),
                                        anr("spo2", attr_spo2_id),
                                        anr("pr", attr_pr_id),
                                        anr("patient_name", attr_patient_id),
                                        anr("message", attr_message_id),
                                        anr(ALERT_PROBE_FIELD, attr_probe_id),
                                    ],
                                },
                            ],
                        }
                    ],
                },
            ],
        }

        rule_entity = {
            "uniqueIdentifier": str(uuid.uuid4()),
            "payload": {
                "name": "Clinical alert events alert",
                "description": "Created by: skills-for-fabric",
                "parentObject": {"targetUniqueIdentifier": object_view_id},
                "parentContainer": {"targetUniqueIdentifier": container_id},
                "definition": {
                    "type": "Rule",
                    "instance": json.dumps(rule_inst),
                    "settings": {"shouldRun": True, "shouldApplyRuleOnUpdate": False},
                },
            },
            "type": "timeSeriesView-v1",
        }
        entities.append(rule_entity)

    json_str = json.dumps(entities)
    b64_str = base64.b64encode(json_str.encode("utf-8")).decode("ascii")
    return entities, b64_str



RETRYABLE_STATUS = (429, 500, 502, 503, 504)
MAX_BACKOFF_SECONDS = 60.0


def is_retryable_response(resp: requests.Response) -> bool:
    """Transient Fabric failures: throttling, 5xx, and the inbound-policy 403 flap."""
    return resp.status_code in RETRYABLE_STATUS or (
        resp.status_code == 403 and "RequestDeniedByInboundPolicy" in resp.text
    )


def retry_delay_seconds(resp: Optional[requests.Response], attempt: int) -> float:
    """Honour Retry-After when present; otherwise exponential backoff, both capped at 60 s."""
    backoff = min(MAX_BACKOFF_SECONDS, 2.0 ** (attempt - 1))
    retry_after = resp.headers.get("Retry-After") if resp is not None else None
    if retry_after:
        try:
            return min(MAX_BACKOFF_SECONDS, max(0.1, float(retry_after)))
        except ValueError:
            return backoff
    return backoff


def fabric_request(
    method: str,
    url: str,
    headers: Dict[str, str],
    json_data: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
    max_attempts: int = 8,
) -> requests.Response:
    """Send one Fabric REST request with retries on transient failures.

    Up to ``max_attempts`` tries with a ``timeout``-second per-request limit. Retries
    429/5xx, 403 RequestDeniedByInboundPolicy and network errors; returns any other
    response for the caller to judge. Not for item-creating POSTs (see deploy_activator).
    """
    method_upper = method.upper()
    send = {"GET": requests.get, "POST": requests.post, "DELETE": requests.delete}.get(method_upper)
    for attempt in range(1, max_attempts + 1):
        try:
            if send is None:
                resp = requests.request(method_upper, url, headers=headers, json=json_data, timeout=timeout)
            elif method_upper == "POST":
                resp = send(url, headers=headers, json=json_data, timeout=timeout)
            else:
                resp = send(url, headers=headers, timeout=timeout)
        except requests.RequestException as ex:
            if attempt == max_attempts:
                raise RuntimeError(
                    f"Fabric request {method_upper} {url} failed after {max_attempts} attempts: {ex}"
                ) from ex
            time.sleep(retry_delay_seconds(None, attempt))
            continue
        if not is_retryable_response(resp):
            return resp
        if attempt == max_attempts:
            raise RuntimeError(
                f"Fabric request {method_upper} {url} failed with HTTP {resp.status_code} after {max_attempts} attempts: {resp.text}"
            )
        time.sleep(retry_delay_seconds(resp, attempt))
    raise AssertionError("unreachable")


def find_reflex_id(ws_id: str, headers: Dict[str, str], reflex_name: str) -> Optional[str]:
    """Return the id of the Reflex item named ``reflex_name``, or None when absent."""
    resp = fabric_request("GET", f"{FABRIC_API_BASE}/workspaces/{ws_id}/items?type=Reflex", headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list Reflex items: HTTP {resp.status_code} - {resp.text}")
    found = next((i for i in resp.json().get("value", []) if i.get("displayName") == reflex_name), None)
    return found.get("id") if found else None


def poll_lro(op_id: str, token: str, deadline_seconds: float = LRO_TIMEOUT_SECONDS) -> None:
    """Poll a Fabric long-running operation until Succeeded; raise on failure or deadline."""
    start = time.time()
    url = f"{FABRIC_API_BASE}/operations/{op_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "x-ms-fabric-skill": SKILL_HEADER,
    }
    default_interval = min(3.0, max(0.01, deadline_seconds / 5.0))
    interval = default_interval
    last_status = "unknown"
    while time.time() - start < deadline_seconds:
        remaining = deadline_seconds - (time.time() - start)
        time.sleep(max(0.0, min(interval, remaining)))
        resp = fabric_request("GET", url, headers=headers, timeout=60, max_attempts=3)
        if resp.status_code not in (200, 202):
            raise RuntimeError(f"Fabric LRO {op_id} polling failed with HTTP {resp.status_code}: {resp.text}")
        data = resp.json() if resp.text else {}
        last_status = data.get("status") or last_status
        if last_status == "Succeeded":
            return
        if last_status in ("Failed", "Cancelled"):
            raise RuntimeError(f"Fabric LRO {op_id} ended with status: {last_status}, detail: {data.get('error', resp.text)}")
        retry_after = resp.headers.get("Retry-After") if hasattr(resp, "headers") else None
        try:
            interval = min(60.0, max(default_interval, float(retry_after))) if retry_after else default_interval
        except (TypeError, ValueError):
            interval = default_interval

    sys.stderr.write(f"Operation timed out after {deadline_seconds}s (Operation ID: {op_id})\n")
    raise TimeoutError(f"Reflex LRO {op_id} did not reach Succeeded within {deadline_seconds} seconds (last status: {last_status})")


def deploy_activator(
    workspace_name: str = "med-1103a",
    email: Optional[str] = None,
    dry_run: bool = True,
    cleanup: bool = False,
    cooldown_minutes: int = 10,
    min_tier: str = "URGENT",
) -> Dict[str, Any]:
    """Idempotently deploy or update ClinicalAlertActivator Reflex item."""
    # FR-2: Allowlist check before any network call
    recipient = validate_recipient_allowlist(email)
    alert_tiers = tiers_at_or_above(min_tier)

    if not (1 <= cooldown_minutes <= 1440):
        sys.stderr.write(f"Error: cooldown_minutes must be between 1 and 1440, got {cooldown_minutes}\n")
        sys.exit(2)

    reflex_name = "ClinicalAlertActivator"

    if dry_run:
        # Build planned entities and verify schema
        dummy_ws = "00000000-0000-0000-0000-000000000002"
        dummy_kql = "00000000-0000-0000-0000-000000000001"
        entities, b64_payload = build_reflex_entities(
            recipient, dummy_kql, dummy_ws, execution_interval_seconds=int(ACTIVATOR_POLL_INTERVAL_SECONDS), include_rule=True,
            cooldown_minutes=cooldown_minutes, min_tier=min_tier,
        )
        return {
            "status": "PLAN_READY",
            "mode": "DRY RUN (no live network writes)",
            "reflex_name": reflex_name,
            "recipient": recipient,
            "execution_interval_seconds": int(ACTIVATOR_POLL_INTERVAL_SECONDS),
            "cooldown_minutes": cooldown_minutes,
            "alert_tiers": list(alert_tiers),
            "source": f"fn_ClinicalAlerts({cooldown_minutes})",
            "entity_count": len(entities),
            "payload_bytes": len(b64_payload),
        }
    # Live deployment
    token = get_fabric_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-ms-fabric-skill": SKILL_HEADER,
    }

    # 1. Resolve workspace ID
    ws_resp = fabric_request("GET", f"{FABRIC_API_BASE}/workspaces", headers=headers, timeout=60)
    if ws_resp.status_code != 200:
        raise RuntimeError(f"Failed to list workspaces: HTTP {ws_resp.status_code} - {ws_resp.text}")
    workspaces = ws_resp.json().get("value", [])
    ws = next((w for w in workspaces if w.get("displayName") == workspace_name), None)
    if not ws:
        raise RuntimeError(f"Workspace '{workspace_name}' not found")
    ws_id = ws["id"]

    # 2. Discover KQL Database
    kql_resp = fabric_request("GET", f"{FABRIC_API_BASE}/workspaces/{ws_id}/kqlDatabases", headers=headers, timeout=60)
    if kql_resp.status_code != 200:
        raise RuntimeError(f"Failed to list KQL databases: HTTP {kql_resp.status_code} - {kql_resp.text}")
    kql_dbs = kql_resp.json().get("value", [])
    kql_db = next((k for k in kql_dbs if "masimo" in k.get("displayName", "").lower()), None)
    if not kql_db and kql_dbs:
        kql_db = kql_dbs[0]
    if not kql_db:
        raise RuntimeError(f"No KQL Database found in workspace '{workspace_name}'")
    kql_db_id = kql_db["id"]

    # 3. Check for existing Reflex
    items_resp = fabric_request("GET", f"{FABRIC_API_BASE}/workspaces/{ws_id}/items?type=Reflex", headers=headers, timeout=60)
    if items_resp.status_code != 200:
        raise RuntimeError(f"Failed to list Reflex items: HTTP {items_resp.status_code} - {items_resp.text}")
    items = items_resp.json().get("value", [])
    existing = next((i for i in items if i.get("displayName") == reflex_name), None)

    if cleanup:
        if existing:
            del_resp = fabric_request("DELETE", f"{FABRIC_API_BASE}/workspaces/{ws_id}/items/{existing['id']}", headers=headers, timeout=60)
            if del_resp.status_code not in (200, 204):
                raise RuntimeError(f"Failed to delete Reflex item: HTTP {del_resp.status_code} - {del_resp.text}")
            return {"status": "DELETED", "reflex_id": existing["id"]}
        return {"status": "NOT_FOUND", "message": "Reflex item did not exist"}

    reflex_id = existing["id"] if existing else None

    # Step 1: Create Reflex with data pipeline if not existing
    if not reflex_id:
        _, no_rule_b64 = build_reflex_entities(
            recipient, kql_db_id, ws_id, execution_interval_seconds=int(ACTIVATOR_POLL_INTERVAL_SECONDS), include_rule=False,
            cooldown_minutes=cooldown_minutes, min_tier=min_tier,
        )
        create_payload = {
            "displayName": reflex_name,
            "description": f"Clinical alert activator: emails {recipient} on {'/'.join(alert_tiers)} alerts from fn_ClinicalAlerts({cooldown_minutes}) with {cooldown_minutes}-minute cooldown.",
            "type": "Reflex",
            "definition": {"parts": [{"path": "ReflexEntities.json", "payload": no_rule_b64, "payloadType": "InlineBase64"}]},
        }
        create_url = f"{FABRIC_API_BASE}/workspaces/{ws_id}/items"
        max_create_attempts = 8
        for attempt in range(1, max_create_attempts + 1):
            if attempt > 1:
                # A timed-out or 5xx create may still have succeeded: reuse it instead of re-POSTing.
                reflex_id = find_reflex_id(ws_id, headers, reflex_name)
                if reflex_id:
                    break
            try:
                create_resp = requests.post(create_url, headers=headers, json=create_payload, timeout=60)
            except requests.RequestException as ex:
                if attempt == max_create_attempts:
                    raise RuntimeError(f"Reflex creation failed after {max_create_attempts} attempts: {ex}") from ex
                time.sleep(retry_delay_seconds(None, attempt))
                continue
            if create_resp.status_code == 201:
                reflex_id = create_resp.json().get("id")
                break
            if create_resp.status_code == 202:
                op_id = create_resp.headers.get("x-ms-operation-id")
                if op_id:
                    poll_lro(op_id, token)
                find_deadline = time.time() + 60
                while not reflex_id and time.time() < find_deadline:
                    reflex_id = find_reflex_id(ws_id, headers, reflex_name)
                    if not reflex_id:
                        time.sleep(3)
                if not reflex_id:
                    raise RuntimeError(f"Reflex item '{reflex_name}' creation accepted (202) but the item was not listed within 60 s")
                break
            if not is_retryable_response(create_resp) or attempt == max_create_attempts:
                raise RuntimeError(f"Reflex creation failed with HTTP {create_resp.status_code}: {create_resp.text}")
            time.sleep(retry_delay_seconds(create_resp, attempt))

    if not reflex_id:
        raise RuntimeError("Reflex was not created or resolved")

    # Step 2: Update definition to add EventTrigger rule
    time.sleep(2)
    _, full_b64 = build_reflex_entities(
        recipient, kql_db_id, ws_id, execution_interval_seconds=int(ACTIVATOR_POLL_INTERVAL_SECONDS), include_rule=True,
        cooldown_minutes=cooldown_minutes, min_tier=min_tier,
    )
    update_payload = {"definition": {"parts": [{"path": "ReflexEntities.json", "payload": full_b64, "payloadType": "InlineBase64"}]}}
    upd_resp = fabric_request(
        "POST",
        f"{FABRIC_API_BASE}/workspaces/{ws_id}/items/{reflex_id}/updateDefinition",
        headers=headers,
        json_data=update_payload,
        timeout=60,
    )
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
        "execution_interval_seconds": int(ACTIVATOR_POLL_INTERVAL_SECONDS),
        "cooldown_minutes": cooldown_minutes,
        "alert_tiers": list(alert_tiers),
    }


def main():
    _bind_interface_if_configured()
    parser = argparse.ArgumentParser(description="Deploy or update ClinicalAlertActivator Reflex item.")
    parser.add_argument("--workspace-name", "--workspace", dest="workspace_name", default=os.environ.get("FABRIC_WORKSPACE_NAME", "med-1103a"), help="Fabric workspace name")
    parser.add_argument("--email", help="Notification recipient email (must match HLS_ALERT_EMAIL allowlist)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Dry run mode (validates without deployment)")
    parser.add_argument("--live", action="store_true", help="Live deployment against Fabric workspace")
    parser.add_argument("--cleanup", action="store_true", help="Delete ClinicalAlertActivator Reflex item")
    parser.add_argument(
        "--cooldown-minutes",
        type=validate_cooldown,
        default=10,
        help="Alert suppression cooldown window in minutes (1..1440; default: 10)",
    )
    parser.add_argument(
        "--min-tier",
        type=str.upper,
        choices=ALERT_TIERS,
        default="URGENT",
        help="Lowest alert tier that sends email: WARNING, URGENT or CRITICAL (default: URGENT)",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    # Dry-run if explicitly requested or if not --live
    dry_run = args.dry_run or (not args.live and not args.cleanup)

    res = deploy_activator(
        workspace_name=args.workspace_name,
        email=args.email,
        dry_run=dry_run,
        cleanup=args.cleanup,
        cooldown_minutes=args.cooldown_minutes,
        min_tier=args.min_tier,
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
    print(f"Cooldown Minutes: {res.get('cooldown_minutes')}m")
    print(f"Alert Tiers: {', '.join(res.get('alert_tiers', []))}")


if __name__ == "__main__":
    main()

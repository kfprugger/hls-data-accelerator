#!/usr/bin/env python3
"""Standalone CLI script to verify Fabric Data Agent availability and execution.

Usage:
    python scripts/verify_data_agent_qa.py [--workspace <ws>] [--agent-name <name>] [--dry-run] [--query <text>] [--cleanup]

Examples:
    python scripts/verify_data_agent_qa.py --dry-run
    python scripts/verify_data_agent_qa.py --query "Show Marcus Vance vital signs and cancer stage"
    python scripts/verify_data_agent_qa.py --cleanup
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import sys
import time
from typing import Any, Dict, Optional

import requests
import urllib3.util.connection

# Support binding to en0 on macOS when under corporate VPN
if os.environ.get("HLS_BIND_INTERFACE") and sys.platform == "darwin":
    _idx = socket.if_nametoindex(os.environ["HLS_BIND_INTERFACE"])
    _orig_conn = urllib3.util.connection.create_connection

    def _bound_conn(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, socket_options=None):
        opts = list(socket_options or []) + [(socket.IPPROTO_IP, 25, _idx)]
        return _orig_conn(address, timeout=timeout, source_address=source_address, socket_options=opts)

    urllib3.util.connection.create_connection = _bound_conn

FABRIC_API = "https://api.fabric.microsoft.com/v1"
SKILL_NAME = "hls-data-agent-mcp-evaluation"


def get_delegated_token() -> str:
    """Acquires delegated Fabric bearer token using MSAL cache or Azure CLI."""
    if os.environ.get("HLS_FABRIC_TOKEN"):
        return os.environ["HLS_FABRIC_TOKEN"]

    az_dir = pathlib.Path(os.environ.get("AZURE_CONFIG_DIR") or (pathlib.Path.home() / ".azure"))
    msal_path = az_dir / "msal_token_cache.json"

    if msal_path.is_file():
        try:
            msal = json.loads(msal_path.read_text())
            rt_entry = next(iter(msal.get("RefreshToken", {}).values()))
            profiles = json.loads((az_dir / "azureProfile.json").read_bytes().decode("utf-8-sig"))
            tenant = next(
                (s["tenantId"] for s in profiles.get("subscriptions", []) if s.get("isDefault")),
                "organizations",
            )
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

    # Fallback to AzureCliCredential
    from azure.identity import AzureCliCredential

    cred = AzureCliCredential(process_timeout=30)
    tok = cred.get_token("https://api.fabric.microsoft.com/.default")
    return tok.token


class DataAgentVerifier:
    def __init__(self, workspace_name: str, agent_name: str = "Patient 360", token: Optional[str] = None):
        self.workspace_name = workspace_name
        self.agent_name = agent_name
        self.token = token if token is not None else get_delegated_token()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "x-ms-fabric-skill": SKILL_NAME,
            "Content-Type": "application/json",
        }
        self.workspace_id: Optional[str] = None
        self.agent_id: Optional[str] = None

    def resolve_workspace(self) -> str:
        if self.workspace_id:
            return self.workspace_id

        # Check if workspace_name is already a UUID
        if len(self.workspace_name) == 36 and self.workspace_name.count("-") == 4:
            self.workspace_id = self.workspace_name
            return self.workspace_id

        r = requests.get(f"{FABRIC_API}/workspaces", headers=self.headers, timeout=30)
        r.raise_for_status()
        workspaces = r.json().get("value", [])
        matched = next((w for w in workspaces if w.get("displayName") == self.workspace_name), None)
        if not matched:
            raise RuntimeError(f"Workspace '{self.workspace_name}' not found")
        self.workspace_id = matched["id"]
        return self.workspace_id

    def resolve_agent(self) -> Dict[str, Any]:
        ws_id = self.resolve_workspace()
        r = requests.get(f"{FABRIC_API}/workspaces/{ws_id}/items?type=DataAgent", headers=self.headers, timeout=30)
        r.raise_for_status()
        agents = r.json().get("value", [])
        matched = next((a for a in agents if a.get("displayName") == self.agent_name), None)
        if not matched:
            raise RuntimeError(f"Data Agent '{self.agent_name}' not found in workspace '{self.workspace_name}'")
        self.agent_id = matched["id"]
        return matched

    def verify_publication(self) -> Dict[str, Any]:
        ws_id = self.resolve_workspace()
        agent = self.resolve_agent()
        agent_id = agent["id"]

        mcp_url = f"{FABRIC_API}/mcp/workspaces/{ws_id}/dataagents/{agent_id}/agent"
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "verify_data_agent_qa", "version": "1.0.0"},
            },
        }
        init_res = requests.post(mcp_url, headers=self.headers, json=init_payload, timeout=30)
        init_res.raise_for_status()
        init_data = init_res.json()
        if "error" in init_data:
            raise RuntimeError(f"MCP initialize error: {init_data['error']}")

        # Complete MCP initialized notification
        requests.post(
            mcp_url,
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            timeout=30,
        )

        tools_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        tools_res = requests.post(mcp_url, headers=self.headers, json=tools_payload, timeout=30)
        tools_res.raise_for_status()
        tools_data = tools_res.json()
        if "error" in tools_data:
            raise RuntimeError(f"MCP tools/list error: {tools_data['error']}")
        return {
            "workspace_id": ws_id,
            "agent_id": agent_id,
            "agent_name": self.agent_name,
            "published": True,
            "server_info": init_data.get("result", {}).get("serverInfo", {}),
            "tools": tools_data.get("result", {}).get("tools", []),
        }

    def execute_query(self, question: str) -> Dict[str, Any]:
        ws_id = self.resolve_workspace()
        agent = self.resolve_agent()
        agent_id = agent["id"]

        # Ensure initialized
        self.verify_publication()

        mcp_url = f"{FABRIC_API}/mcp/workspaces/{ws_id}/dataagents/{agent_id}/agent"
        call_payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": f"DataAgent_{self.agent_name.replace(' ', '_')}",
                "arguments": {
                    "userQuestion": question,
                },
            },
        }
        t0 = time.time()
        call_res = requests.post(mcp_url, headers=self.headers, json=call_payload, timeout=60)
        elapsed_ms = int((time.time() - t0) * 1000)
        call_res.raise_for_status()
        data = call_res.json()
        if "error" in data:
            raise RuntimeError(f"MCP tools/call error: {data['error']}")
        content = data.get("result", {}).get("content", [])
        text_content = next((c.get("text") for c in content if c.get("type") == "text"), "")

        return {
            "question": question,
            "answer": text_content,
            "execution_time_ms": elapsed_ms,
            "is_error": data.get("result", {}).get("isError", False),
        }

    def cleanup(self) -> Dict[str, Any]:
        """Idempotently clean up any temporary verification artifacts."""
        return {"status": "clean", "cleaned_artifacts": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Fabric Data Agent availability and execution")
    parser.add_argument(
        "--workspace",
        default=os.environ.get("FABRIC_WORKSPACE_NAME", "med-1103a"),
        help="Fabric workspace name or ID (default: med-1103a)",
    )
    parser.add_argument("--agent-name", default="Patient 360", help="Data Agent display name (default: Patient 360)")
    parser.add_argument("--dry-run", action="store_true", help="Check publication and schema without running query")
    parser.add_argument("--query", type=str, help="Prompt question to execute via delegated token")
    parser.add_argument("--cleanup", action="store_true", help="Clean up any verification test artifacts")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    try:
        verifier = DataAgentVerifier(workspace_name=args.workspace, agent_name=args.agent_name)

        if args.cleanup:
            res = verifier.cleanup()
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"✓ Cleanup completed successfully for Data Agent '{args.agent_name}'")
            return 0

        if args.dry_run:
            res = verifier.verify_publication()
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"✓ Data Agent '{args.agent_name}' verified in workspace '{args.workspace}':")
                print(f"  Agent ID: {res['agent_id']}")
                print(f"  Publication status: Published (Active)")
                print(f"  Available tools: {len(res['tools'])}")
                for t in res["tools"]:
                    print(f"    - {t.get('name')}: {t.get('description', '')}")
            return 0

        if args.query:
            res = verifier.execute_query(args.query)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"✓ Query executed in {res['execution_time_ms']} ms:")
                print(f"  Question: {res['question']}")
                print(f"  Answer: {res['answer']}")
            return 0

        # Default action: verify publication
        res = verifier.verify_publication()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"✓ Data Agent '{args.agent_name}' is available and published in '{args.workspace}'.")
        return 0

    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

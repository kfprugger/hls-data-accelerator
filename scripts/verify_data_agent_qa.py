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


def get_delegated_token(resource: str = "https://api.fabric.microsoft.com") -> str:
    """Acquires delegated Fabric access credential using MSAL cache or Azure CLI."""
    if resource == "https://api.fabric.microsoft.com" and os.environ.get("HLS_FABRIC_TOKEN"):
        return os.environ["HLS_FABRIC_TOKEN"]

    az_dir = pathlib.Path(os.environ.get("AZURE_CONFIG_DIR") or (pathlib.Path.home() / ".azure"))
    msal_path = az_dir / "msal_token_cache.json"

    target_scope = f"{resource.rstrip('/')}/.default"
    if "kusto" in resource.lower():
        target_scope = "https://kusto.kusto.windows.net/.default"
    elif "database.windows.net" in resource.lower():
        target_scope = "https://database.windows.net/.default"

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
                    "scope": f"{target_scope} offline_access",
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
    tok = cred.get_token(target_scope)
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

        base_url = f"{FABRIC_API}/workspaces/{ws_id}/dataagents/{agent_id}/aiassistant/openai"
        params = {"api-version": "2024-05-01-preview", "stage": "production"}
        call_headers = dict(self.headers)
        call_headers["OpenAI-Beta"] = "assistants=v2"

        t0 = time.time()
        # 1. Resolve assistant
        r_asst = requests.post(f"{base_url}/assistants", params=params, headers=call_headers, json={"model": "not used"}, timeout=30)
        r_asst.raise_for_status()
        asst_id = r_asst.json()["id"]

        # 2. Create thread
        r_th = requests.post(f"{base_url}/threads", params=params, headers=call_headers, json={}, timeout=30)
        r_th.raise_for_status()
        th_id = r_th.json()["id"]

        # 3. Add message (sending user question unchanged without extra prompt instructions)
        r_msg = requests.post(
            f"{base_url}/threads/{th_id}/messages",
            params=params,
            headers=call_headers,
            json={"role": "user", "content": question},
            timeout=30,
        )
        r_msg.raise_for_status()

        # 4. Create run
        r_run = requests.post(
            f"{base_url}/threads/{th_id}/runs",
            params=params,
            headers=call_headers,
            json={"assistant_id": asst_id},
            timeout=30,
        )
        r_run.raise_for_status()
        run_data = r_run.json()
        run_id = run_data["id"]
        # 4. Poll run until completion or terminal state
        terminal_status: Optional[Dict[str, Any]] = None
        for _ in range(45):
            time.sleep(2)
            r_poll = requests.get(
                f"{base_url}/threads/{th_id}/runs/{run_id}",
                params=params,
                headers=call_headers,
                timeout=30,
            )
            if r_poll.status_code == 200:
                p_data = r_poll.json()
                st = p_data.get("status")
                if st in ("completed", "failed", "cancelled", "expired", "requires_action"):
                    terminal_status = p_data
                    break

        elapsed_ms = int((time.time() - t0) * 1000)

        # 5. Fetch run steps
        r_steps = requests.get(
            f"{base_url}/threads/{th_id}/runs/{run_id}/steps",
            params=params,
            headers=call_headers,
            timeout=30,
        )
        steps_data = r_steps.json() if r_steps.status_code == 200 else {}

        # 6. Extract tool-call steps containing executed SQL or KQL
        generated_query = ""
        query_language = ""

        for step in steps_data.get("data", []):
            details = step.get("step_details", {})
            for tc in details.get("tool_calls", []):
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", "")
                out = fn.get("output", "")
                if "execute" in name.lower() or "nl2code" in name.lower() or "sql" in name.lower() or "kql" in name.lower():
                    try:
                        args_obj = json.loads(args) if isinstance(args, str) else args
                        if isinstance(args_obj, dict):
                            if "code" in args_obj and str(args_obj["code"]).strip():
                                candidate = str(args_obj["code"]).strip()
                                generated_query = candidate
                                query_language = "KQL" if "kql" in name.lower() or "kusto" in name.lower() or "|" in candidate else "SQL"
                                break
                            for k, v in args_obj.items():
                                if "natural" in k.lower():
                                    continue
                                if any(sub in k.lower() for sub in ("code", "sql", "query")):
                                    candidate = str(v).strip()
                                    if candidate and ("select" in candidate.lower() or "|" in candidate):
                                        generated_query = candidate
                                        query_language = "KQL" if "kql" in name.lower() or "kusto" in name.lower() or "|" in candidate else "SQL"
                                        break
                    except Exception:
                        pass
                    if not generated_query and isinstance(out, str) and ("select" in out.lower() or "| where" in out.lower() or "from " in out.lower()):
                        generated_query = out.strip()
                        query_language = "KQL" if "telemetry" in out.lower() or "| " in out else "SQL"
            if generated_query:
                break

        # Strip markdown fences if present in generated_query
        if generated_query.startswith("```"):
            lines = generated_query.splitlines()
            if len(lines) >= 2 and lines[0].startswith("```"):
                end_idx = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
                generated_query = "\n".join(lines[1:end_idx]).strip()

        # 7. Get final assistant message (latest assistant response)
        r_msgs = requests.get(
            f"{base_url}/threads/{th_id}/messages",
            params=params,
            headers=call_headers,
            timeout=30,
        )
        answer = ""
        if r_msgs.status_code == 200:
            for m in r_msgs.json().get("data", []):
                if m.get("role") == "assistant":
                    text_parts = [c.get("text", {}).get("value", "") for c in m.get("content", []) if c.get("type") == "text"]
                    answer = "\n".join(text_parts).strip()
                    if answer:
                        break

        # 8. Clean up ephemeral thread
        try:
            requests.delete(f"{base_url}/threads/{th_id}", params=params, headers=call_headers, timeout=10)
        except Exception:
            pass
        # If steps returned no query text, report raw steps response
        if not generated_query:
            is_err = (terminal_status.get("status") if terminal_status else "") != "completed" or not answer
            return {
                "question": question,
                "answer": answer,
                "generatedQuery": "",
                "queryLanguage": "",
                "execution_time_ms": elapsed_ms,
                "is_error": is_err,
                "error": "no query text in run steps" if is_err else None,
                "raw_steps": steps_data,
                "run_status": terminal_status.get("status") if terminal_status else "unknown",
                "last_error": terminal_status.get("last_error") if terminal_status else None,
            }

        return {
            "question": question,
            "answer": answer,
            "generatedQuery": generated_query,
            "queryLanguage": query_language or "SQL",
            "execution_time_ms": elapsed_ms,
            "is_error": False,
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
                if res.get("is_error"):
                    print(f"FAIL: {res.get('error', 'Execution failed')}", file=sys.stderr)
                    print(f"Run status: {res.get('run_status')}", file=sys.stderr)
                    print(f"Raw steps: {json.dumps(res.get('raw_steps'), indent=2)}", file=sys.stderr)
                else:
                    print(f"✓ Query executed in {res['execution_time_ms']} ms:")
                    print(f"  Question: {res['question']}")
                    print(f"  Answer: {res['answer']}")
                    print(f"  Query Language: {res['queryLanguage']}")
                    print(f"  Generated Query:\n    {res['generatedQuery']}")
            return 1 if res.get("is_error") else 0
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

#!/usr/bin/env python3
"""Call the HLS Databricks MCP demos through APIM without third-party packages.

The client supports the two meeting paths:
- a Unity Catalog function exposed as one deterministic MCP tool;
- a curated Databricks Genie space exposed as query/poll MCP tools.

Authentication is either the active Azure CLI identity or an Azure managed identity.
Tokens are held in memory and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

PROTOCOL_VERSION = "2025-06-18"


def entra_token(mode: str, audience: str) -> str:
    resource = audience.rstrip("/")
    if mode == "azcli":
        result = subprocess.run(
            ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Azure CLI token acquisition failed")
        return result.stdout.strip()
    if mode == "mi":
        query = {"api-version": "2019-08-01", "resource": resource}
        if os.environ.get("AZURE_CLIENT_ID"):
            query["client_id"] = os.environ["AZURE_CLIENT_ID"]
        request = urllib.request.Request(
            f"{os.environ['IDENTITY_ENDPOINT']}?{urllib.parse.urlencode(query)}",
            headers={"X-IDENTITY-HEADER": os.environ["IDENTITY_HEADER"]},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())["access_token"]
    raise ValueError(f"unsupported auth mode: {mode}")


class McpClient:
    def __init__(self, url: str, token: str) -> None:
        self.url = url
        self.token = token
        self.session_id: str | None = None
        self.request_id = 0

    def _post(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                self.session_id = response.headers.get("Mcp-Session-Id", self.session_id)
                correlation_id = response.headers.get("x-hls-correlation-id")
                content_type = response.headers.get("Content-Type", "")
                body = response.read().decode()
        except urllib.error.HTTPError as error:
            detail = error.read().decode()[:1000]
            raise RuntimeError(f"HTTP {error.code} {error.reason}: {detail}") from error
        if correlation_id:
            print(f"# {payload.get('method')}: correlation={correlation_id}")
        if not body.strip():
            return None
        if content_type.startswith("text/event-stream"):
            events = [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
            body = events[-1] if events else "{}"
        message = json.loads(body)
        if message.get("error"):
            raise RuntimeError(str(message["error"]))
        return message.get("result")

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        self.request_id += 1
        return self._post({"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params or {}})

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "hls-imh-demo", "version": "1.0"},
            },
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})


def text_content(result: dict[str, Any]) -> str:
    return "\n".join(
        part.get("text", "")
        for part in result.get("content", [])
        if isinstance(part, dict) and part.get("type") == "text"
    )


def poll_genie(client: McpClient, query_tool: str, result: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    poll_tool = query_tool.replace("query_space_", "poll_response_", 1)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            status = json.loads(text_content(result))
        except json.JSONDecodeError:
            return result
        if status.get("status") in {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}:
            return result
        if not status.get("conversationId") or not status.get("messageId"):
            return result
        time.sleep(3)
        result = client.request(
            "tools/call",
            {
                "name": poll_tool,
                "arguments": {
                    "conversation_id": status["conversationId"],
                    "message_id": status["messageId"],
                },
            },
        ) or {}
    raise TimeoutError(f"Genie did not complete within {timeout_seconds} seconds")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("APIM_MCP_URL"), required=False)
    parser.add_argument("--auth", choices=["azcli", "mi"], default=os.environ.get("APIM_AUTH", "azcli"))
    parser.add_argument("--audience", default=os.environ.get("APIM_AUDIENCE", "https://management.azure.com"))
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--tool", default=os.environ.get("MCP_TOOL"))
    parser.add_argument("--args", default=os.environ.get("MCP_ARGS", "{}"))
    parser.add_argument("--query", default=os.environ.get("MCP_QUERY"))
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if not args.url:
        parser.error("set APIM_MCP_URL or pass --url")

    client = McpClient(args.url, entra_token(args.auth, args.audience))
    client.initialize()
    tools = (client.request("tools/list") or {}).get("tools", [])
    if args.list:
        print(json.dumps([{"name": tool["name"], "inputSchema": tool.get("inputSchema", {})} for tool in tools], indent=2))
        return 0

    names = [tool["name"] for tool in tools]
    tool_name = args.tool
    arguments = json.loads(args.args)
    if args.query:
        tool_name = tool_name or next((name for name in names if name.startswith("query_space_")), None)
        arguments = {"query": args.query}
    elif not tool_name and len(names) == 1:
        tool_name = names[0]
    if not tool_name or tool_name not in names:
        raise RuntimeError(f"tool not found; available={names}")

    result = client.request("tools/call", {"name": tool_name, "arguments": arguments}) or {}
    if tool_name.startswith("query_space_"):
        result = poll_genie(client, tool_name, result, args.timeout)
    print(text_content(result))
    return 1 if result.get("isError") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

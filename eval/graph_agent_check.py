"""Grounded graph-agent checks using its published MCP tool schema."""
import re


def _answer(response):
    result = response.get("result") or {}
    text = "\n".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text").strip()
    if response.get("error") or result.get("isError") or not text:
        raise RuntimeError(text or response.get("error") or "empty graph answer")
    return text


def check_graph_agent(az, ws_id, items, log, mcp_jsonrpc, expected_association_count):
    agents = [i for i in items if i["type"] == "DataAgent" and i["displayName"] == "Healthcare Graph Agent"]
    results = []
    try:
        if len(agents) != 1:
            raise RuntimeError("Expected exactly one Healthcare Graph Agent")
        agent = agents[0]
        endpoint = f"https://api.fabric.microsoft.com/v1/mcp/workspaces/{ws_id}/dataagents/{agent['id']}/agent"
        token = az.token("https://api.fabric.microsoft.com")
        initialized = mcp_jsonrpc(endpoint, token, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "hls-graph-eval", "version": "1.0"}}})
        if initialized.get("error"):
            raise RuntimeError(initialized["error"])
        mcp_jsonrpc(endpoint, token, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        listed = mcp_jsonrpc(endpoint, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = (listed.get("result") or {}).get("tools") or []
        if len(tools) != 1:
            raise RuntimeError("Graph agent must expose one MCP tool")
        tool = tools[0]
        properties = tool.get("inputSchema", {}).get("properties", {})
        argument = next((n for n in properties if "question" in n.lower()), None) or (next(iter(properties)) if len(properties) == 1 else None)
        if not argument:
            raise RuntimeError("Graph tool question argument is ambiguous")
        questions = [
            "Using only DevicePayerOntology, count all DeviceAssoc entities. Return the integer count and identify the ontology source.",
            "Using only DevicePayerOntology, return one actual DeviceAssoc entity's assocPatientId and deviceRef. Do not invent IDs.",
            "Use DevicePayerOntology to count Patient entities and linkedToDevice relationships. Then separately query TelemetryRaw in MasimoEventhouse for the last five minutes using EventEnqueuedUtcTime, and report the distinct currently reporting devices. Name the source for every result.",
        ]
        answers = []
        for index, question in enumerate(questions, 3):
            answer = None
            response = None
            for _ in range(3):
                response = mcp_jsonrpc(endpoint, token, {"jsonrpc": "2.0", "id": index, "method": "tools/call", "params": {
                    "name": tool["name"], "arguments": {argument: question}}})
                candidate = _answer(response)
                if not any(term in candidate.lower() for term in ("not able", "cannot", "can't", "failed", "no data")):
                    answer = candidate
                    break
            answers.append({"question": question, "answer": answer or _answer(response), "rawResponse": response})
        count_match = re.search(r"\b(\d+)\b", answers[0]["answer"])
        association_count = int(count_match.group(1)) if count_match else None
        id_match = re.search(r"assocPatientId\s*[:` ]+([0-9a-f-]{36})", answers[1]["answer"], re.I)
        device_match = re.search(r"deviceRef\s*[:` ]+(MASIMO-[A-Z0-9-]+)", answers[1]["answer"], re.I)
        mixed_answer = answers[2]["answer"].lower()
        mixed_counts = [int(v) for v in re.findall(r"\b\d+\b", mixed_answer)]
        mixed_grounded = (
            "devicepayerontology" in mixed_answer
            and "masimoeventhouse" in mixed_answer
            and mixed_counts.count(expected_association_count) >= 2
        )
        passed = association_count == expected_association_count and bool(id_match and device_match) and mixed_grounded
        results.append({"agent": agent["displayName"], "status": "PASS" if passed else "FAIL",
                        "expectedAssociationCount": expected_association_count, "associationCount": association_count,
                        "patientId": id_match.group(1) if id_match else None, "deviceId": device_match.group(1) if device_match else None,
                        "mixedSourceGrounded": mixed_grounded, "queries": answers})
    except Exception as exc:
        results.append({"status": "FAIL", "reason": str(exc)})
    return {"category": "graph_agent", "passed": bool(results) and all(r["status"] == "PASS" for r in results), "results": results}

"""OperationsAgent conversation acceptance checks."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def validate_operations_agents(items, evidence_path=None, max_age_seconds=3600):
    agents = [item for item in items if item["type"] == "OperationsAgent"]
    results = []
    try:
        if not agents:
            raise RuntimeError("No OperationsAgent item found")
        if not evidence_path:
            raise RuntimeError("Fresh OperationsAgent API evidence is required; CLI Power BI tokens cannot authenticate to the dedicated MwcToken backend")
        evidence = json.loads(Path(evidence_path).read_text())
        captured = datetime.fromisoformat(evidence["capturedAt"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - captured).total_seconds()
        if age < 0 or age > max_age_seconds:
            raise RuntimeError("OperationsAgent API evidence is stale or future-dated")
        by_id = {row["agentId"]: row for row in evidence.get("agents", [])}
        for agent in agents:
            row = by_id.get(agent["id"], {})
            answer = row.get("answer") or ""
            configuration = row.get("configuration") or {}
            rejected = ("not available", "not accessible", "cannot", "can't", "unable", "no playbook", "not configured")
            passed = (row.get("sessionStatus") in (200, 201) and row.get("messageStatus") in (200, 201, 202)
                      and row.get("finalStatus") == "complete" and len(answer) >= 80
                      and not any(term in answer.lower() for term in rejected)
                      and bool(configuration.get("playbookId"))
                      and len(configuration.get("instructions", "")) >= 120
                      and bool(configuration.get("dataSources")))
            results.append({"agent": agent["displayName"], "status": "PASS" if passed else "FAIL", "evidence": row})
    except Exception as exc:
        results.append({"status": "FAIL", "reason": str(exc)})
    return {"category": "operations_agents", "passed": bool(results) and all(r["status"] == "PASS" for r in results), "results": results}

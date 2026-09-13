"""Live deployment, report-layout, and browser-evidence acceptance checks."""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def category(name, results):
    return {"category": name, "passed": bool(results) and all(r["status"] == "PASS" for r in results), "results": results}


def orchestrator_checks(base_url, workspace, resource_group):
    results = []

    def request(path, body=None):
        req = urllib.request.Request(base_url.rstrip("/") + path,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=240) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            return json.load(error)

    try:
        auth = request("/api/auth/context?force=true")
        results.append({"check": "Azure identity alignment", "status": "PASS" if auth.get("ready") else "FAIL", "evidence": auth})
        runs = request("/api/deployments")
        if not isinstance(runs, list) or not runs:
            raise RuntimeError("No deployment history available")
        latest = max(runs, key=lambda r: r.get("createdTime", ""))
        if latest.get("name") == "teardown_batch":
            batch = request("/api/teardown/batch/" + latest["instanceId"])
            latest = batch["batch"]
            evaluated_runs = batch.get("children", [])
            if not evaluated_runs:
                raise RuntimeError("Latest teardown batch has no child runs")
        else:
            evaluated_runs = [latest]
        errors = [entry for run in evaluated_runs for entry in (run.get("customStatus") or {}).get("logs", [])
                  if str(entry.get("level", "")).lower() == "error"]
        completed = latest.get("runtimeStatus") == "Completed" and all(r.get("runtimeStatus") == "Completed" for r in evaluated_runs)
        results.append({"check": "Latest deployment or teardown", "status": "PASS" if completed and not errors else "FAIL",
                        "instanceId": latest["instanceId"], "runtimeStatus": latest.get("runtimeStatus"), "errorLogs": errors})
        preflight = request("/api/deploy/preflight", {"fabric_workspace_name": workspace,
                            "resource_group_name": resource_group, "location": "westus2"})
        checks = preflight.get("checks") or []
        passed = preflight.get("passed") and checks and all(c.get("status") == "pass" for c in checks)
        passed = passed and not preflight.get("failures") and not preflight.get("warnings")
        results.append({"check": "All preflight checks", "status": "PASS" if passed else "FAIL",
                        "checks": checks, "failures": preflight.get("failures"), "warnings": preflight.get("warnings")})
    except Exception as exc:
        results.append({"check": "Orchestrator availability", "status": "FAIL", "reason": str(exc)})
    return category("deployment_preflight", results)


def report_layout_checks(az, workspace_id, items, http, fabric_api):
    results = []
    for item in items:
        if item["type"] != "Report":
            continue
        try:
            token = az.token("https://api.fabric.microsoft.com")
            url = f"{fabric_api}/workspaces/{workspace_id}/reports/{item['id']}/getDefinition"
            request = urllib.request.Request(url, data=b"", method="POST", headers={"Authorization": "Bearer " + token})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read()
                payload = json.loads(raw) if raw else {}
                status, location = response.status, response.headers.get("Location")
            if status == 202:
                if not location:
                    raise RuntimeError("Definition response omitted operation Location")
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    code, operation = http("GET", location, token)
                    if code != 200 or operation.get("status") in ("Failed", "Cancelled"):
                        raise RuntimeError(f"Definition operation failed: {operation}")
                    if operation.get("status") == "Succeeded":
                        code, payload = http("GET", location + "/result", token)
                        if code != 200:
                            raise RuntimeError(f"Definition result HTTP {code}")
                        break
                    time.sleep(2)
                else:
                    raise TimeoutError("Report definition operation timed out")
            parts = {part["path"]: json.loads(base64.b64decode(part["payload"]))
                     for part in payload["definition"]["parts"] if part["path"].endswith(".json")}
            pages = parts.get("definition/pages/pages.json", {}).get("pageOrder", [])
            if pages:
                for page in pages:
                    visuals = [value for path, value in parts.items() if path.startswith(f"definition/pages/{page}/visuals/")]
                    analytic = [visual for visual in visuals if (visual.get("visual") or {}).get("visualType") not in ("textbox", "shape", "image", "actionButton")]
                    results.append({"check": "Multi-visual report page", "report": item["displayName"], "reportId": item["id"],
                                    "page": page, "analyticVisuals": len(analytic), "status": "PASS" if len(analytic) > 1 else "FAIL"})
                continue
            legacy = parts.get("report.json", {}).get("sections", [])
            if not legacy:
                raise RuntimeError("Report definition has no enumerated pages")
            for page in legacy:
                count = len(page.get("visualContainers", []))
                results.append({"check": "Multi-visual report page", "report": item["displayName"], "reportId": item["id"],
                                "page": page.get("displayName") or page.get("name"), "analyticVisuals": count,
                                "status": "PASS" if count > 1 else "FAIL"})
        except Exception as exc:
            results.append({"check": "Report layout", "report": item["displayName"], "status": "FAIL", "reason": str(exc)})
    return category("report_layout", results)


def browser_evidence_checks(path, workspace_id, items, max_age_seconds=3600):
    """Fail closed unless a fresh BrakeKat browser run covers every report and three linked studies."""
    results = []
    try:
        if not path:
            raise RuntimeError("Browser evaluation evidence required; API row counts do not prove rendering")
        evidence = json.loads(Path(path).read_text())
        captured = datetime.fromisoformat(evidence["capturedAt"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - captured).total_seconds()
        if age < 0 or age > max_age_seconds:
            raise RuntimeError("Browser evidence is stale or future-dated")
        if evidence.get("workspaceId") != workspace_id or evidence.get("profile") != "Work - Brakekat":
            raise RuntimeError("Browser evidence belongs to a different workspace or profile")
        if "Edg/" not in evidence.get("userAgent", ""):
            raise RuntimeError("Browser evidence is not from Microsoft Edge")
        report_rows = {r["reportId"]: r for r in evidence.get("reports", [])}
        for item in items:
            if item["type"] != "Report":
                continue
            report = report_rows.get(item["id"], {})
            pages = report.get("pages") or []
            passed = bool(pages) and all(p.get("hasData") and not p.get("errors") and p.get("screenshot") for p in pages)
            results.append({"check": "Report rendering", "report": item["displayName"], "status": "PASS" if passed else "FAIL", "pages": pages})
        studies = evidence.get("ohifStudies") or []
        linked = [s for s in studies if s.get("fromReportId") in report_rows and s.get("studyInstanceUid")
                  and s.get("imageRendered") and s.get("screenshot")]
        results.append({"check": "Report-linked OHIF studies", "status": "PASS" if len({s['studyInstanceUid'] for s in linked}) >= 3 else "FAIL",
                        "studies": studies})
    except Exception as exc:
        results.append({"check": "Browser coverage", "status": "FAIL", "reason": str(exc)})
    return category("browser_surfaces", results)

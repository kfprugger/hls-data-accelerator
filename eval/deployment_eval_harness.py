#!/usr/bin/env python3
"""
Post-deployment evaluation harness for the HLS Data Accelerator.

Validates, for a target Fabric workspace, that the deployment's user-facing
surfaces actually WORK (not just that items exist):

  1. Reports        - every Power BI semantic model backing a report is queryable
                      via DAX and its visual-backing tables return rows (catches
                      blank/unrepaired visuals and Direct Lake connection breaks).
  2. Data Agents    - every Data Agent answers a natural-language test query end to
                      end (catches unpublished/draft agents -> "Stage configuration
                      not found").
  3. RTI dashboards - every KQL dashboard's backing tables/functions return data
                      (TelemetryRaw, AlertHistory, claims_events, fn_AlertLocationMap,
                      fn_PayerOpsWorklist, PatientLocationDashboard).

Auth: uses the local Azure CLI (isolated BrakeKat profile by default) to mint
tokens for three resources — Fabric, Power BI, and the Eventhouse (Kusto).

Exit code 0 = all checks passed; 1 = one or more failures; 2 = harness/setup error.

Usage:
  python3 eval/deployment_eval_harness.py --workspace med-0719
  python3 eval/deployment_eval_harness.py --workspace med-0719 --json-out eval/last_run.json
  python3 eval/deployment_eval_harness.py --workspace med-0719 --skip agents
"""
from __future__ import annotations
import argparse, json, os, ssl, subprocess, sys, time, urllib.request, urllib.error
from surface_checks import orchestrator_checks, report_layout_checks, browser_evidence_checks
from operations_agent_check import validate_operations_agents
from graph_agent_check import check_graph_agent

FABRIC_API = "https://api.fabric.microsoft.com/v1"
PBI_API = "https://api.powerbi.com/v1.0/myorg"
FABRIC_RESOURCE = "https://api.fabric.microsoft.com"
PBI_RESOURCE = "https://analysis.windows.net/powerbi/api"
DB_RESOURCE = "https://database.windows.net"
AGENT_API_VERSION = "2024-05-01-preview"
CAPACITY_ID = ("/subscriptions/5772d06a-5513-4cc5-ac08-a3805440c60e/resourceGroups/"
               "rg-fabricskus/providers/Microsoft.Fabric/capacities/fabrjbwu2")

_CTX = ssl.create_default_context()


class Az:
    """Azure CLI token minter honoring an isolated config dir."""
    def __init__(self, config_dir: str | None):
        self.env = dict(os.environ)
        if config_dir:
            self.env["AZURE_CONFIG_DIR"] = config_dir
        self._cache: dict[str, tuple[float, str]] = {}

    def token(self, resource: str) -> str:
        # cache ~40 min (tokens live 60-75 min)
        hit = self._cache.get(resource)
        if hit and time.time() - hit[0] < 2400:
            return hit[1]
        out = subprocess.run(
            ["az", "account", "get-access-token", "--resource", resource,
             "--query", "accessToken", "-o", "tsv"],
            capture_output=True, text=True, env=self.env, timeout=60)
        tok = out.stdout.strip()
        if not tok:
            raise RuntimeError(f"az token failed for {resource}: {out.stderr.strip()[:200]}")
        self._cache[resource] = (time.time(), tok)
        return tok

    def run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, env=self.env, timeout=120)


def http(method: str, url: str, token: str, body=None, timeout=90):
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    elif method == "POST":
        data = b""
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, context=_CTX, timeout=timeout)
        raw = r.read()
        return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw[:400]}


def ensure_capacity_active(az: Az, log, *, resume: bool = True) -> bool:
    """The F64 capacity backing these workspaces auto-pauses; Direct Lake reads,
    KQL queries, and agent runs all fail when it is Paused. Resume if needed."""
    out = az.run(["az", "resource", "show", "--ids", CAPACITY_ID,
                  "--query", "properties.state", "-o", "tsv"])
    state = out.stdout.strip()
    log(f"capacity fabrjbwu2 state: {state or '(unknown)'}")
    if out.returncode == 0 and state == "Active":
        return True
    if out.returncode or not state:
        log("  ERROR: could not read capacity state; aborting")
        return False
    if not resume:
        log("  ERROR: capacity is not Active and automatic resume is disabled")
        return False
    log(f"  capacity is {state}; resuming...")
    resumed = az.run(["az", "resource", "invoke-action", "--action", "resume",
                      "--ids", CAPACITY_ID, "--no-wait"])
    if resumed.returncode:
        log(f"  ERROR: capacity resume failed: {resumed.stderr.strip()[:300]}")
        return False
    for _ in range(12):
        time.sleep(20)
        s = az.run(["az", "resource", "show", "--ids", CAPACITY_ID,
                    "--query", "properties.state", "-o", "tsv"]).stdout.strip()
        if s == "Active":
            log("  capacity resumed -> Active")
            return True
    log("  ERROR: capacity did not reach Active")
    return False


def find_workspace(az: Az, name: str) -> str | None:
    _, data = http("GET", f"{FABRIC_API}/workspaces", az.token(FABRIC_RESOURCE))
    for w in data.get("value", []):
        if w.get("displayName") == name:
            return w["id"]
    return None


def list_items(az: Az, ws_id: str) -> list[dict]:
    _, data = http("GET", f"{FABRIC_API}/workspaces/{ws_id}/items", az.token(FABRIC_RESOURCE))
    return data.get("value", [])


def _dax(az: Az, model_id: str, query: str):
    body = {"queries": [{"query": query}], "serializerSettings": {"includeNulls": True}}
    st, data = http("POST", f"{PBI_API}/datasets/{model_id}/executeQueries",
                    az.token(PBI_RESOURCE), body)
    if st != 200:
        return None, json.dumps(data)[:300]
    try:
        return data["results"][0]["tables"][0]["rows"], None
    except Exception:
        return None, json.dumps(data)[:200]


def _user_tables(az: Az, model_id: str) -> list[str]:
    rows, err = _dax(az, model_id, "EVALUATE INFO.VIEW.TABLES()")
    if err or not rows:
        return []
    names = []
    for row in rows:
        key = next((column for column in row if "Name" in column), None)
        if key and row[key]:
            names.append(row[key])
    return [name for name in names if "Date" not in name and not name.startswith("_")]


REQUIRED_REPORT_TABLES = {
    "healthcare1_msft_cma_semantic_model": {"person", "cost", "visit_occurrence", "measurement", "social_determinant"},
    "healthcare1_msft_poa_semantic_model": {"PatientDim", "AppointmentDim", "AppointmentTransitionFact", "JourneyDim", "MarketingEventFact"},
    "ImagingReport": {"Patient", "ImagingStudy", "DicomFile"},
    "Population Health & Quality Semantic Model": {"fact_claim", "agg_quality_summary", "care_gaps", "dim_payer", "agg_medication_adherence", "agg_risk_scores", "readmission_risk_scores", "agg_utilization_summary"},
}


def validate_reports(az: Az, ws_id: str, items: list[dict], log) -> dict:
    models = [item for item in items if item["type"] == "SemanticModel"]
    log(f"semantic models backing reports: {len(models)}")
    results = []
    for model in models:
        model_id, name = model["id"], model["displayName"]
        _, error = _dax(az, model_id, 'EVALUATE ROW("n", 1)')
        if error:
            results.append({"model": name, "status": "FAIL", "reason": f"semantic model not queryable: {error[:160]}"})
            continue
        tables = _user_tables(az, model_id)
        if not tables:
            results.append({"model": name, "status": "FAIL", "reason": "no user tables enumerated"})
            continue
        counts, errors = {}, {}
        for table in tables:
            rows, error = _dax(az, model_id, f'EVALUATE ROW("n", COUNTROWS(\'{table}\'))')
            if error:
                errors[table] = error
                counts[table] = None
            else:
                counts[table] = rows[0].get("[n]") if rows else None
        required = REQUIRED_REPORT_TABLES.get(name, set(tables))
        missing = sorted(table for table in required if not counts.get(table))
        status = "FAIL" if errors or missing else "PASS"
        nonempty = sum(bool(value) for value in counts.values())
        reason = f"{nonempty}/{len(tables)} tables have rows; " + ("required report facts populated" if not missing else "missing: " + ", ".join(missing))
        results.append({"model": name, "status": status, "counts": counts, "errors": errors,
                        "missingRequiredTables": missing, "emptyOptionalTables": sorted(table for table, count in counts.items() if not count and table not in required), "reason": reason})
        log(f"  [{status}] {name}: {reason}")
    return {"category": "reports", "passed": bool(results) and all(row["status"] == "PASS" for row in results), "results": results}


def mcp_jsonrpc(url: str, token: str, payload: dict, timeout: int = 300) -> dict:
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urllib.request.urlopen(request, context=_CTX, timeout=timeout) as response:
        raw = response.read().decode(errors="replace").strip()
        if not raw:
            return {}
        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("text/event-stream"):
            events = [json.loads(line[5:].strip()) for line in raw.splitlines() if line.startswith("data:") and line[5:].strip()]
            return events[-1] if events else {}
        if "application/json" not in content_type:
            return {"raw": raw}
        return json.loads(raw)


def agent_validation_question(name: str) -> str:
    if "Imaging" in name:
        return "Count imaging studies by modality from the connected imaging data. Include each count and the data source."
    if "Patient 360" in name:
        return "Count patients by gender without returning names or IDs. Include the data source."
    if "Clinical Triage" in name:
        return "Count distinct devices and TelemetryRaw rows from the last seven days. Include the data source and latest event timestamp."
    if "Payer" in name:
        return ("Compare the current claim event count by event_type from MasimoEventhouse with the historical "
                "total claim count and total paid amount from healthcare1_reporting_gold. Query each source "
                "separately, keep the grains separate, and name the source for every number.")
    if "Graph" in name:
        return "Using the ontology graph itself, count distinct patients and trace one patient-to-device relationship. Return grounded IDs and the ontology source."
    return "Count records in the primary connected dataset and identify the data source."


def agent_required_terms(name: str) -> tuple[str, ...]:
    """Terms that prove a prompt reached every required source family."""
    if "Payer" in name:
        return ("claims_events", "healthcare1_reporting_gold")
    return ()


def validate_agents(az: Az, ws_id: str, items: list[dict], log) -> dict:
    agents = [item for item in items if item["type"] == "DataAgent" and item["displayName"] != "Healthcare Graph Agent"]
    log(f"data agents: {len(agents)}")
    token = az.token(FABRIC_RESOURCE)
    results = []
    for agent in agents:
        agent_id, name = agent["id"], agent["displayName"]
        endpoint = f"{FABRIC_API}/mcp/workspaces/{ws_id}/dataagents/{agent_id}/agent"
        try:
            initialized = mcp_jsonrpc(endpoint, token, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "hls-deployment-eval", "version": "1.0"},
                },
            })
            if "error" in initialized:
                raise RuntimeError(initialized["error"])
            mcp_jsonrpc(endpoint, token, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            listed = mcp_jsonrpc(endpoint, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tools = ((listed.get("result") or {}).get("tools") or [])
            if len(tools) != 1:
                raise RuntimeError(f"expected one MCP tool, found {len(tools)}")
            tool = tools[0]
            properties = (tool.get("inputSchema") or {}).get("properties") or {}
            if not properties:
                raise RuntimeError("MCP tool input schema has no question property")
            argument_name = next(iter(properties))
            called = mcp_jsonrpc(endpoint, token, {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool["name"],
                    "arguments": {argument_name: agent_validation_question(name)},
                },
            })
            result = called.get("result") or {}
            answer = "\n".join(
                block.get("text", "")
                for block in result.get("content") or []
                if block.get("type") == "text"
            ).strip()
            rejected = ("not able", "cannot", "can't", "couldn't", "error", "rejected", "unavailable")
            grounded = any(term in answer.lower() for term in ("source", "lakehouse", "eventhouse", "ontology", "table"))
            missing_sources = [term for term in agent_required_terms(name) if term not in answer.lower()]
            if (result.get("isError") or called.get("error") or not answer
                    or any(term in answer.lower() for term in rejected) or not grounded or missing_sources):
                if missing_sources:
                    raise RuntimeError(f"missing required sources: {', '.join(missing_sources)}; answer={answer[:300]}")
                raise RuntimeError(answer or called.get("error") or "empty or ungrounded MCP response")
            results.append({"agent": name, "status": "PASS", "reason": f"Grounded MCP answer ({len(answer)} chars)",
                            "question": agent_validation_question(name), "answer": answer})
            log(f"  [PASS] {name}: grounded MCP answer ({len(answer)} chars)")
        except Exception as exc:
            results.append({"agent": name, "status": "FAIL", "reason": f"MCP validation failed: {str(exc)[:180]}"})
            log(f"  [FAIL] {name}: MCP {str(exc)[:80]}")
    passed = bool(results) and all(result["status"] == "PASS" for result in results)
    return {"category": "agents", "passed": passed, "results": results}


def _kql(az: Az, query_uri: str, db: str, csl: str, tries: int = 4):
    body = json.dumps({"db": db, "csl": csl}).encode()
    last_err = None
    for attempt in range(tries):
        req = urllib.request.Request(f"{query_uri}/v1/rest/query", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {az.token(query_uri)}",
                                              "Content-Type": "application/json", "Accept": "application/json"})
        try:
            r = urllib.request.urlopen(req, context=_CTX, timeout=90)
            return json.loads(r.read())["Tables"][0]["Rows"], None
        except urllib.error.HTTPError as e:
            # HTTP errors (bad query, 404) are deterministic — do not retry
            return None, e.read().decode(errors="replace")[:160]
        except Exception as e:
            # transient transport blips (SSL EOF, reset, timeout) — retry with backoff
            last_err = str(e)[:120]
            if attempt < tries - 1:
                time.sleep(3 * (attempt + 1))
    return None, last_err


def validate_rti(az: Az, ws_id: str, items: list[dict], log) -> dict:
    """Every RTI/KQL dashboard's backing Eventhouse tables/functions return data."""
    dashboards = [i for i in items if i["type"] == "KQLDashboard"]
    ehs = [i for i in items if i["type"] == "Eventhouse"]
    log(f"RTI dashboards: {len(dashboards)} | eventhouses: {len(ehs)}")
    if not ehs:
        return {"category": "rti", "passed": False, "results": [{"status": "FAIL", "reason": "no eventhouse"}]}
    _, det = http("GET", f"{FABRIC_API}/workspaces/{ws_id}/eventhouses/{ehs[0]['id']}", az.token(FABRIC_RESOURCE))
    quri = (det.get("properties") or {}).get("queryServiceUri")
    db = ehs[0]["displayName"]
    if not quri:
        return {"category": "rti", "passed": False, "results": [{"status": "FAIL", "reason": "no queryServiceUri"}]}
    tbl_rows, _ = _kql(az, quri, db, ".show tables | project TableName")
    existing = {r[0] for r in (tbl_rows or [])}
    fn_rows, _ = _kql(az, quri, db, ".show functions | project Name")
    fns = {r[0] for r in (fn_rows or [])}
    checks = [("TelemetryRaw", "TelemetryRaw | count", True),
              ("AlertHistory", "AlertHistory | count", True),
              ("claims_events", "claims_events | count", False),
              ("PatientLocationDashboard", "PatientLocationDashboard | count", False)]
    fn_checks = [("fn_AlertLocationMap", "fn_AlertLocationMap(10080) | count", False),
                 ("fn_PayerOpsWorklist", "fn_PayerOpsWorklist(10080) | count", False)]
    results = []
    for name, csl, must in checks:
        if name not in existing:
            results.append({"check": name, "status": "SKIP", "reason": "table not present"}); continue
        rows, err = _kql(az, quri, db, csl)
        n = rows[0][0] if rows else None
        if err:
            results.append({"check": name, "status": "FAIL", "reason": f"query error: {err[:100]}"}); log(f"  [FAIL] {name}: {err[:60]}")
        elif must and not n:
            results.append({"check": name, "status": "FAIL", "reason": "table empty", "rows": n}); log(f"  [FAIL] {name}: empty")
        else:
            results.append({"check": name, "status": "PASS", "rows": n}); log(f"  [PASS] {name}: rows={n}")
    for name, csl, must in fn_checks:
        if name not in fns:
            results.append({"check": name, "status": "SKIP", "reason": "function not present"}); continue
        rows, err = _kql(az, quri, db, csl)
        n = rows[0][0] if rows else None
        if err:
            results.append({"check": name, "status": "FAIL", "reason": f"query error: {err[:100]}"}); log(f"  [FAIL] {name}: {err[:60]}")
        else:
            results.append({"check": name, "status": "PASS", "rows": n}); log(f"  [PASS] {name}: rows={n}")
    passed = not any(r["status"] == "FAIL" for r in results)
    return {"category": "rti", "passed": passed, "results": results,
            "dashboards": [d["displayName"] for d in dashboards]}


def ensure_telemetry_ready(az: Az, ws_id: str, items: list[dict], rg: str, sub: str | None, timeout_sec: int, log) -> dict:
    """Start both producers and require running streams with current destination events."""
    result = {"category": "telemetry_readiness", "passed": False, "results": [], "actions": []}
    deadline = time.monotonic() + timeout_sec
    required = {
        "MasimoTelemetryStream": ("masimo-emulator-grp", "TelemetryRaw", "timestamp"),
        "ClaimsRTIStream": ("claim-emulator-grp", "claims_events", "event_timestamp"),
    }
    started, resumed, resetting = set(), set(), set()

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError("Telemetry readiness deadline exceeded; report evaluation blocked")
        return seconds

    def container_command(action, name, *extra):
        remaining()
        command = ["az", "container", action, "--name", name, "--resource-group", rg, *extra]
        if sub:
            command += ["--subscription", sub]
        response = az.run(command)
        if response.returncode:
            raise RuntimeError(f"{name} {action} failed: {response.stderr.strip()[:300]}")
        return response.stdout

    try:
        streams = [item for item in items if item["type"] == "Eventstream"]
        for name in required:
            if sum(item["displayName"] == name for item in streams) != 1:
                raise RuntimeError(f"Expected exactly one {name} Eventstream")

        # Resolve the actual Eventhouse owning each destination database, not the first item.
        databases = {}
        for item in items:
            if item["type"] != "Eventhouse":
                continue
            status, data = http("GET", f"{FABRIC_API}/workspaces/{ws_id}/eventhouses/{item['id']}",
                                az.token(FABRIC_RESOURCE), timeout=min(90, remaining()))
            properties = data.get("properties") or {}
            if status != 200 or not properties.get("queryServiceUri"):
                raise RuntimeError(f"Cannot resolve Eventhouse {item['displayName']}: HTTP {status}")
            for database_id in properties.get("databasesItemIds", []):
                databases[database_id] = properties["queryServiceUri"]

        while True:
            remaining()
            observations = []
            result["results"] = observations
            for producer, _, _ in required.values():
                state = json.loads(container_command(
                    "show", producer, "--query",
                    "{state:instanceView.state,containers:containers[].instanceView.currentState.state}", "-o", "json"))
                if not state.get("state") or not state.get("containers"):
                    raise RuntimeError(f"{producer}: container runtime state is unavailable")
                running = state["state"] == "Running" and all(s == "Running" for s in state["containers"])
                observations.append({"check": producer, "status": "PASS" if running else "WAIT", "state": state})
                if not running and producer not in started:
                    container_command("start", producer, "--no-wait")
                    started.add(producer)
                    result["actions"].append({"producer": producer, "action": "start"})
                    log(f"  starting producer {producer}")

            destinations = {}
            for stream in streams:
                name, stream_id = stream["displayName"], stream["id"]
                url = f"{FABRIC_API}/workspaces/{ws_id}/eventstreams/{stream_id}"
                status, topology = http("GET", url + "/topology", az.token(FABRIC_RESOURCE),
                                        timeout=min(90, remaining()))
                if status != 200:
                    raise RuntimeError(f"{name} topology failed: HTTP {status}: {topology}")
                groups = [topology.get(kind) or [] for kind in ("sources", "streams", "destinations")]
                if not all(groups):
                    raise RuntimeError(f"{name}: topology must contain sources, streams, and destinations")
                nodes = [node for group in groups for node in group]
                states = [{"name": node.get("name"), "status": node.get("status")} for node in nodes]
                if any(node.get("status") in ("Error", "Failed") for node in nodes):
                    raise RuntimeError(f"{name}: failed topology nodes: {states}")
                running = all(node.get("status") == "Running" for node in nodes)
                observations.append({"check": name, "id": stream_id, "status": "PASS" if running else "WAIT", "nodes": states})
                if (any(node.get("status") in ("Paused", "Stopped") for node in nodes)
                        and not any(node.get("status") in ("Pausing", "Resuming") for node in nodes)
                        and stream_id not in resumed):
                    status, body = http("POST", url + "/resume", az.token(FABRIC_RESOURCE),
                                        {"startType": "Now"}, timeout=min(90, remaining()))
                    if status not in (200, 202):
                        raise RuntimeError(f"{name} resume failed: HTTP {status}: {body}")
                    resumed.add(stream_id)
                    result["actions"].append({"eventstream": name, "action": "resume", "startType": "Now"})
                    log(f"  resuming {name} from Now (test policy: skip queued history)")
                if name in required:
                    _, table, column = required[name]
                    matches = [node.get("properties") or {} for node in groups[2]
                               if node.get("type") == "Eventhouse"
                               and (node.get("properties") or {}).get("tableName") == table]
                    if len(matches) != 1 or matches[0].get("workspaceId") != ws_id:
                        raise RuntimeError(f"{name}: expected one {table} destination in the target workspace")
                    destination = matches[0]
                    query_uri = databases.get(destination.get("itemId"))
                    if not query_uri or not destination.get("databaseName"):
                        raise RuntimeError(f"{name}: destination database could not be resolved")
                    destinations[table] = (query_uri, destination["databaseName"], column, name, stream_id)

            if all(row["status"] == "PASS" for row in observations):
                # Sample both streams in the same poll; never retain a stale earlier PASS.
                for table, (query_uri, database, column, name, stream_id) in destinations.items():
                    remaining()
                    query = (
                        f"{table} | where ingestion_time() > ago(5m) "
                        f"| extend event_time=todatetime({column}) "
                        "| summarize latest_event=max(event_time), latest_ingestion=max(ingestion_time()), "
                        "recent_events=countif(event_time between (ago(5m) .. now())), "
                        "backlog_events=countif(event_time < ago(5m))"
                    )
                    rows, error = _kql(az, query_uri, database, query, tries=1)
                    if error:
                        raise RuntimeError(f"{table} freshness query failed: {error}")
                    latest, ingested, count, backlog = rows[0] if rows and len(rows[0]) == 4 else (None, None, 0, 0)
                    observations.append({
                        "check": f"fresh_data_{table}", "status": "PASS" if count and count > 0 else "WAIT",
                        "query": query, "database": database, "latestEvent": latest,
                        "latestIngestion": ingested, "recentEvents": count or 0, "backlogEvents": backlog or 0,
                    })
                    log(f"  {table}: {count or 0} recent events; latest event={latest}, ingestion={ingested}")
                    if not count and backlog and stream_id not in resetting and stream_id not in resumed:
                        # Test streams should not spend the evaluation window replaying old events.
                        status, body = http("POST",
                                            f"{FABRIC_API}/workspaces/{ws_id}/eventstreams/{stream_id}/pause",
                                            az.token(FABRIC_RESOURCE), timeout=min(90, remaining()))
                        if status not in (200, 202):
                            raise RuntimeError(f"{name} pause for Resume from Now failed: HTTP {status}: {body}")
                        resetting.add(stream_id)
                        result["actions"].append({"eventstream": name, "action": "pause_for_resume_now"})
                        log(f"  resetting stale {name} so the next resume starts from Now")
                remaining()
                if all(row["status"] == "PASS" for row in observations):
                    result["passed"] = True
                    return result
            log("  waiting for both telemetry streams to be live-ready...")
            time.sleep(min(15, remaining()))
    except Exception as exc:
        result["results"].append({"check": "telemetry_readiness", "status": "FAIL", "reason": str(exc)})
        return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-deployment eval harness")
    ap.add_argument("--workspace", required=True, help="Fabric workspace display name (e.g. med-0719)")
    ap.add_argument("--resource-group", default=None, help="Azure resource group (default: rg-{workspace})")
    ap.add_argument("--operations-evidence", help="Fresh authenticated OperationsAgent API result JSON")
    ap.add_argument("--subscription", default=None, help="Azure subscription ID for container lookups")
    ap.add_argument("--expected-device-associations", type=int, default=100)
    ap.add_argument("--readiness-timeout", type=int, default=600, help="timeout for telemetry readiness (seconds)")
    ap.add_argument("--azure-config-dir", default="/Users/joey/.azure-isolated/BrakeKat")
    ap.add_argument("--json-out", default=None, help="write full results JSON here")
    ap.add_argument("--orchestrator-url", default="http://127.0.0.1:7071")
    ap.add_argument("--browser-evidence", help="Fresh Edge BrakeKat report/OHIF evaluation JSON")
    ap.add_argument("--skip", action="append", default=[], choices=["reports", "agents", "rti", "deployment", "browser"],
                    help="skip a category (repeatable)")
    ap.add_argument("--no-capacity-resume", action="store_true", help="do not auto-resume the capacity")
    args = ap.parse_args()
    if args.readiness_timeout <= 0:
        ap.error("--readiness-timeout must be greater than zero")

    def log(m): print(m, flush=True)
    az = Az(args.azure_config_dir)
    log(f"=== deployment eval harness :: workspace={args.workspace} :: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} ===")
    try:
        if not ensure_capacity_active(az, log, resume=not args.no_capacity_resume):
            log("ABORT: capacity not Active"); return 2
        ws_id = find_workspace(az, args.workspace)
        if not ws_id:
            log(f"ABORT: workspace '{args.workspace}' not found"); return 2
        log(f"workspace id: {ws_id}")
        items = list_items(az, ws_id)
        log(f"items: {len(items)}")
        
        rg = args.resource_group or f"rg-{args.workspace}"
        log(f"\n--- TELEMETRY READINESS ---")
        t_ready = ensure_telemetry_ready(az, ws_id, items, rg, args.subscription, args.readiness_timeout, log)
        if not t_ready["passed"]:
            log("\nABORT: Telemetry readiness gate failed.")
            overall = False
            categories = [t_ready]
            summary = {"workspace": args.workspace, "workspaceId": ws_id,
                       "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "overallPassed": overall, "categories": categories}
            if args.json_out:
                with open(args.json_out, "w") as f:
                    json.dump(summary, f, indent=2)
                log(f"  wrote {args.json_out}")
            return 1
        categories = [t_ready]
    except Exception as e:
        log(f"ABORT: setup failed: {e}"); return 2

    if "deployment" not in args.skip:
        log("\n--- DEPLOYMENT AND PREFLIGHT ---")
        categories.append(orchestrator_checks(args.orchestrator_url, args.workspace, rg))
    if "reports" not in args.skip:
        log("\n--- REPORTS ---"); categories.append(validate_reports(az, ws_id, items, log))
        categories.append(report_layout_checks(az, ws_id, items, http, FABRIC_API))
    if "rti" not in args.skip:
        log("\n--- RTI DASHBOARDS ---"); categories.append(validate_rti(az, ws_id, items, log))
    if "agents" not in args.skip:
        log("\n--- DATA AGENTS ---"); categories.append(validate_agents(az, ws_id, items, log))
        categories.append(validate_operations_agents(items, args.operations_evidence))
        categories.append(check_graph_agent(az, ws_id, items, log, mcp_jsonrpc, args.expected_device_associations))
    if "browser" not in args.skip:
        log("\n--- REPORT AND OHIF RENDERING ---")
        categories.append(browser_evidence_checks(args.browser_evidence, ws_id, items))


    overall = all(c["passed"] for c in categories)
    summary = {"workspace": args.workspace, "workspaceId": ws_id,
               "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "overallPassed": overall, "categories": categories}
    log("\n=== SUMMARY ===")
    for c in categories:
        not_passing = sum(1 for r in c["results"] if r.get("status") != "PASS")
        log(f"  {c['category']:8} {'PASS' if c['passed'] else 'FAIL'}  ({not_passing} checks not passing)")
    log(f"  OVERALL: {'PASS' if overall else 'FAIL'}")
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(summary, f, indent=2)
        log(f"  wrote {args.json_out}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())

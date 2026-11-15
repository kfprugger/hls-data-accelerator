"""Behavioral regressions for the pre-report telemetry gate."""
import json
import os
import subprocess
import unittest
from unittest.mock import Mock, patch
import deployment_eval_harness as harness


class TelemetryReadinessTests(unittest.TestCase):
    def test_resume_waits_for_all_pause_transitions(self):
        """A paused destination does not mean a still-pausing source can resume."""
        items = [
            {"id": "masimo", "type": "Eventstream", "displayName": "MasimoTelemetryStream"},
            {"id": "claims", "type": "Eventstream", "displayName": "ClaimsRTIStream"},
            {"id": "eventhouse", "type": "Eventhouse", "displayName": "MasimoEventhouse"},
        ]
        az = Mock()
        az.run.return_value = subprocess.CompletedProcess(
            [], 0, json.dumps({"state": "Running", "containers": ["Running"]}), "")
        az.token.return_value = "test-token"
        polls = 0
        resumed = False

        def http(method, url, token, body=None, timeout=90):
            nonlocal polls, resumed
            if "/eventhouses/" in url:
                return 200, {"properties": {
                    "queryServiceUri": "https://test.kusto.invalid",
                    "databasesItemIds": ["database"],
                }}
            if url.endswith("/resume"):
                if polls < 2:
                    return 409, {"errorCode": "ArtifactOperationConflict"}
                resumed = True
                return 200, {}
            masimo = "/masimo/" in url
            if masimo:
                polls += 1
            source_state = "Running" if not masimo or resumed else ("Pausing" if polls == 1 else "Paused")
            destination_state = "Running" if not masimo or resumed else "Paused"
            return 200, {
                "sources": [{"name": "source", "status": source_state}],
                "streams": [{"name": "stream", "status": "Running"}],
                "destinations": [{
                    "name": "destination", "status": destination_state, "type": "Eventhouse",
                    "properties": {"workspaceId": "workspace", "itemId": "database",
                                   "databaseName": "MasimoEventhouse",
                                   "tableName": "TelemetryRaw" if masimo else "claims_events"},
                }],
            }

        with patch.object(harness, "http", side_effect=http), \
             patch.object(harness, "_kql", return_value=([["current", "current", 10, 0]], None)), \
             patch.object(harness.time, "sleep"):
            result = harness.ensure_telemetry_ready(
                az, "workspace", items, "rg-test", None, 30, lambda _: None)

        self.assertTrue(result["passed"], result)
        self.assertEqual(result["actions"], [{
            "eventstream": "MasimoTelemetryStream", "action": "resume", "startType": "Now",
        }])

    def _run_masimo_topologies(self, masimo_states):
        """Run the gate with Masimo node states (source, stream, destination) per poll."""
        items = [
            {"id": "masimo", "type": "Eventstream", "displayName": "MasimoTelemetryStream"},
            {"id": "claims", "type": "Eventstream", "displayName": "ClaimsRTIStream"},
            {"id": "eventhouse", "type": "Eventhouse", "displayName": "MasimoEventhouse"},
        ]
        az = Mock()
        az.run.return_value = subprocess.CompletedProcess(
            [], 0, json.dumps({"state": "Running", "containers": ["Running"]}), "")
        az.token.return_value = "test-token"
        polls = 0

        def http(method, url, token, body=None, timeout=90):
            nonlocal polls
            if "/eventhouses/" in url:
                return 200, {"properties": {
                    "queryServiceUri": "https://test.kusto.invalid",
                    "databasesItemIds": ["database"],
                }}
            if url.endswith("/resume"):
                return 202, {}
            masimo = "/masimo/" in url
            if masimo:
                polls += 1
            source, stream, destination = (
                masimo_states[min(polls, len(masimo_states)) - 1] if masimo else ("Running",) * 3)
            return 200, {
                "sources": [{"name": "source", "status": source}],
                "streams": [{"name": "stream", "status": stream}],
                "destinations": [{
                    "name": "EventhouseDestination", "status": destination, "type": "Eventhouse",
                    "properties": {"workspaceId": "workspace", "itemId": "database",
                                   "databaseName": "MasimoEventhouse",
                                   "tableName": "TelemetryRaw" if masimo else "claims_events"},
                }],
            }

        with patch.object(harness, "http", side_effect=http), \
             patch.object(harness, "_kql", return_value=([["current", "current", 10, 0]], None)), \
             patch.object(harness.time, "sleep"):
            return harness.ensure_telemetry_ready(
                az, "workspace", items, "rg-test", None, 30, lambda _: None)

    def test_destination_failed_during_own_resume_is_not_terminal(self):
        """After a capacity resume the destination reports Failed until its stream settles."""
        result = self._run_masimo_topologies([
            ("Paused", "Paused", "Paused"),
            ("Resuming", "Created", "Failed"),
            ("Running", "Created", "Failed"),
            ("Running", "Running", "Running"),
        ])

        self.assertTrue(result["passed"], result)
        self.assertEqual(result["actions"], [{
            "eventstream": "MasimoTelemetryStream", "action": "resume", "startType": "Now",
        }])

    def test_destination_failed_on_settled_stream_is_terminal(self):
        """A failure the run did not cause by resuming must stop the gate at once."""
        result = self._run_masimo_topologies([("Running", "Running", "Failed")])

        self.assertFalse(result["passed"])
        self.assertEqual(result["actions"], [])
        self.assertIn("failed topology nodes", result["results"][-1]["reason"])
        self.assertIn("EventhouseDestination", result["results"][-1]["reason"])


OPERATION_CONFLICT = {
    "errorCode": "ArtifactOperationConflict",
    "message": "Please wait until the previous operation is completed before initiating the new call.",
    "isRetriable": False,
}


class FakeTelemetryEstate:
    """Producers, Eventstreams and Eventhouse whose state follows only accepted lifecycle calls.

    `rejections` maps (stream id, "resume" | "pause") to responses returned instead of accepting
    the call; once exhausted, calls are accepted. A stream resumed from Now delivers current
    events; a running stream not resumed from Now replays only queued history.
    """
    TABLES = {"masimo": "TelemetryRaw", "claims": "claims_events"}

    def __init__(self, states, rejections=(), delivers_events=True):
        self.states = dict(states)
        self.current = {stream: False for stream in states}
        self.rejections = {key: list(responses) for key, responses in dict(rejections).items()}
        self.delivers_events = delivers_events
        self.clock = 0.0

    def run(self, timeout_sec=600):
        items = [
            {"id": "masimo", "type": "Eventstream", "displayName": "MasimoTelemetryStream"},
            {"id": "claims", "type": "Eventstream", "displayName": "ClaimsRTIStream"},
            {"id": "eventhouse", "type": "Eventhouse", "displayName": "MasimoEventhouse"},
        ]
        az = Mock()
        az.run.return_value = subprocess.CompletedProcess(
            [], 0, json.dumps({"state": "Running", "containers": ["Running"]}), "")
        az.token.return_value = "test-token"
        with patch.object(harness, "http", side_effect=self.http), \
             patch.object(harness, "_kql", side_effect=self.kql), \
             patch.object(harness.time, "monotonic", side_effect=lambda: self.clock), \
             patch.object(harness.time, "sleep", side_effect=self.sleep):
            return harness.ensure_telemetry_ready(
                az, "workspace", items, "rg-test", None, timeout_sec, lambda _: None)

    def sleep(self, seconds):
        self.clock += seconds

    def http(self, method, url, token, body=None, timeout=90):
        if "/eventhouses/" in url:
            return 200, {"properties": {"queryServiceUri": "https://test.kusto.invalid",
                                        "databasesItemIds": ["database"]}}
        stream = url.split("/eventstreams/")[1].split("/")[0]
        operation = url.rsplit("/", 1)[1]
        if operation in ("resume", "pause"):
            pending = self.rejections.get((stream, operation))
            if pending:
                return pending.pop(0)
            self.states[stream] = "Running" if operation == "resume" else "Paused"
            self.current[stream] = operation == "resume" and body == {"startType": "Now"}
            return 202, {}
        status = self.states[stream]
        return 200, {
            "sources": [{"name": "source", "status": status}],
            "streams": [{"name": "stream", "status": "Running"}],
            "destinations": [{
                "name": "destination", "status": status, "type": "Eventhouse",
                "properties": {"workspaceId": "workspace", "itemId": "database",
                               "databaseName": "MasimoEventhouse", "tableName": self.TABLES[stream]},
            }],
        }

    def kql(self, az, query_uri, database, query, tries=4, timeout=60):
        stream = next(stream for stream, table in self.TABLES.items() if query.startswith(table + " "))
        if self.states[stream] != "Running" or not self.delivers_events:
            return [[None, None, 0, 0]], None
        if self.current[stream]:
            return [["now", "now", 10, 0]], None
        return [["old", "now", 0, 50]], None


class TelemetryOperationConflictTests(unittest.TestCase):
    RESUME_BOTH = [
        {"eventstream": "MasimoTelemetryStream", "action": "resume", "startType": "Now"},
        {"eventstream": "ClaimsRTIStream", "action": "resume", "startType": "Now"},
    ]

    def test_resume_conflict_from_earlier_operation_converges(self):
        """med-1103a: Masimo resume is accepted, Claims resume is refused while it finishes."""
        estate = FakeTelemetryEstate({"masimo": "Paused", "claims": "Paused"},
                                     {("claims", "resume"): [(409, OPERATION_CONFLICT)]})

        result = estate.run()

        self.assertTrue(result["passed"], result)
        self.assertEqual(result["actions"], self.RESUME_BOTH)
        fresh = {row["check"]: row["recentEvents"] for row in result["results"]
                 if row["check"].startswith("fresh_data_")}
        self.assertEqual(fresh, {"fresh_data_TelemetryRaw": 10, "fresh_data_claims_events": 10})

    def test_conflict_that_outlasts_the_deadline_fails(self):
        estate = FakeTelemetryEstate({"masimo": "Paused", "claims": "Paused"},
                                     {("claims", "resume"): [(409, OPERATION_CONFLICT)] * 100})

        result = estate.run(timeout_sec=60)

        self.assertFalse(result["passed"])
        self.assertEqual(result["actions"], self.RESUME_BOTH[:1])
        self.assertIn("deadline exceeded", result["results"][-1]["reason"])
        claims = next(row for row in result["results"] if row["check"] == "ClaimsRTIStream")
        self.assertEqual(claims["status"], "WAIT")
        self.assertEqual(claims["deferred"]["action"], "resume")

    def test_other_conflict_is_terminal(self):
        estate = FakeTelemetryEstate({"masimo": "Paused", "claims": "Paused"}, {
            ("claims", "resume"): [(409, {"errorCode": "EventstreamInvalidState",
                                          "message": "Eventstream cannot be resumed.",
                                          "isRetriable": False})],
        })

        result = estate.run()

        self.assertFalse(result["passed"])
        self.assertEqual(result["actions"], self.RESUME_BOTH[:1])
        self.assertIn("ClaimsRTIStream resume failed: HTTP 409", result["results"][-1]["reason"])
        self.assertEqual(estate.clock, 0.0, "a terminal error must not wait for the deadline")

    def test_converged_streams_without_current_events_fail_at_deadline(self):
        estate = FakeTelemetryEstate({"masimo": "Paused", "claims": "Paused"},
                                     {("claims", "resume"): [(409, OPERATION_CONFLICT)]},
                                     delivers_events=False)

        result = estate.run(timeout_sec=60)

        self.assertFalse(result["passed"])
        self.assertEqual(result["actions"], self.RESUME_BOTH)
        self.assertIn("deadline exceeded", result["results"][-1]["reason"])

    def test_pause_conflict_still_resets_stale_stream_from_now(self):
        """A refused reset pause is retried; the stream still ends up resumed from Now."""
        estate = FakeTelemetryEstate({"masimo": "Running", "claims": "Running"},
                                     {("claims", "pause"): [(409, OPERATION_CONFLICT)]})
        estate.current["masimo"] = True

        result = estate.run()

        self.assertTrue(result["passed"], result)
        self.assertEqual(result["actions"], [
            {"eventstream": "ClaimsRTIStream", "action": "pause_for_resume_now"},
            {"eventstream": "ClaimsRTIStream", "action": "resume", "startType": "Now"},
        ])


class ReportCoverageTests(unittest.TestCase):
    def test_populated_dimension_does_not_pass_empty_report_facts(self):
        items = [{"id": "model", "type": "SemanticModel", "displayName": "Outreach"}]
        responses = [([{"[n]": 1}], None), ([{"[n]": 100}], None), ([{"[n]": None}], None)]
        with patch.object(harness, "_user_tables", return_value=["PatientDim", "AppointmentDim"]), \
             patch.object(harness, "_dax", side_effect=responses):
            result = harness.validate_reports(Mock(), "workspace", items, lambda _: None)
        self.assertFalse(result["passed"])
        self.assertEqual(result["results"][0]["status"], "FAIL")

    def test_table_query_error_cannot_be_masked_by_populated_dimensions(self):
        items = [{"id": "model", "type": "SemanticModel", "displayName": "Outreach"}]
        responses = [([{"[n]": 1}], None), ([{"[n]": 100}], None), (None, "Calculation required")]
        with patch.object(harness, "_user_tables", return_value=["PatientDim", "AppointmentDim"]), \
             patch.object(harness, "_dax", side_effect=responses):
            result = harness.validate_reports(Mock(), "workspace", items, lambda _: None)
        self.assertFalse(result["passed"])
        self.assertEqual(result["results"][0]["status"], "FAIL")

    def test_model_timeout_records_fail_and_continues_to_next_model(self):
        items = [
            {"id": "m1", "type": "SemanticModel", "displayName": "SlowModel"},
            {"id": "m2", "type": "SemanticModel", "displayName": "FastModel"},
        ]
        # For m1, simulate exceeding deadline; for m2, succeed
        with patch.object(harness, "_user_tables", side_effect=[["Table1", "Table2"], ["TableA"]]), \
             patch.object(harness, "_dax") as mock_dax, \
             patch("time.monotonic") as mock_time:
            # mock_time returns increasing timestamps:
            # loop start: t=0 -> deadline=10
            # m1 health check: t=1 -> ok
            # m1 user tables: t=2 -> ok
            # m1 table querying: t=15 -> deadline exceeded!
            # m2 loop start: t=16 -> deadline=26
            # m2 health check: t=17 -> ok
            # m2 user tables: t=18 -> ok
            # m2 table querying: t=19 -> ok
            mock_time.side_effect = [
                0.0, 1.0, 2.0, 15.0, 15.0, 15.0, 15.0,
                16.0, 17.0, 18.0, 19.0, 19.0, 20.0, 20.0, 21.0, 22.0, 23.0
            ]
            mock_dax.side_effect = [
                ([{"[n]": 1}], None),        # m1 health check
                ([{"[n]": 1}], None),        # m2 health check
                ([{"[n]": 42}], None),       # m2 TableA count
            ]
            result = harness.validate_reports(Mock(), "workspace", items, lambda _: None, model_timeout=10, batch=False)

        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["status"], "FAIL")
        self.assertTrue("timed out" in result["results"][0]["reason"] or "deadline exceeded" in result["results"][0]["reason"])
        self.assertEqual(result["results"][1]["status"], "PASS")
        self.assertEqual(result["results"][1]["counts"], {"TableA": 42})

    def test_http_honors_deadline_when_expired(self):
        status, body = harness.http("GET", "https://api.fabric.microsoft.com/v1/workspaces", "token", deadline=1.0)
        self.assertEqual(status, 0)
        self.assertIn("deadline exceeded", body.get("_raw", ""))

    def test_main_writes_incremental_json_on_step_failure(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            json_file = tf.name
        try:
            test_args = [
                "deployment_eval_harness.py",
                "--workspace", "test-ws",
                "--json-out", json_file,
                "--no-capacity-resume",
                "--skip", "browser",
                "--skip", "deployment",
                "--skip", "rti",
                "--skip", "agents",
            ]
            with patch("sys.argv", test_args), \
                 patch.object(harness, "find_workspace", return_value="ws-123"), \
                 patch.object(harness, "resolve_capacity_id", return_value="cap-123"), \
                 patch.object(harness, "ensure_capacity_active", return_value=True), \
                 patch.object(harness, "list_items", return_value=[]), \
                 patch.object(harness, "ensure_telemetry_ready", return_value={"category": "telemetry_readiness", "passed": True, "results": []}), \
                 patch.object(harness, "validate_reports", side_effect=RuntimeError("unexpected report failure")):
                with self.assertRaises(RuntimeError):
                    harness.main()

            with open(json_file) as f:
                saved = json.load(f)
            self.assertEqual(saved["workspace"], "test-ws")
            self.assertEqual(saved["workspaceId"], "ws-123")
            # telemetry_readiness was appended before the crash, so it must be present
            self.assertEqual(len(saved["categories"]), 1)
            self.assertEqual(saved["categories"][0]["category"], "telemetry_readiness")
        finally:
            if os.path.exists(json_file):
                os.unlink(json_file)
    def test_browser_rendering_is_required_without_evidence(self):
        from surface_checks import browser_evidence_checks
        result = browser_evidence_checks(None, "workspace", [])
        self.assertFalse(result["passed"])

    def test_operations_agent_requires_authenticated_api_evidence(self):
        from operations_agent_check import validate_operations_agents
        result = validate_operations_agents([{"id": "agent", "type": "OperationsAgent", "displayName": "Ops"}])
        self.assertFalse(result["passed"])

    def test_single_analytic_visual_does_not_pass_layout(self):
        from surface_checks import category
        result = category("report_layout", [{"status": "FAIL", "analyticVisuals": 1}])
        self.assertFalse(result["passed"])


class GraphAgentCheckTests(unittest.TestCase):
    def _run(self, sample_answer):
        from graph_agent_check import check_graph_agent
        answers = [
            "100 DeviceAssoc entities were found.\n\nSource: DevicePayerOntology.",
            sample_answer,
            "1. DevicePayerOntology\n   - Patient entities: 100\n   - linkedToDevice relationships: 100\n"
            "2. MasimoEventhouse / TelemetryRaw\n   - Distinct currently reporting devices: 100",
        ]
        tool = {"name": "ask", "inputSchema": {"properties": {"userQuestion": {}}}}

        def rpc(_endpoint, _token, body):
            if body.get("method") == "tools/list":
                return {"result": {"tools": [tool]}}
            if body.get("method") == "tools/call":
                return {"result": {"content": [{"type": "text", "text": answers[body["id"] - 3]}]}}
            return {"result": {}}

        az = Mock()
        az.token.return_value = "token"
        items = [{"type": "DataAgent", "displayName": "Healthcare Graph Agent", "id": "agent"}]
        return check_graph_agent(az, "ws", items, Mock(), rpc, 100)

    def test_markdown_formatted_association_passes(self):
        result = self._run("- **assocPatientId**: `a88fa4a9-7abf-6238-a5f8-8d1dc76263fc`  \n- **deviceRef**: `MASIMO-RADIUS7-0061`")
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["results"][0]["deviceId"], "MASIMO-RADIUS7-0061")

    def test_association_without_real_ids_fails(self):
        result = self._run("- **assocPatientId**: `patient-1`\n- **deviceRef**: `device-1`")
        self.assertFalse(result["passed"])


class FabricCollectionTests(unittest.TestCase):
    API = harness.FABRIC_API

    def _serve(self, pages):
        """Answer GETs from a URL-keyed page table; unknown URLs fail the test."""
        self.requested = []

        def http(method, url, token, body=None, timeout=60):
            self.requested.append(url)
            page = pages[url]
            return page if isinstance(page, tuple) else (200, page)

        az = Mock()
        az.token.return_value = "token"
        return az, patch.object(harness, "http", side_effect=http)

    def test_lookups_read_every_page_before_reporting_absence(self):
        az, served = self._serve({
            f"{self.API}/workspaces": {
                "value": [{"id": "other", "displayName": "other"}],
                "continuationUri": f"{self.API}/workspaces?continuationToken=two",
            },
            f"{self.API}/workspaces?continuationToken=two": {
                "value": [{"id": "target-id", "displayName": "target"}],
                "continuationToken": "three",
            },
            f"{self.API}/workspaces?continuationToken=three": {"value": []},
            f"{self.API}/workspaces/ws/items": {
                "value": [{"id": "a", "type": "Report", "displayName": "a"}],
                "continuationToken": "n/+=",
            },
            f"{self.API}/workspaces/ws/items?continuationToken=n%2F%2B%3D": {
                "value": [{"id": "b", "type": "SemanticModel", "displayName": "b"}],
            },
            f"{self.API}/workspaces/ws": {"id": "ws", "capacityId": "cap-2"},
            f"{self.API}/capacities": {
                "value": [{"id": "cap-1", "displayName": "fabricone"}],
                "continuationToken": "two",
            },
            f"{self.API}/capacities?continuationToken=two": {
                "value": [{"id": "cap-2", "displayName": "fabrictwo"}],
            },
        })
        az.run.return_value = subprocess.CompletedProcess([], 0, "/subscriptions/s/capacity/fabrictwo\n", "")
        with served:
            self.assertEqual(harness.find_workspace(az, "target"), "target-id")
            self.assertIsNone(harness.find_workspace(az, "missing"))
            self.assertEqual([item["id"] for item in harness.list_items(az, "ws")], ["a", "b"])
            self.assertEqual(harness.resolve_capacity_id(az, "ws"), "/subscriptions/s/capacity/fabrictwo")
        self.assertIn("fabrictwo", " ".join(az.run.call_args.args[0]))

    def test_failed_or_unreadable_later_page_never_becomes_absence(self):
        for label, page in (
            ("http 404", (404, {"error": {"code": "NotFound"}})),
            ("transport error", (0, {"_raw": "transport error: offline"})),
            ("null value", {"value": None}),
            ("missing value", {}),
            ("non-mapping entry", {"value": ["target"]}),
            ("empty mapping entry", {"value": [{}]}),
            ("null name", {"value": [{"id": "w", "displayName": None}]}),
            ("blank id", {"value": [{"id": "", "displayName": "target"}]}),
            ("non-string continuation", {"value": [], "continuationToken": 7}),
        ):
            with self.subTest(page=label):
                az, served = self._serve({
                    f"{self.API}/workspaces": {
                        "value": [{"id": "other", "displayName": "other"}],
                        "continuationToken": "two",
                    },
                    f"{self.API}/workspaces?continuationToken=two": page,
                })
                with served, self.assertRaises(RuntimeError):
                    harness.find_workspace(az, "target")
        for label, entry in (
            ("missing type", {"id": "i", "displayName": "gold"}),
            ("null name", {"id": "i", "displayName": None, "type": "Lakehouse"}),
        ):
            with self.subTest(item=label):
                az, served = self._serve({
                    f"{self.API}/workspaces/ws/items": {
                        "value": [{"id": "a", "displayName": "bronze", "type": "Lakehouse"}],
                        "continuationToken": "two",
                    },
                    f"{self.API}/workspaces/ws/items?continuationToken=two": {"value": [entry]},
                })
                with served, self.assertRaises(RuntimeError):
                    harness.list_items(az, "ws")

    def test_main_reports_unreadable_workspace_listing_as_setup_failure(self):
        import tempfile
        az, served = self._serve({f"{self.API}/workspaces": (403, {"error": {"code": "Unauthorized"}})})
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "result.json")
            argv = ["deployment_eval_harness.py", "--workspace", "target", "--json-out", out]
            with patch("sys.argv", argv), patch.object(harness, "Az", return_value=az), served:
                self.assertEqual(harness.main(), 2)
            with open(out) as f:
                saved = json.load(f)
        self.assertIn("HTTP 403", saved["setupError"])
        self.assertNotIn("not found", saved["setupError"])

    def test_continuation_cannot_leave_fabric_api_or_loop(self):
        for uri in (
            "https://evil.test/v1/workspaces?continuationToken=two",
            "https://api.fabric.microsoft.com.evil.test/v1/workspaces",
            "https://api.fabric.microsoft.com/v10/workspaces",
            "https://api.fabric.microsoft.com/v1/%2E%2E/admin",
            f"{harness.FABRIC_API}/workspaces",
        ):
            with self.subTest(uri=uri):
                az, served = self._serve({
                    f"{self.API}/workspaces": {"value": [], "continuationUri": uri},
                })
                with served, self.assertRaises(RuntimeError):
                    harness.find_workspace(az, "target")
                self.assertEqual(self.requested, [f"{self.API}/workspaces"])

        az, served = self._serve({
            f"{self.API}/workspaces": {"value": [], "continuationToken": "two"},
            f"{self.API}/workspaces?continuationToken=two": {"value": [], "continuationToken": "two"},
        })
        with served, self.assertRaises(RuntimeError):
            harness.find_workspace(az, "target")



if __name__ == "__main__":
    unittest.main()

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



if __name__ == "__main__":
    unittest.main()

"""Behavioral regressions for the pre-report telemetry gate."""
import json
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


class ExpandedCoverageTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

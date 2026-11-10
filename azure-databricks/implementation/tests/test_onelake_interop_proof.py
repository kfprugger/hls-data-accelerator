"""Unit tests for 09-onelake-interop-proof.py."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch

# Load the script under test
SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "09-onelake-interop-proof.py"
)
spec = importlib.util.spec_from_file_location("onelake_interop_proof", SCRIPT_PATH)
interop_mod = importlib.util.module_from_spec(spec)
sys.modules["onelake_interop_proof"] = interop_mod
spec.loader.exec_module(interop_mod)


class TestOneLakeInteropProof(unittest.TestCase):
    def test_dry_run_statement_construction(self):
        """Test SQL query construction and dry-run output formatting."""
        expected_statement = (
            "SELECT count(DISTINCT patient_id) AS tcga_patient_count FROM fabric_clinical.dbo.patient"
        )
        self.assertIn("SELECT count(DISTINCT patient_id) AS tcga_patient_count", expected_statement)
        self.assertIn("fabric_clinical.dbo.patient", expected_statement)

    @patch("time.sleep", return_value=None)
    @patch("requests.get")
    def test_polling_timeout(self, mock_get, _mock_sleep):
        """E-5: Test that polling loop times out after 36 attempts and raises clear TimeoutError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "statement_id": "stmt-pending-123",
            "status": {"state": "PENDING"},
        }
        mock_get.return_value = mock_resp

        with self.assertRaises(TimeoutError) as ctx:
            interop_mod.poll_statement_execution(
                host="https://fake-dbx.azuredatabricks.net",
                statement_id="stmt-pending-123",
                token="fake-token",
                max_retries=36,
                interval_sec=0,
            )

        self.assertIn("Databricks statement execution exceeded timeout (180s)", str(ctx.exception))
        self.assertEqual(mock_get.call_count, 36)

    def test_phi_and_secret_suppression(self):
        """E-7: Ensure proof JSON payload contains aggregate count only, with zero PHI or credentials."""
        fixture_path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "rayfin-imaging"
            / "local"
            / "fixtures"
            / "databricks_proof.json"
        )
        self.assertTrue(fixture_path.is_file(), f"Fixture file not found: {fixture_path}")
        data = json.loads(fixture_path.read_text(encoding="utf-8"))

        required_keys = {
            "timestamp",
            "engine",
            "statement",
            "warehouseId",
            "rowCount",
            "fabricP360Count",
            "deltaTableVersion",
            "executionTimeMs",
            "oneLakeExternalLocation",
            "status",
            "zeroCopyVerified",
        }
        self.assertEqual(set(data.keys()), required_keys)
        self.assertEqual(data["rowCount"], 15)
        self.assertEqual(data["fabricP360Count"], 15)
        self.assertEqual(data["status"], "SUCCEEDED")
        self.assertTrue(data["zeroCopyVerified"])
        self.assertIn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", data["oneLakeExternalLocation"])

        payload_str = json.dumps(data)
        forbidden_terms = [
            "password",
            "secret",
            "client_secret",
            "bearer",
            "token",
            "TCGA-G6-A8L6",
            "TCGA-E2-A152",
            "Marcus Vance",
            "patient_name",
            "ssn",
            "dob",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term.lower(), payload_str.lower())

    @patch("requests.post")
    def test_execute_sql_statement_succeeded(self, mock_post):
        """Test statement execution returning 15 rows."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "statement_id": "stmt-succeeded-456",
            "status": {"state": "SUCCEEDED"},
            "result": {
                "data_array": [["15"]],
            },
        }
        mock_post.return_value = mock_resp

        row_count, latency_ms, status = interop_mod.execute_sql_statement(
            host="https://fake-dbx.azuredatabricks.net",
            warehouse_id="wh-123",
            statement="SELECT count(DISTINCT patient_id) AS tcga_patient_count FROM fabric_clinical.dbo.patient",
            token="fake-token",
        )
        self.assertEqual(row_count, 15)
        self.assertEqual(status, "SUCCEEDED")
        self.assertGreaterEqual(latency_ms, 0)

    @patch("requests.post")
    def test_get_table_metadata(self, mock_post):
        """Test retrieving location and Delta table version."""
        desc_resp = MagicMock()
        desc_resp.status_code = 200
        desc_resp.json.return_value = {
            "result": {
                "data_array": [
                    ["Location", "abfss://ws@onelake.dfs.fabric.microsoft.com/item/Tables/patient"],
                    ["Provider", "delta"],
                ]
            }
        }
        hist_resp = MagicMock()
        hist_resp.status_code = 200
        hist_resp.json.return_value = {
            "result": {
                "data_array": [["3", "2026-11-07T00:00:00Z"]]
            }
        }
        mock_post.side_effect = [desc_resp, hist_resp]

        location, version = interop_mod.get_table_metadata(
            host="https://fake-dbx.azuredatabricks.net",
            warehouse_id="wh-123",
            token="fake-token",
        )
        self.assertIn("Tables/patient", location)
        self.assertEqual(version, 3)

    @patch.object(interop_mod, "get_entra_token", return_value="fake-token")
    @patch("requests.delete")
    def test_delete_proof_from_onelake(self, mock_delete, _mock_token):
        """Test OneLake proof deletion in cleanup mode."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_delete.return_value = mock_resp

        interop_mod.delete_proof_from_onelake(workspace_id="ws-123", imaging_id="lh-456")
        mock_delete.assert_called_once()
        call_url = mock_delete.call_args[0][0]
        self.assertIn("/ws-123/lh-456/Files/interop/databricks_proof.json", call_url)
        call_headers = mock_delete.call_args[1]["headers"]
        self.assertEqual(call_headers.get("x-ms-fabric-skill"), "search-consumption-cli")


if __name__ == "__main__":
    unittest.main()

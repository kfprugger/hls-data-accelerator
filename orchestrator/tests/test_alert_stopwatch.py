"""Unit tests for acute SpO2 alert trigger, deduplication, and stopwatch measurement."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

import scripts.trigger_spo2_alert as trigger_mod
import scripts.deploy_clinical_activator as activator_mod


class TestAlertStopwatch(unittest.TestCase):
    def setUp(self):
        self.orig_env = dict(os.environ)
        os.environ["HLS_ALERT_EMAIL"] = "joey@jbatl.dev"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_ten_minute_deduplication(self):
        """FR-4 / E-4: Simulate drop at T=0, followed by second drop at T=180s for MASIMO-RADIUS7-0101.

        First alert must generate status DISPATCHED with email queued.
        Second alert must generate status SUPPRESSED_DEDUPE with zero new email actions.
        """
        device_id = "MASIMO-RADIUS7-0101"
        test_history = {}

        # Alert 1 at T = 0
        t0 = 1000.0
        is_suppressed_1, status_1, email_queued_1 = trigger_mod.check_deduplication(
            device_id=device_id,
            current_time_epoch=t0,
            history=test_history,
        )
        self.assertFalse(is_suppressed_1)
        self.assertEqual("DISPATCHED", status_1)
        self.assertTrue(email_queued_1)
        trigger_mod.record_alert_dispatch(device_id, t0, history=test_history)

        # Alert 2 at T = 180s (3 minutes later, within 10-min window)
        t1 = 1000.0 + 180.0
        is_suppressed_2, status_2, email_queued_2 = trigger_mod.check_deduplication(
            device_id=device_id,
            current_time_epoch=t1,
            history=test_history,
        )
        self.assertTrue(is_suppressed_2)
        self.assertEqual("SUPPRESSED_DEDUPE", status_2)
        self.assertFalse(email_queued_2)

        # Alert 3 after 601s (past 10-min cooldown window)
        t2 = 1000.0 + 605.0
        is_suppressed_3, status_3, email_queued_3 = trigger_mod.check_deduplication(
            device_id=device_id,
            current_time_epoch=t2,
            history=test_history,
        )
        self.assertFalse(is_suppressed_3)
        self.assertEqual("DISPATCHED", status_3)
        self.assertTrue(email_queued_3)

    def test_stopwatch_latency_calculation(self):
        """FR-5 / E-7: Verify stopwatch latency calculation for T0=0.0s, T1=2.3s, T2=8.1s, T3=18.4s.

        Total elapsed time t_total = 18.4s <= 60.0s.
        """
        t0 = 0.0
        t1 = 2.3
        t2 = 8.1
        t3 = 18.4

        latencies = trigger_mod.calculate_stopwatch(t0, t1, t2, t3)
        self.assertEqual(2.3, latencies["t_ingest"])
        self.assertEqual(5.8, latencies["t_detect"])
        self.assertEqual(10.3, latencies["t_action"])
        self.assertEqual(18.4, latencies["t_total"])
        self.assertLessEqual(latencies["t_total"], 60.0)

    def test_allowlist_validation_success(self):
        """FR-2: Valid configured email passes allowlist validation."""
        os.environ["HLS_ALERT_EMAIL"] = "joey@jbatl.dev"
        self.assertEqual("joey@jbatl.dev", trigger_mod.validate_recipient_allowlist())
        self.assertEqual("joey@jbatl.dev", trigger_mod.validate_recipient_allowlist("joey@jbatl.dev"))

    def test_allowlist_validation_unauthorized_rejection(self):
        """FR-2 / E-3: Supplying non-allowlisted email raises SystemExit(2)."""
        os.environ["HLS_ALERT_EMAIL"] = "joey@jbatl.dev"
        with self.assertRaises(SystemExit) as cm:
            trigger_mod.validate_recipient_allowlist("attacker@evil.com")
        self.assertEqual(2, cm.exception.code)

    def test_allowlist_validation_missing_env(self):
        """FR-2 / E-10: Unset HLS_ALERT_EMAIL raises SystemExit(2)."""
        if "HLS_ALERT_EMAIL" in os.environ:
            del os.environ["HLS_ALERT_EMAIL"]
        with self.assertRaises(SystemExit) as cm:
            trigger_mod.validate_recipient_allowlist()
        self.assertEqual(2, cm.exception.code)

    def test_patient_device_resolution_marcus_vance(self):
        """FR-1: Marcus Vance resolves to MASIMO-RADIUS7-0101."""
        name, dev_id = trigger_mod.resolve_patient_device("TCGA-G6-A8L6", live=False)
        self.assertEqual("Marcus Vance", name)
        self.assertEqual("MASIMO-RADIUS7-0101", dev_id)

    def test_patient_device_resolution_unknown_patient(self):
        """FR-1 / E-9: Unknown patient exits with 1."""
        with self.assertRaises(SystemExit) as cm:
            trigger_mod.resolve_patient_device("TCGA-XX-0000", live=False)
        self.assertEqual(1, cm.exception.code)

    def test_activator_reflex_definition_schema(self):
        """FR-3: Reflex entities contain executionIntervalInSeconds = 60 and no isStopped."""
        entities, b64 = activator_mod.build_reflex_entities(
            alert_email="joey@jbatl.dev",
            kql_db_id="kql-123",
            workspace_id="ws-456",
            execution_interval_seconds=60,
            include_rule=True,
        )
        self.assertTrue(len(entities) >= 10)
        kql_source = next((e for e in entities if e.get("type") == "kqlSource-v1"), None)
        self.assertIsNotNone(kql_source)
        run_settings = kql_source["payload"]["runSettings"]
        self.assertEqual(60, run_settings.get("executionIntervalInSeconds"))
        self.assertNotIn("isStopped", run_settings)

    @patch("scripts.deploy_clinical_activator.requests.get")
    def test_lro_polling_success(self, mock_get):
        """FR-3: LRO polling succeeds when operation returns status Succeeded."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "Succeeded"}
        mock_get.return_value = mock_resp

        # Should not raise
        activator_mod.poll_lro("op-123", "dummy-tok", deadline_seconds=10)

    @patch("scripts.deploy_clinical_activator.requests.get")
    def test_lro_polling_timeout(self, mock_get):
        """FR-3 / Edge cases: LRO polling raises TimeoutError on timeout."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "Running"}
        mock_get.return_value = mock_resp

        with self.assertRaises(TimeoutError):
            activator_mod.poll_lro("op-timeout", "dummy-tok", deadline_seconds=0.05)


if __name__ == "__main__":
    unittest.main()

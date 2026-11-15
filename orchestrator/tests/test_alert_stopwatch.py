"""Unit tests for acute SpO2 alert trigger, deduplication, and stopwatch measurement."""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import scripts.trigger_spo2_alert as trigger_mod
import scripts.deploy_clinical_activator as activator_mod


class TestAlertStopwatch(unittest.TestCase):
    def setUp(self):
        self.orig_env = dict(os.environ)
        os.environ["HLS_ALERT_EMAIL"] = "alerts@example.com"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_classify_alert_outcome_deduplication_bands(self):
        """FR-4 / R-2: Classify alert outcome against Eventhouse alert history with W, P, and L."""
        # W = 600s (10 min), P = 60s, L = 10s
        # delta < W - L (590s): SUPPRESSED_DEDUPE
        # W - L <= delta <= W + P + L (590s..670s): UNCERTAIN_BOUNDARY
        # delta > W + P + L (670s): EXPECTED_DISPATCH (a prediction; delivery is only DISPATCHED once observed)
        t_base = 10000.0

        # No previous alert -> EXPECTED_DISPATCH
        st, sup, eq = trigger_mod.classify_alert_outcome(t_base, None, cooldown_minutes=10)
        self.assertEqual("EXPECTED_DISPATCH", st)
        self.assertFalse(sup)
        self.assertTrue(eq)

        # delta = 0s -> SUPPRESSED_DEDUPE
        st, sup, eq = trigger_mod.classify_alert_outcome(t_base, t_base, cooldown_minutes=10)
        self.assertEqual("SUPPRESSED_DEDUPE", st)
        self.assertTrue(sup)
        self.assertFalse(eq)

        # delta = 180s (3 min) -> SUPPRESSED_DEDUPE
        st, sup, eq = trigger_mod.classify_alert_outcome(t_base + 180.0, t_base, cooldown_minutes=10)
        self.assertEqual("SUPPRESSED_DEDUPE", st)
        self.assertTrue(sup)
        self.assertFalse(eq)

        # delta = 589s (< 590s) -> SUPPRESSED_DEDUPE
        st, sup, eq = trigger_mod.classify_alert_outcome(t_base + 589.0, t_base, cooldown_minutes=10)
        self.assertEqual("SUPPRESSED_DEDUPE", st)
        self.assertTrue(sup)
        self.assertFalse(eq)

        # Boundary lower edge: delta = 590s (W - L) -> UNCERTAIN_BOUNDARY
        st, sup, eq = trigger_mod.classify_alert_outcome(t_base + 590.0, t_base, cooldown_minutes=10)
        self.assertEqual("UNCERTAIN_BOUNDARY", st)
        self.assertFalse(sup)
        self.assertFalse(eq)

        # Boundary midpoint: delta = 600s -> UNCERTAIN_BOUNDARY
        st, sup, eq = trigger_mod.classify_alert_outcome(t_base + 600.0, t_base, cooldown_minutes=10)
        self.assertEqual("UNCERTAIN_BOUNDARY", st)
        self.assertFalse(sup)
        self.assertFalse(eq)

        # Boundary upper edge: delta = 670s (W + P + L) -> UNCERTAIN_BOUNDARY
        st, sup, eq = trigger_mod.classify_alert_outcome(t_base + 670.0, t_base, cooldown_minutes=10)
        self.assertEqual("UNCERTAIN_BOUNDARY", st)
        self.assertFalse(sup)
        self.assertFalse(eq)

        # Above boundary: delta = 671s -> EXPECTED_DISPATCH
        st, sup, eq = trigger_mod.classify_alert_outcome(t_base + 671.0, t_base, cooldown_minutes=10)
        self.assertEqual("EXPECTED_DISPATCH", st)
        self.assertFalse(sup)
        self.assertTrue(eq)

        # delta = 900s (15 min) -> EXPECTED_DISPATCH
        st, sup, eq = trigger_mod.classify_alert_outcome(t_base + 900.0, t_base, cooldown_minutes=10)
        self.assertEqual("EXPECTED_DISPATCH", st)
        self.assertFalse(sup)
        self.assertTrue(eq)

        # Custom cooldown: 5 min -> W=300s, W-L=290s, W+P+L=370s
        st_5_sup, sup_5, _ = trigger_mod.classify_alert_outcome(t_base + 200.0, t_base, cooldown_minutes=5)
        self.assertEqual("SUPPRESSED_DEDUPE", st_5_sup)
        self.assertTrue(sup_5)

        st_5_bnd, _, _ = trigger_mod.classify_alert_outcome(t_base + 300.0, t_base, cooldown_minutes=5)
        self.assertEqual("UNCERTAIN_BOUNDARY", st_5_bnd)

        st_5_disp, sup_5_d, eq_5_d = trigger_mod.classify_alert_outcome(t_base + 380.0, t_base, cooldown_minutes=5)
        self.assertEqual("EXPECTED_DISPATCH", st_5_disp)
        self.assertFalse(sup_5_d)
        self.assertTrue(eq_5_d)

    def test_stopwatch_latency_calculation(self):
        """FR-5 / E-7: Verify stopwatch latency calculation for T0=0.0s, T1=2.3s, T2=8.1s, T3=18.4s."""
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
        os.environ["HLS_ALERT_EMAIL"] = "alerts@example.com"
        self.assertEqual("alerts@example.com", trigger_mod.validate_recipient_allowlist())
        self.assertEqual("alerts@example.com", trigger_mod.validate_recipient_allowlist("alerts@example.com"))

    def test_allowlist_validation_unauthorized_rejection(self):
        """FR-2 / E-3: Supplying non-allowlisted email raises SystemExit(2)."""
        os.environ["HLS_ALERT_EMAIL"] = "alerts@example.com"
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
            alert_email="alerts@example.com",
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
        # FR-3: kqlSource contains fn_ClinicalAlerts with default 10-minute cooldown
        self.assertIn("fn_ClinicalAlerts(10)", kql_source["payload"]["query"]["queryString"])

    def test_stateful_alert_rule_definition(self):
        """FR-3 / FR-4: Definition models Device object, alert_active attribute, and AttributeTrigger."""
        recipient = "alerts@example.com"
        entities, _ = activator_mod.build_reflex_entities(
            alert_email=recipient,
            kql_db_id="kql-123",
            workspace_id="ws-456",
            execution_interval_seconds=60,
            include_rule=True,
            cooldown_minutes=10,
        )

        # 1. Device object entity
        device_obj = next((e for e in entities if e.get("type") == "timeSeriesView-v1" and e.get("payload", {}).get("name") == "Device"), None)
        self.assertIsNotNone(device_obj)
        self.assertEqual("Object", device_obj["payload"]["definition"]["type"])
        device_obj_id = device_obj["uniqueIdentifier"]

        # 2. alert_active attribute entity
        alert_active_attr = next((e for e in entities if e.get("type") == "timeSeriesView-v1" and e.get("payload", {}).get("name") == "alert_active"), None)
        self.assertIsNotNone(alert_active_attr)
        self.assertEqual("Attribute", alert_active_attr["payload"]["definition"]["type"])
        self.assertEqual(device_obj_id, alert_active_attr["payload"]["parentObject"]["targetUniqueIdentifier"])
        alert_active_id = alert_active_attr["uniqueIdentifier"]

        # 3. AttributeTrigger rule entity
        rule_entity = next((e for e in entities if e.get("type") == "timeSeriesView-v1" and e.get("payload", {}).get("definition", {}).get("type") == "Rule"), None)
        self.assertIsNotNone(rule_entity)
        self.assertEqual(device_obj_id, rule_entity["payload"]["parentObject"]["targetUniqueIdentifier"])
        rule_inst = json.loads(rule_entity["payload"]["definition"]["instance"])
        self.assertEqual("AttributeTrigger", rule_inst.get("templateId"))
        self.assertEqual("1.2.4", rule_inst.get("templateVersion"))

        steps = {s["name"]: s for s in rule_inst.get("steps", [])}
        self.assertIn("ScalarSelectStep", steps)
        self.assertIn("ScalarDetectStep", steps)
        self.assertIn("ActStep", steps)

        # ScalarSelectStep selects alert_active
        select_rows = steps["ScalarSelectStep"]["rows"]
        attr_selector = next((r for r in select_rows if r.get("name") == "AttributeSelector"), None)
        self.assertIsNotNone(attr_selector)
        ref_arg = attr_selector["arguments"][0]["arguments"][0]
        self.assertEqual(alert_active_id, ref_arg["value"])

        # ScalarDetectStep: NumberBecomes BecomesGreaterThan 0, OccurrenceOption EachTime
        detect_rows = {r["name"]: r for r in steps["ScalarDetectStep"]["rows"]}
        self.assertIn("NumberBecomes", detect_rows)
        nb_args = {a["name"]: a["value"] for a in detect_rows["NumberBecomes"]["arguments"]}
        self.assertEqual("BecomesGreaterThan", nb_args.get("op"))
        self.assertEqual(0, nb_args.get("value"))
        self.assertIn("OccurrenceOption", detect_rows)
        self.assertEqual("EachTime", detect_rows["OccurrenceOption"]["kind"])

        # ActStep: EmailMessage to only allowlisted recipient
        act_rows = steps["ActStep"]["rows"]
        email_binding = next((r for r in act_rows if r.get("name") == "EmailBinding"), None)
        self.assertIsNotNone(email_binding)
        self.assertEqual("EmailMessage", email_binding["kind"])
        email_args = {a["name"]: a for a in email_binding["arguments"]}
        sent_to = [v["value"] for v in email_args["sentTo"]["values"]]
        self.assertEqual([recipient], sent_to)
        self.assertEqual([], email_args["copyTo"]["values"])
        self.assertEqual([], email_args["bCCTo"]["values"])

    def test_cooldown_minutes_parameterizes_kql_query(self):
        """FR-3: --cooldown-minutes parameterizes fn_ClinicalAlerts window in KQL query."""
        entities_15, _ = activator_mod.build_reflex_entities(
            alert_email="alerts@example.com",
            kql_db_id="kql-1",
            workspace_id="ws-1",
            cooldown_minutes=15,
        )
        kql_source_15 = next(e for e in entities_15 if e.get("type") == "kqlSource-v1")
        query_15 = kql_source_15["payload"]["query"]["queryString"]
        self.assertIn("fn_ClinicalAlerts(15)", query_15)
        self.assertIn("ago(60m)", query_15)

        entities_90, _ = activator_mod.build_reflex_entities(
            alert_email="alerts@example.com",
            kql_db_id="kql-1",
            workspace_id="ws-1",
            cooldown_minutes=90,
        )
        kql_source_90 = next(e for e in entities_90 if e.get("type") == "kqlSource-v1")
        query_90 = kql_source_90["payload"]["query"]["queryString"]
        self.assertIn("fn_ClinicalAlerts(90)", query_90)
        self.assertIn("ago(100m)", query_90)

    def test_min_tier_selects_tiers_at_or_above_threshold(self):
        """Deploy-All -AlertTierThreshold: the KQL source emails only tiers at or above the threshold."""
        def tier_filter(min_tier: str) -> str:
            entities, _ = activator_mod.build_reflex_entities(
                alert_email="alerts@example.com", kql_db_id="kql-1", workspace_id="ws-1", min_tier=min_tier,
            )
            query = next(e for e in entities if e.get("type") == "kqlSource-v1")["payload"]["query"]["queryString"]
            return next(line.strip() for line in query.splitlines() if "where alert_tier in" in line)

        self.assertEqual("| where alert_tier in ('CRITICAL', 'URGENT', 'WARNING')", tier_filter("WARNING"))
        self.assertEqual("| where alert_tier in ('CRITICAL', 'URGENT')", tier_filter("urgent"))
        self.assertEqual("| where alert_tier in ('CRITICAL')", tier_filter("CRITICAL"))
        with self.assertRaises(ValueError):
            tier_filter("INFO")

        # An invalid tier is rejected before any token or network call.
        with patch("scripts.deploy_clinical_activator.get_fabric_token", side_effect=AssertionError("Network called!")):
            with self.assertRaises(ValueError):
                activator_mod.deploy_activator(dry_run=False, min_tier="INFO")

    def test_deploy_activator_early_exit_guards_before_network(self):
        """FR-2: deploy_activator validates recipient allowlist before acquiring token or network calls."""
        # Should exit with code 2 if HLS_ALERT_EMAIL is unset
        if "HLS_ALERT_EMAIL" in os.environ:
            del os.environ["HLS_ALERT_EMAIL"]

        with patch("scripts.deploy_clinical_activator.get_fabric_token", side_effect=AssertionError("Network called!")):
            with self.assertRaises(SystemExit) as cm:
                activator_mod.deploy_activator(dry_run=False)
            self.assertEqual(2, cm.exception.code)

        # Should exit with code 2 if unauthorized recipient provided
        os.environ["HLS_ALERT_EMAIL"] = "alerts@example.com"
        with patch("scripts.deploy_clinical_activator.get_fabric_token", side_effect=AssertionError("Network called!")):
            with self.assertRaises(SystemExit) as cm:
                activator_mod.deploy_activator(email="attacker@evil.com", dry_run=False)
            self.assertEqual(2, cm.exception.code)

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

    def test_live_requires_explicit_targets_and_fails_when_beats_not_observed(self):
        with self.assertRaises(SystemExit) as cm:
            trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="",
                resource_group="rg-test",
                eventhouse_query_uri="",
            )
        self.assertEqual(cm.exception.code, 2)

        eh_resp = MagicMock()
        eh_resp.status_code = 201
        kql_resp = MagicMock()
        kql_resp.status_code = 500
        fake_time = [100.0]

        def advancing_clock():
            val = fake_time[0]
            fake_time[0] += 16.0
            return val

        kql_recent_resp = MagicMock()
        kql_recent_resp.status_code = 200
        kql_recent_resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2026-11-13T00:00:00.000Z"]]}]

        def mock_live_post(url, **kw):
            if "servicebus" in url:
                return eh_resp
            csl = kw.get("json", {}).get("csl", "")
            if "ago(55m)" in csl:
                return kql_recent_resp
            return kql_resp

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_live_post), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=kql_resp), \
             patch("scripts.trigger_spo2_alert.time.sleep"), \
             patch("scripts.trigger_spo2_alert.time.time", side_effect=advancing_clock), \
             patch("scripts.trigger_spo2_alert.time.monotonic", side_effect=advancing_clock):
            res = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
            )
        beats_by_id = {b["id"]: b for b in res["beats"]}
        self.assertEqual(beats_by_id["eventstream_enqueued"]["status"], "not_observed")
        self.assertEqual(beats_by_id["kql_detected"]["status"], "not_observed")
        self.assertIsNone(res["t_ingest"])
        self.assertIsNone(res["t_detect"])

    def test_split_event_wiring_and_entity_graph(self):
        """FR-3 / R-1: SplitEvent links Device object to SourceEvent via IdentityPartAttribute device_id."""
        entities, _ = activator_mod.build_reflex_entities(
            alert_email="alerts@example.com",
            kql_db_id="kql-123",
            workspace_id="ws-456",
        )
        device_obj = next(e for e in entities if e.get("type") == "timeSeriesView-v1" and e.get("payload", {}).get("name") == "Device")
        src_event = next(e for e in entities if e.get("type") == "timeSeriesView-v1" and e.get("payload", {}).get("name") == "Clinical alert events")
        split_event = next(e for e in entities if e.get("type") == "timeSeriesView-v1" and e.get("payload", {}).get("name") == "SplitEvent")
        device_id_attr = next(e for e in entities if e.get("type") == "timeSeriesView-v1" and e.get("payload", {}).get("name") == "device_id")

        device_obj_id = device_obj["uniqueIdentifier"]
        src_event_id = src_event["uniqueIdentifier"]
        split_event_id = split_event["uniqueIdentifier"]
        device_id_attr_id = device_id_attr["uniqueIdentifier"]

        # SplitEvent parentObject = Device id
        self.assertEqual(device_obj_id, split_event["payload"]["parentObject"]["targetUniqueIdentifier"])

        # SplitEvent template verification
        split_inst = json.loads(split_event["payload"]["definition"]["instance"])
        self.assertEqual("SplitEvent", split_inst["templateId"])
        self.assertEqual("1.2.4", split_inst["templateVersion"])
        rows = split_inst["steps"][0]["rows"]
        rows_by_name = {r["name"]: r for r in rows}

        # EventSelector -> SourceEvent id
        evt_sel = rows_by_name["EventSelector"]
        self.assertEqual(src_event_id, evt_sel["arguments"][0]["arguments"][0]["value"])

        # FieldIdMapping fieldName device_id -> IdentityPartAttribute id
        field_map = rows_by_name["FieldIdMapping"]
        map_args = {a["name"]: a for a in field_map["arguments"]}
        self.assertEqual("device_id", map_args["fieldName"]["value"])
        self.assertEqual(device_id_attr_id, map_args["idPart"]["arguments"][0]["value"])

        # SplitEventOptions isAuthoritative = True
        options = rows_by_name["SplitEventOptions"]
        self.assertTrue(options["arguments"][0]["value"])

        # Every value attribute references SplitEvent id (not SourceEvent id)
        value_attr_names = ["alert_active", "alert_tier", "spo2", "pr", "patient_name", "message", "alert_time", "device_id_val"]
        for attr_name in value_attr_names:
            attr_entity = next(e for e in entities if e.get("type") == "timeSeriesView-v1" and e.get("payload", {}).get("name") == attr_name)
            attr_inst = json.loads(attr_entity["payload"]["definition"]["instance"])
            self.assertEqual("BasicEventAttribute", attr_inst["templateId"])
            ev_sel = next(r for r in attr_inst["steps"][0]["rows"] if r.get("name") == "EventSelector")
            referenced_ev_id = ev_sel["arguments"][0]["arguments"][0]["value"]
            self.assertEqual(split_event_id, referenced_ev_id, f"Attribute {attr_name} must reference SplitEvent id")

    def test_roster_lookback_cooldown_relationship(self):
        """R-4: Roster lookback is max(60, cooldown + 10) so lookback > cooldown and >= 60 for all cooldowns."""
        test_cooldowns = [1, 10, 59, 60, 90, 1440]
        for cd in test_cooldowns:
            expected_lookback = max(60, cd + 10)
            self.assertGreater(expected_lookback, cd)
            self.assertGreaterEqual(expected_lookback, 60)

            entities, _ = activator_mod.build_reflex_entities(
                alert_email="alerts@example.com",
                kql_db_id="kql-1",
                workspace_id="ws-1",
                cooldown_minutes=cd,
            )
            kql_source = next(e for e in entities if e.get("type") == "kqlSource-v1")
            query = kql_source["payload"]["query"]["queryString"]
            self.assertIn(f"ago({expected_lookback}m)", query)
            self.assertIn(f"fn_ClinicalAlerts({cd})", query)

    def test_cooldown_range_validation_rejection(self):
        """R-3: Cooldown values outside 1..1440 are rejected with exit code 2 and no network calls."""
        for invalid_cd in [0, -5, 1441]:
            # Argument parser rejects invalid cooldown with exit code 2
            parser = argparse.ArgumentParser()
            parser.add_argument("--cooldown-minutes", type=activator_mod.validate_cooldown)
            with self.assertRaises(SystemExit) as cm:
                parser.parse_args(["--cooldown-minutes", str(invalid_cd)])
            self.assertEqual(2, cm.exception.code)

            # deploy_activator exits with code 2 before any network / token call
            with patch("scripts.deploy_clinical_activator.get_fabric_token", side_effect=AssertionError("Network called!")):
                with self.assertRaises(SystemExit) as cm:
                    activator_mod.deploy_activator(dry_run=False, cooldown_minutes=invalid_cd)
                self.assertEqual(2, cm.exception.code)

            # build_reflex_entities raises ValueError
            with self.assertRaises(ValueError):
                activator_mod.build_reflex_entities(
                    alert_email="alerts@example.com",
                    kql_db_id="kql-1",
                    workspace_id="ws-1",
                    cooldown_minutes=invalid_cd,
                )

    def test_dedupe_sequences(self):
        """FR-4 / R-2: Dry-run predicts dedupe outcomes but never reports an observed dispatch or timing."""
        t_base = 10000.0
        cases = [
            # (label, drop offset, previous alert, cooldown, expected outcome, suppressed, email expected)
            ("initial", 0.0, None, 10, "EXPECTED_DISPATCH", False, True),
            ("t+3m", 180.0, t_base, 10, "SUPPRESSED_DEDUPE", True, False),
            ("t+10m boundary", 600.0, t_base, 10, "UNCERTAIN_BOUNDARY", False, False),
            ("t+12m", 720.0, t_base, 10, "EXPECTED_DISPATCH", False, True),
            ("cooldown 5m, t+400s", 400.0, t_base, 5, "EXPECTED_DISPATCH", False, True),
        ]
        for label, offset, prev, cooldown, exp_outcome, exp_suppressed, exp_email in cases:
            with self.subTest(case=label):
                res = trigger_mod.run_trigger(
                    patient_id="TCGA-G6-A8L6",
                    email="alerts@example.com",
                    dry_run=True,
                    current_time_epoch=t_base + offset,
                    previous_alert_epoch=prev,
                    cooldown_minutes=cooldown,
                )
                self.assertEqual("PLANNED", res["status"])
                self.assertEqual(exp_outcome, res["expected_outcome"])
                self.assertEqual(exp_suppressed, res["suppressed_by_dedupe"])
                self.assertEqual(exp_email, res["email_expected"])
                self.assertFalse(res["dispatch_observed"])
                self.assertEqual({"planned"}, {b["status"] for b in res["beats"]})
                self.assertTrue(all(b["timestamp"] is None and b["elapsed_seconds"] is None for b in res["beats"]))
                self.assertIsNone(res["t_total"])
                self.assertEqual("UNCERTAIN_BOUNDARY" == exp_outcome, "boundary_notice" in res)

    def test_eventhub_env_var_fallbacks(self):
        """R-7: Event Hub namespace and name resolve from both standard and underscored env vars."""
        # 1. EVENTHUB_NAMESPACE fallback
        os.environ["EVENTHUB_NAMESPACE"] = "ns-standard"
        os.environ.pop("EVENT_HUB_NAMESPACE", None)
        os.environ["EVENTHUB_NAME"] = "hub-standard"
        os.environ.pop("EVENT_HUB_NAME", None)

        parser1 = argparse.ArgumentParser()
        parser1.add_argument("--eventhub-namespace", default=os.environ.get("EVENTHUB_NAMESPACE") or os.environ.get("EVENT_HUB_NAMESPACE"))
        parser1.add_argument("--eventhub-name", default=os.environ.get("EVENTHUB_NAME") or os.environ.get("EVENT_HUB_NAME") or "telemetry-stream")
        args1 = parser1.parse_args([])
        self.assertEqual("ns-standard", args1.eventhub_namespace)
        self.assertEqual("hub-standard", args1.eventhub_name)

        # 2. EVENT_HUB_NAMESPACE fallback
        os.environ.pop("EVENTHUB_NAMESPACE", None)
        os.environ["EVENT_HUB_NAMESPACE"] = "ns-underscored"
        os.environ.pop("EVENTHUB_NAME", None)
        os.environ["EVENT_HUB_NAME"] = "hub-underscored"

        parser2 = argparse.ArgumentParser()
        parser2.add_argument("--eventhub-namespace", default=os.environ.get("EVENTHUB_NAMESPACE") or os.environ.get("EVENT_HUB_NAMESPACE"))
        parser2.add_argument("--eventhub-name", default=os.environ.get("EVENTHUB_NAME") or os.environ.get("EVENT_HUB_NAME") or "telemetry-stream")
        args2 = parser2.parse_args([])
        self.assertEqual("ns-underscored", args2.eventhub_namespace)
        self.assertEqual("hub-underscored", args2.eventhub_name)

    def test_eventhub_post_failure_raises_system_exit(self):
        """Simulated Event Hub delivery failure exits with code 1 before alert classification."""
        eh_fail_resp = MagicMock()
        eh_fail_resp.status_code = 500

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", return_value=eh_fail_resp):
            with self.assertRaises(SystemExit) as cm:
                trigger_mod.run_trigger(
                    patient_id="TCGA-G6-A8L6",
                    email="alerts@example.com",
                    dry_run=False,
                    live=True,
                    eventhub_namespace="ns-test",
                    resource_group="rg-test",
                    eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                    previous_alert_epoch=100.0,
                )
            self.assertEqual(1, cm.exception.code)

    def test_baseline_seeding_logic(self):
        """Question 3: Live mode sends baseline if no telemetry in last 55m and waits >=70s; skips baseline if recent telemetry exists."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201

        # Case A: No recent telemetry in last 55m -> baseline sent, slept >= 70s, baseline_seeded = True
        kql_empty_resp = MagicMock()
        kql_empty_resp.status_code = 200
        kql_empty_resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": []}]

        kql_poll_resp = MagicMock()
        kql_poll_resp.status_code = 200
        kql_poll_resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2026-11-13T00:00:00.000Z"]]}]

        sent_payloads = []
        kql_csl_queries = []

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                data = json.loads(kwargs.get("data", b"{}").decode("utf-8"))
                sent_payloads.append(data)
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            kql_csl_queries.append(csl)
            if "ago(55m)" in csl:
                return kql_empty_resp
            return kql_poll_resp

        clock_ticks = [100.0]

        def mock_clock():
            val = clock_ticks[0]
            clock_ticks[0] += 1.0
            return val

        sleep_calls = []

        def mock_sleep(secs):
            sleep_calls.append(secs)
            clock_ticks[0] += secs

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=kql_empty_resp):
            res_a = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                sleep_fn=mock_sleep,
                time_fn=mock_clock,
                monotonic_fn=mock_clock,
                previous_alert_epoch=10.0,
            )

        self.assertTrue(res_a["baseline_seeded"])
        self.assertEqual(2, len(sent_payloads))
        self.assertEqual(97.0, sent_payloads[0]["telemetry"]["spo2"])
        self.assertEqual(80, sent_payloads[0]["telemetry"]["pr"])
        self.assertEqual(84.0, sent_payloads[1]["telemetry"]["spo2"])
        self.assertIn(70.0, sleep_calls)
        total_slept = sum(sleep_calls)
        self.assertGreaterEqual(total_slept, 70.0)

        # The baseline poll waits for this exact baseline row via its own probe id, distinct from the drop's probe.
        base_probe = sent_payloads[0]["metadata"][trigger_mod.ALERT_PROBE_FIELD]
        self.assertNotEqual(base_probe, sent_payloads[1]["metadata"][trigger_mod.ALERT_PROBE_FIELD])
        base_poll_csl = next((c for c in kql_csl_queries if f"== '{base_probe}'" in c), None)
        self.assertIsNotNone(base_poll_csl)

        # Case B: Recent telemetry in last 55m -> no baseline sent, baseline_seeded = False
        sent_payloads.clear()
        sleep_calls.clear()
        kql_csl_queries.clear()
        clock_ticks[0] = 100.0

        kql_recent_resp = MagicMock()
        kql_recent_resp.status_code = 200
        kql_recent_resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2026-11-13T00:00:00.000Z", "2026-11-13T00:00:00.000Z", "MASIMO-RADIUS7-0101"]]}]

        def mock_post_recent(url, **kwargs):
            if "servicebus" in url:
                data = json.loads(kwargs.get("data", b"{}").decode("utf-8"))
                sent_payloads.append(data)
                return eh_resp
            return kql_recent_resp

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post_recent), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=kql_empty_resp):
            res_b = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                sleep_fn=mock_sleep,
                time_fn=mock_clock,
                monotonic_fn=mock_clock,
                previous_alert_epoch=10.0,
            )

        self.assertFalse(res_b["baseline_seeded"])
        self.assertEqual(1, len(sent_payloads))
        self.assertEqual(84.0, sent_payloads[0]["telemetry"]["spo2"])
        self.assertNotIn(70.0, sleep_calls)

    def test_baseline_polling_deadline_expiry_exits_1(self):
        """Baseline polling deadline expiry exits with code 1."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201
        kql_empty_resp = MagicMock()
        kql_empty_resp.status_code = 200
        kql_empty_resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": []}]

        fake_clock = [100.0]

        def fast_clock():
            val = fake_clock[0]
            fake_clock[0] += 15.0
            return val

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=lambda url, **kw: eh_resp if "servicebus" in url else kql_empty_resp):
            with self.assertRaises(SystemExit) as cm:
                trigger_mod.run_trigger(
                    patient_id="TCGA-G6-A8L6",
                    email="alerts@example.com",
                    dry_run=False,
                    live=True,
                    eventhub_namespace="ns-test",
                    resource_group="rg-test",
                    eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                    sleep_fn=lambda _: None,
                    time_fn=fast_clock,
                    monotonic_fn=fast_clock,
                )
            self.assertEqual(1, cm.exception.code)

    def test_settle_seconds_invokes_sleep_before_drop(self):
        """--settle-seconds parameter delays execution by configured seconds before baseline and drop."""
        sleep_calls = []

        def mock_sleep(secs):
            sleep_calls.append(secs)

        res = trigger_mod.run_trigger(
            patient_id="TCGA-G6-A8L6",
            email="alerts@example.com",
            dry_run=True,
            settle_seconds=70.0,
            sleep_fn=mock_sleep,
        )
        self.assertIn(70.0, sleep_calls)
        self.assertEqual("PLANNED", res["status"])

    def test_drop_payload_timestamp_matches_t0(self):
        """SpO2 drop payload timestamp matches t0_str and is generated at drop time."""
        res = trigger_mod.run_trigger(
            patient_id="TCGA-G6-A8L6",
            email="alerts@example.com",
            dry_run=True,
            current_time_epoch=1234567.89,
        )
        payload_ts = res["payload"]["timestamp"]
        self.assertEqual("1970-01-15T06:56:07.890Z", payload_ts)
        # Dry run shows the planned payload but no emitted T0 observation.
        self.assertIsNone(res["beats"][0]["timestamp"])
        self.assertEqual("planned", res["beats"][0]["status"])

    def test_kql_query_uses_configured_cooldown_in_t2(self):
        """fn_ClinicalAlerts query in T2 uses configured cooldown_minutes."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201
        kql_queries = []
        kql_resp = MagicMock()
        kql_resp.status_code = 200
        kql_resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2026-11-13T00:00:00.000Z"]]}]

        def capture_post(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            kql_queries.append(csl)
            return kql_resp

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=capture_post), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=kql_resp):
            # Bounded fake clock/sleep so the T1/T2 deadlines never sleep in real time.
            fake_now = [1763000000.0]
            trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                cooldown_minutes=25,
                previous_alert_epoch=10.0,
                sleep_fn=lambda s: fake_now.__setitem__(0, fake_now[0] + s),
                time_fn=lambda: fake_now[0],
                monotonic_fn=lambda: fake_now[0],
            )

        t2_query = next((q for q in kql_queries if "fn_ClinicalAlerts(25)" in q), None)
        self.assertIsNotNone(t2_query)
        self.assertIn("where tostring(device_id) == 'MASIMO-RADIUS7-0101'", t2_query)

    def test_live_history_query_uses_qualifying_reading_and_shared_lookback(self):
        """F-1, F-2, F-4 (M2, M3): History query filters TelemetryRaw by qualifying tier and exact cooldown_minutes lookback."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201

        kql_queries = []
        # Prior qualifying reading was at epoch 1000.0 (2026-11-13T00:16:40.000Z), drop is at 1300.0 (delta = 300s < 590s -> SUPPRESSED_DEDUPE)
        t_prev = 1763000000.0
        t_drop = t_prev + 300.0
        prev_iso = "2025-11-13T02:13:20.000Z"  # epoch 1763000000.0

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            kql_queries.append(csl)
            resp = MagicMock()
            resp.status_code = 200
            if "summarize max(todatetime(timestamp))" in csl:
                # Simulate KQL ago(lookback) evaluation: only return prev_iso if query uses ago(790s) (12m + 70s)
                if "ago(790s)" in csl and "where alert_tier in ('CRITICAL')" in csl:
                    resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[prev_iso, False]]}]
                else:
                    resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[None, False]]}]
            else:
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2025-11-13T02:18:20.000Z"]]}]
            return resp

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post):
            res = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                cooldown_minutes=12,
                min_tier="CRITICAL",
                sleep_fn=lambda _: None,
                time_fn=lambda: t_drop,
                monotonic_fn=lambda: t_drop,
            )

        self.assertEqual("SUPPRESSED_DEDUPE", res["status"])
        self.assertTrue(res["suppressed_by_dedupe"])
        self.assertFalse(res["email_expected"])
        self.assertFalse(res["dispatch_observed"])

    def test_emulator_normal_readings_after_qualifying_drop_do_not_mask_dedupe(self):
        """F-1 (A1/A2/A3): Normal emulator readings after an earlier qualifying drop do not reset or extend qualifying timestamp."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201
        t_prev_qualifying = 1763000000.0
        # Case A1: 720s after qualifying drop, emulator has emitted normal (SpO2 98%) readings every second up to now.
        # Because 720s > 10m lookback, TelemetryRaw qualifying query in ago(10m) returns [[None]] -> DISPATCHED.
        t_drop_a1 = t_prev_qualifying + 720.0

        def mock_post_a1(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            resp = MagicMock()
            resp.status_code = 200
            if "summarize max(todatetime(timestamp))" in csl:
                # Only qualifying rows in ago(10m) are returned; normal rows (spo2=98, pr=75) are filtered out by alert_tier in (...)
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[None, False]]}]
            else:
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2025-11-13T02:25:20.000Z"]]}]
            return resp

        graph_resp = MagicMock()
        graph_resp.status_code = 200
        graph_resp.json.return_value = {"value": []}

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post_a1), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=graph_resp):
            res_a1 = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                cooldown_minutes=10,
                min_tier="URGENT",
                sleep_fn=lambda _: None,
                time_fn=lambda: t_drop_a1,
                monotonic_fn=lambda: t_drop_a1,
            )

        # Eligibility is only a prediction: an empty mailbox leaves dispatch unobserved, never DISPATCHED.
        self.assertEqual("DISPATCH_NOT_OBSERVED", res_a1["status"])
        self.assertEqual("EXPECTED_DISPATCH", res_a1["expected_outcome"])
        self.assertFalse(res_a1["suppressed_by_dedupe"])
        self.assertTrue(res_a1["email_expected"])
        self.assertFalse(res_a1["dispatch_observed"])

    def test_history_query_failure_classifies_as_uncertain_and_logs_warning(self):
        """F-1: A failed Eventhouse history query must not fall back to DISPATCHED silently; it logs and classifies as UNCERTAIN_BOUNDARY."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201

        def mock_post_fail(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            resp = MagicMock()
            if "summarize max(todatetime(timestamp))" in csl:
                resp.status_code = 500
                resp.text = "Internal Kusto Error"
                return resp
            resp.status_code = 200
            resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2025-11-13T02:25:20.000Z"]]}]
            return resp

        stderr_capture = io.StringIO()
        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post_fail), \
             patch("sys.stderr", stderr_capture):
            res = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                sleep_fn=lambda _: None,
                time_fn=lambda: 1763000500.0,
                monotonic_fn=lambda: 1763000500.0,
            )

        self.assertEqual("UNCERTAIN_BOUNDARY", res["status"])
        self.assertFalse(res["suppressed_by_dedupe"])
        self.assertFalse(res["email_expected"])
        self.assertIn("Eventhouse alert history query failed", stderr_capture.getvalue())
        self.assertIn("Eventhouse alert history query failed", res.get("boundary_notice", ""))

    @staticmethod
    def _kusto_response(rows=None, status_code=200, text=""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = text
        resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": rows if rows is not None else []}]
        return resp

    def _run_live_against_history(self, history_answer, t_drop, min_tier="URGENT"):
        """Run a live trigger whose history query is answered by history_answer(csl); other Eventhouse polls see the probe."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            if "summarize max(todatetime(timestamp))" in csl:
                return history_answer(csl)
            return self._kusto_response([["2025-11-13T02:25:20.000Z"]])

        graph_resp = MagicMock()
        graph_resp.status_code = 200
        graph_resp.json.return_value = {"value": []}

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=graph_resp), \
             patch("sys.stderr", io.StringIO()):
            return trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                cooldown_minutes=10,
                min_tier=min_tier,
                sleep_fn=lambda _: None,
                time_fn=lambda: t_drop,
                monotonic_fn=lambda: t_drop,
            )

    def test_high_risk_escalation_inside_cooldown_suppresses_dispatch(self):
        """A high-risk patient's 92.4% reading 240 s before the drop is URGENT in fn_ClinicalAlerts, so the Reflex sends no email."""
        t_drop = 1763001000.0
        reading_iso = trigger_mod.format_iso_timestamp(t_drop - 240.0)

        def eventhouse(csl):
            # Eventhouse holds one natural 92.4% reading (base tier WARNING). The device's linked patient has a
            # high-risk condition in SilverCondition, so fn_ClinicalAlerts rates the reading URGENT. A history query
            # sees that tier only when it joins the patient's conditions the way fn_ClinicalAlerts does.
            tier = "URGENT" if "SilverCondition" in csl else "WARNING"
            row = [reading_iso if tier in trigger_mod.tiers_at_or_above("URGENT") else None]
            if "has_high_risk" in csl:
                row.append(True)
            return self._kusto_response([row])

        res = self._run_live_against_history(eventhouse, t_drop)

        self.assertEqual("SUPPRESSED_DEDUPE", res["status"])
        self.assertTrue(res["suppressed_by_dedupe"])
        self.assertFalse(res["email_expected"])

    def test_unknown_high_risk_escalation_is_uncertain(self):
        """If the patient high-risk escalation cannot be determined, the trigger never predicts a dispatch."""
        t_drop = 1763001000.0

        def condition_table_unavailable(csl):
            if "SilverCondition" in csl:
                return self._kusto_response(status_code=400, text="Failed to resolve table expression named 'SilverCondition'")
            return self._kusto_response([[None]])

        def high_risk_flag_missing(csl):
            return self._kusto_response([[None]])

        for name, answer in (("condition_table_unavailable", condition_table_unavailable), ("high_risk_flag_missing", high_risk_flag_missing)):
            with self.subTest(case=name):
                res = self._run_live_against_history(answer, t_drop)
                self.assertEqual("UNCERTAIN_BOUNDARY", res["status"])
                self.assertFalse(res["email_expected"])
                self.assertIn("Eventhouse alert history query failed", res.get("boundary_notice", ""))

    def test_failed_beat_polls_report_last_query_error(self):
        """When every T1 and T2 poll fails, the JSON result and the stderr failure message carry the Eventhouse error."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201
        denied = "Forbidden: principal has no viewer role on database MasimoEventhouse"

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            if "ago(55m)" in csl:
                return self._kusto_response([["2025-11-13T02:00:00.000Z"]])
            if "summarize max(todatetime(timestamp))" in csl:
                return self._kusto_response([[None, False]])
            return self._kusto_response(status_code=403, text=denied)

        graph_resp = MagicMock()
        graph_resp.status_code = 200
        graph_resp.json.return_value = {"value": []}
        fake_time = [1763000000.0]

        def advancing_clock():
            fake_time[0] += 16.0
            return fake_time[0]

        argv = [
            "trigger_spo2_alert.py", "--live", "--json",
            "--eventhub-namespace", "ns-test",
            "--resource-group", "rg-test",
            "--eventhouse-query-uri", "https://eh.kusto.fabric.microsoft.com",
        ]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch("sys.stderr", stderr), \
             patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=graph_resp), \
             patch("scripts.trigger_spo2_alert.time.sleep"), \
             patch("scripts.trigger_spo2_alert.time.time", side_effect=advancing_clock), \
             patch("scripts.trigger_spo2_alert.time.monotonic", side_effect=advancing_clock):
            rc = trigger_mod.main()

        self.assertEqual(1, rc)
        result = json.loads(stdout.getvalue())
        self.assertIn(denied, result["poll_errors"]["t1"])
        self.assertIn(denied, result["poll_errors"]["t2"])
        failure = next(line for line in stderr.getvalue().splitlines() if "Live alert verification failed" in line)
        self.assertIn(f"T1 observed=False (last query error: HTTP 403: {denied})", failure)
        self.assertIn(f"T2 observed=False (last query error: HTTP 403: {denied})", failure)

    def _run_live_cli_against_timed_eventhouse(self, timings, honor_timeout=True, graph_pages=None, wall_rollback=None):
        """Run the live CLI against a fake Eventhouse on a fake clock; return (exit code, JSON result, stderr, query log).

        timings maps a query kind (recent, history, t1, t2) to (seconds, has_row) for its successive calls; the last entry
        repeats. With honor_timeout, a query slower than its request timeout raises ReadTimeout once that timeout has
        elapsed, as requests does; without it, the transport returns late anyway. wall_rollback=(kind, seconds) steps the
        local UTC clock (time.time) back by seconds when the first query of that kind (including "graph") starts, while
        elapsed time (time.monotonic) and the service-side timestamps keep advancing.
        """
        script = {"recent": [(0.4, True)], "history": [(0.4, True)], "t1": [(0.4, True)], "t2": [(0.4, True)]}
        script.update(timings)
        now = [1763000000.0]
        queries = []  # (kind, start, timeout)
        wall_offset = [0.0]
        eh_resp = MagicMock()
        eh_resp.status_code = 201
        emitted_events = []

        def kind_of(csl):
            if "ago(55m)" in csl:
                return "recent"
            if "summarize max(todatetime(timestamp))" in csl:
                return "history"
            return "t2" if "fn_ClinicalAlerts" in csl else "t1"

        def roll_wall_clock_back(kind):
            if wall_rollback is not None and wall_rollback[0] == kind and not any(q[0] == kind for q in queries):
                wall_offset[0] -= wall_rollback[1]

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                emitted_events.append(json.loads(kwargs["data"]))
                return eh_resp
            kind = kind_of(kwargs["json"]["csl"])
            start, timeout = now[0], kwargs["timeout"]
            seconds, has_row = script[kind][min(sum(1 for q in queries if q[0] == kind), len(script[kind]) - 1)]
            roll_wall_clock_back(kind)
            queries.append((kind, start, timeout))
            if honor_timeout and seconds > timeout:
                now[0] += timeout
                raise trigger_mod.requests.exceptions.ReadTimeout(f"Read timed out. (read timeout={timeout})")
            now[0] += seconds
            stamp = trigger_mod.format_iso_timestamp(now[0])
            rows = {
                "recent": [[stamp, stamp, "MASIMO-RADIUS7-0101"]],
                "history": [[None, False]],
                "t1": [[stamp]],
                "t2": [[stamp, stamp, "CRITICAL", "SpO2", 84.0, 115]],
            }[kind]
            return self._kusto_response(rows if has_row else [])

        def advance(seconds):
            now[0] += seconds

        graph_resp = MagicMock()
        graph_resp.status_code = 200
        graph_resp.json.return_value = {"value": []}

        def mock_get(url, **kwargs):
            if graph_pages is None:
                return graph_resp
            page_index = sum(1 for query in queries if query[0] == "graph")
            seconds, matches = graph_pages[min(page_index, len(graph_pages) - 1)]
            start, timeout = now[0], kwargs["timeout"]
            roll_wall_clock_back("graph")
            queries.append(("graph", start, timeout))
            if honor_timeout and seconds > timeout:
                now[0] += timeout
                raise trigger_mod.requests.exceptions.ReadTimeout(f"Read timed out. (read timeout={timeout})")
            now[0] += seconds
            event = emitted_events[-1]
            message = {
                "subject": f"Alert {event['device_id']} {trigger_mod.alert_probe_subject_marker(event['metadata'][trigger_mod.ALERT_PROBE_FIELD])}",
                "receivedDateTime": trigger_mod.format_iso_timestamp(now[0]),
            }
            response = MagicMock()
            response.status_code = 200
            body = {"value": [message] if matches else []}
            if page_index + 1 < len(graph_pages):
                body["@odata.nextLink"] = f"https://graph.microsoft.com/v1.0/me/messages?skip={page_index + 1}"
            response.json.return_value = body
            return response

        os.environ.pop("FHIR_SERVICE_URL", None)
        os.environ.pop("FHIR_URL", None)
        argv = [
            "trigger_spo2_alert.py", "--live", "--json",
            "--eventhub-namespace", "ns-test",
            "--resource-group", "rg-test",
            "--eventhouse-query-uri", "https://eh.kusto.fabric.microsoft.com",
        ]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", argv), patch("sys.stdout", stdout), patch("sys.stderr", stderr), \
             patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post), \
             patch("scripts.trigger_spo2_alert.requests.get", side_effect=mock_get), \
             patch("scripts.trigger_spo2_alert.time.sleep", side_effect=advance), \
             patch("scripts.trigger_spo2_alert.time.time", side_effect=lambda: now[0] + wall_offset[0]), \
             patch("scripts.trigger_spo2_alert.time.monotonic", side_effect=lambda: now[0]):
            rc = trigger_mod.main()
        return rc, json.loads(stdout.getvalue()), stderr.getvalue(), queries

    def test_slow_valid_history_and_t2_queries_are_observed(self):
        """Valid history and T2 queries that take 12 s (longer than a 10 s request timeout) succeed inside the 30 s window."""
        rc, result, stderr, _ = self._run_live_cli_against_timed_eventhouse({"history": [(12.0, True)], "t2": [(12.0, True)]})

        self.assertEqual(0, rc, stderr)
        self.assertEqual("EXPECTED_DISPATCH", result["expected_outcome"])
        self.assertNotIn("Eventhouse alert history query failed", stderr)
        beats = {b["id"]: b for b in result["beats"]}
        self.assertEqual("completed", beats["eventstream_enqueued"]["status"])
        self.assertEqual("completed", beats["kql_detected"]["status"])
        self.assertIsNone(result["poll_errors"]["t2"])

    def test_eventhouse_queries_stay_inside_observation_deadline(self):
        """Request timeouts use the remaining budget; failed polls retain their error and late rows are not observed."""
        deadline = trigger_mod.KQL_OBSERVATION_DEADLINE_SECONDS
        cases = (
            # The first T2 poll returns no alert row after 12 s; the next poll gets only the remaining budget and times out.
            ("transport_timeout", {"history": [(40.0, True)], "t2": [(12.0, False), (40.0, True)]}, True),
            # A transport that ignores its timeout returns a valid T2 row after the window has closed.
            ("late_success", {"t2": [(40.0, True)]}, False),
        )
        for name, timings, honor_timeout in cases:
            with self.subTest(case=name):
                rc, result, stderr, queries = self._run_live_cli_against_timed_eventhouse(timings, honor_timeout)

                self.assertEqual(1, rc)
                beats = {b["id"]: b for b in result["beats"]}
                self.assertEqual("completed", beats["eventstream_enqueued"]["status"])
                self.assertEqual("not_observed", beats["kql_detected"]["status"])
                self.assertIn("T2 observed=False", stderr)
                history = next(q for q in queries if q[0] == "history")
                self.assertLessEqual(history[2], deadline)
                t2_polls = [q for q in queries if q[0] == "t2"]
                for _, start, timeout in t2_polls:
                    self.assertLessEqual(start + timeout, t2_polls[0][1] + deadline)
                if honor_timeout:
                    self.assertEqual(2, len(t2_polls))
                    self.assertEqual("UNCERTAIN_BOUNDARY", result["status"])
                    self.assertIn("Read timed out", result["boundary_notice"])
                    self.assertIn("Read timed out", result["poll_errors"]["t2"])
                    self.assertIn("T2 observed=False (last query error: Read timed out", stderr)
                else:
                    self.assertEqual("EXPECTED_DISPATCH", result["expected_outcome"])
                    self.assertIsNone(beats["kql_detected"]["timestamp"])

    def test_poll_refreshes_budget_after_process_pause(self):
        """A process pause must not consume expired network time or retain the initial timeout."""
        for pause in (12.0, 31.0):
            with self.subTest(pause=pause):
                now = [0.0]
                requests_started = []

                def clock():
                    before_pause = now[0]
                    now[0] = pause
                    return before_pause

                def request(budget):
                    requests_started.append((now[0], budget))
                    return "observed"

                result = trigger_mod.poll_until(clock, lambda _: None, 30.0, 3.0, request)
                if pause < 30.0:
                    self.assertEqual("observed", result)
                    self.assertEqual([(pause, 30.0 - pause)], requests_started)
                else:
                    self.assertIsNone(result)
                    self.assertEqual([], requests_started)

    def test_mailbox_pages_share_one_observation_deadline(self):
        """A delayed second page cannot count an email after the mailbox observation window."""
        with patch.object(trigger_mod, "GRAPH_OBSERVATION_DEADLINE_SECONDS", 20.0):
            rc, result, stderr, queries = self._run_live_cli_against_timed_eventhouse(
                {}, graph_pages=[(12.0, False), (12.0, True)],
            )
        self.assertEqual(0, rc, stderr)
        self.assertEqual("DISPATCH_NOT_OBSERVED", result["status"])
        self.assertFalse(result["dispatch_observed"])
        self.assertIn("Read timed out", result["graph_error"])
        beat = next(beat for beat in result["beats"] if beat["id"] == "activator_dispatched")
        self.assertEqual("not_observed", beat["status"])
        self.assertIsNone(beat["timestamp"])
        graph_queries = [query for query in queries if query[0] == "graph"]
        deadline = graph_queries[0][1] + 20.0
        for _, start, timeout in graph_queries:
            self.assertLess(start, deadline)
            self.assertLessEqual(start + timeout, deadline)

    def test_utc_rollback_does_not_grow_mailbox_page_budget(self):
        """A backward UTC step during the first mailbox page leaves the second page only the elapsed-time budget."""
        with patch.object(trigger_mod, "GRAPH_OBSERVATION_DEADLINE_SECONDS", 20.0):
            rc, result, stderr, queries = self._run_live_cli_against_timed_eventhouse(
                {}, graph_pages=[(12.0, False), (12.0, True)], wall_rollback=("graph", 100.0),
            )
        self.assertEqual(0, rc, stderr)
        self.assertEqual("DISPATCH_NOT_OBSERVED", result["status"])
        self.assertFalse(result["dispatch_observed"])
        self.assertIsNone(result["graph_msg"])
        self.assertIn("Read timed out", result["graph_error"])
        graph_queries = [query for query in queries if query[0] == "graph"]
        self.assertEqual(2, len(graph_queries))
        first_start = graph_queries[0][1]
        for _, start, timeout in graph_queries:
            self.assertLessEqual(start + timeout, first_start + 20.0)
        self.assertLessEqual(graph_queries[1][2], 20.0 - 12.0)
        beats = {b["id"]: b for b in result["beats"]}
        self.assertEqual("not_observed", beats["activator_dispatched"]["status"])
        self.assertIsNone(beats["activator_dispatched"]["timestamp"])
        # T0 was taken before the adjustment and stays the real UTC emission time.
        expected_t0 = trigger_mod.format_iso_timestamp(1763000000.0 + 0.4 + 0.4)
        self.assertEqual(expected_t0, result["payload"]["timestamp"])
        self.assertEqual(expected_t0, beats["telemetry_emitted"]["timestamp"])

    def test_injected_utc_rollback_does_not_extend_eventhouse_window(self):
        """run_trigger with separate UTC and monotonic clocks rejects a T1 row that arrives after 31 elapsed seconds
        even though UTC moved back 100 s during the query; UTC still supplies T0 and the payload timestamp."""
        wall_start = 1763000000.0
        elapsed = [0.0]
        wall_offset = [0.0]
        t1_starts = []
        eh_resp = MagicMock()
        eh_resp.status_code = 201

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs["json"]["csl"]
            if "ago(55m)" in csl:
                return self._kusto_response([["2025-11-13T02:00:00.000Z", "2025-11-13T02:00:00.000Z", "MASIMO-RADIUS7-0101"]])
            if "summarize max(todatetime(timestamp))" in csl:
                return self._kusto_response([[None, False]])
            if "fn_ClinicalAlerts" in csl:
                return self._kusto_response([])
            # T1: the row arrives after 31 s of elapsed time while the local UTC clock steps back 100 s.
            t1_starts.append((elapsed[0], kwargs["timeout"]))
            elapsed[0] += 31.0
            wall_offset[0] -= 100.0
            return self._kusto_response([[trigger_mod.format_iso_timestamp(wall_start + elapsed[0])]])

        graph_resp = MagicMock()
        graph_resp.status_code = 200
        graph_resp.json.return_value = {"value": []}

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=graph_resp):
            res = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                sleep_fn=lambda s: elapsed.__setitem__(0, elapsed[0] + s),
                time_fn=lambda: wall_start + elapsed[0] + wall_offset[0],
                monotonic_fn=lambda: elapsed[0],
            )

        self.assertEqual(1, len(t1_starts))
        self.assertLessEqual(t1_starts[0][1], trigger_mod.KQL_OBSERVATION_DEADLINE_SECONDS)
        beats = {b["id"]: b for b in res["beats"]}
        self.assertEqual("not_observed", beats["eventstream_enqueued"]["status"])
        self.assertIsNone(beats["eventstream_enqueued"]["timestamp"])
        self.assertIsNone(res["t_ingest"])
        expected_t0 = trigger_mod.format_iso_timestamp(wall_start)
        self.assertEqual(expected_t0, res["payload"]["timestamp"])
        self.assertEqual(expected_t0, beats["telemetry_emitted"]["timestamp"])

    def test_live_drop_payload_timestamp_matches_graph_filter_after_settle(self):
        """F-4 (M9): In live mode with settle delay, payload['timestamp'] is updated at drop time and equals the Graph filter timestamp."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201
        kql_resp = MagicMock()
        kql_resp.status_code = 200

        sent_payloads = []

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                sent_payloads.append(json.loads(kwargs.get("data", b"{}").decode("utf-8")))
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            if "ago(55m)" in csl:
                r = MagicMock()
                r.status_code = 200
                r.json.return_value = [{"TableKind": "PrimaryResult", "Rows": []}]
                return r
            if "summarize max(todatetime(timestamp))" in csl:
                r = MagicMock()
                r.status_code = 200
                r.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[None, False]]}]
                return r
            kql_resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2025-11-13T02:20:00.000Z"]]}]
            return kql_resp
        graph_urls = []

        def mock_get(url, **kwargs):
            graph_urls.append(url)
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {
                "value": [
                    {
                        "subject": "Clinical Alert: MASIMO-RADIUS7-0101",
                        "receivedDateTime": "2025-11-13T02:14:40Z",
                        "from": {"emailAddress": {"address": "activator@example.com"}},
                    }
                ]
            }
            return r

        clock_val = [1763000000.0]  # 2025-11-13T02:13:20.000Z at run start

        def advancing_sleep(secs):
            clock_val[0] += secs

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post), \
             patch("scripts.trigger_spo2_alert.requests.get", side_effect=mock_get):
            res = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                sleep_fn=advancing_sleep,
                time_fn=lambda: clock_val[0],
                monotonic_fn=lambda: clock_val[0],
            )

        # Run started at 1763000000.0 (02:13:20.000Z), baseline seeded (3s poll + 70s settle) -> drop at 1763000073.0 (02:14:33.000Z)
        self.assertEqual("2025-11-13T02:14:33.000Z", res["payload"]["timestamp"])
        self.assertEqual(res["payload"]["timestamp"], sent_payloads[-1]["timestamp"])
        self.assertTrue(len(graph_urls) > 0)
        self.assertIn(f"receivedDateTime ge {res['payload']['timestamp']}", graph_urls[0])

    def test_cleanup_returns_non_success_status_and_exit_code(self):
        """F-3: --cleanup returns UNSUPPORTED_CLEANUP and exits non-zero because Eventhouse dedupe state cannot be safely reset."""
        res = trigger_mod.run_trigger(cleanup=True)
        self.assertEqual("UNSUPPORTED_CLEANUP", res["status"])
        self.assertIn("cannot reset Eventhouse deduplication state", res["message"])

        with patch("sys.argv", ["trigger_spo2_alert.py", "--cleanup", "--json"]), \
             patch("sys.stdout", io.StringIO()) as out:
            rc = trigger_mod.main()
            self.assertEqual(1, rc)
            parsed = json.loads(out.getvalue())
            self.assertEqual("UNSUPPORTED_CLEANUP", parsed["status"])

    def test_shared_poll_and_latency_constants(self):
        """Answer 2: P (60s), L (10s), and REFLEX_SETTLE_SECONDS (70s) are shared from deploy_clinical_activator."""
        self.assertEqual(60.0, activator_mod.ACTIVATOR_POLL_INTERVAL_SECONDS)
        self.assertEqual(10.0, activator_mod.INGEST_LATENCY_ALLOWANCE_SECONDS)
        self.assertEqual(70.0, activator_mod.REFLEX_SETTLE_SECONDS)
        self.assertIs(trigger_mod.ACTIVATOR_POLL_INTERVAL_SECONDS, activator_mod.ACTIVATOR_POLL_INTERVAL_SECONDS)
        self.assertIs(trigger_mod.REFLEX_SETTLE_SECONDS, activator_mod.REFLEX_SETTLE_SECONDS)

    def test_history_query_malformed_and_inband_errors_behave_as_uncertain(self):
        """P1 (R-2): Missing PrimaryResult, empty Rows, malformed timestamp, or Kusto in-band error mark history uncertain."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201

        test_cases = [
            ("missing_primary", [{"TableKind": "DataSetHeader"}]),
            ("empty_rows", [{"TableKind": "PrimaryResult", "Rows": []}]),
            ("malformed_ts", [{"TableKind": "PrimaryResult", "Rows": [["not_a_valid_timestamp"]]}]),
            ("inband_error_frame", [{"TableKind": "Error", "ErrorMessage": "Syntax error"}]),
            ("inband_has_errors", [{"TableKind": "PrimaryResult", "Rows": [["2025-11-13T02:13:20.000Z"]]}, {"HasErrors": True}]),
        ]

        for case_name, frames in test_cases:
            with self.subTest(case=case_name):
                def mock_post(url, **kwargs):
                    if "servicebus" in url:
                        return eh_resp
                    csl = kwargs.get("json", {}).get("csl", "")
                    resp = MagicMock()
                    resp.status_code = 200
                    if "summarize max(todatetime(timestamp))" in csl:
                        resp.json.return_value = frames
                    else:
                        resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2025-11-13T02:25:20.000Z"]]}]
                    return resp

                with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
                     patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post):
                    res = trigger_mod.run_trigger(
                        patient_id="TCGA-G6-A8L6",
                        email="alerts@example.com",
                        dry_run=False,
                        live=True,
                        eventhub_namespace="ns-test",
                        resource_group="rg-test",
                        eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                        sleep_fn=lambda _: None,
                        time_fn=lambda: 1763000500.0,
                        monotonic_fn=lambda: 1763000500.0,
                    )
                self.assertEqual("UNCERTAIN_BOUNDARY", res["status"])
                self.assertFalse(res["email_expected"])

    def test_valid_null_aggregate_proves_no_history(self):
        """P1 (R-2): A one-row null aggregate [[None]] proves no history -> EXPECTED_DISPATCH; with no email seen the status is DISPATCH_NOT_OBSERVED."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            resp = MagicMock()
            resp.status_code = 200
            if "summarize max(todatetime(timestamp))" in csl:
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[None, False]]}]
            else:
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2025-11-13T02:25:20.000Z"]]}]
            return resp

        graph_resp = MagicMock()
        graph_resp.status_code = 200
        graph_resp.json.return_value = {"value": []}

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=graph_resp):
            res = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                sleep_fn=lambda _: None,
                time_fn=lambda: 1763000500.0,
                monotonic_fn=lambda: 1763000500.0,
            )
        self.assertEqual("DISPATCH_NOT_OBSERVED", res["status"])
        self.assertTrue(res["email_expected"])
        self.assertFalse(res["dispatch_observed"])

    def test_live_history_wpl_boundary_band_edges(self):
        """P1 (R-1, R-9): Delta classification across both edges of W + P + L window."""
        # W=600s (10m), P=60s, L=10s. W-L=590s, W+P+L=670s.
        t_drop = 1763001000.0
        eh_resp = MagicMock()
        eh_resp.status_code = 201

        graph_resp = MagicMock()
        graph_resp.status_code = 200
        graph_resp.json.return_value = {"value": []}

        cases = [
            (589.0, "SUPPRESSED_DEDUPE", True, False),
            (590.0, "UNCERTAIN_BOUNDARY", False, False),
            (600.0, "UNCERTAIN_BOUNDARY", False, False),
            (650.0, "UNCERTAIN_BOUNDARY", False, False),
            (670.0, "UNCERTAIN_BOUNDARY", False, False),
            (671.0, "DISPATCH_NOT_OBSERVED", False, True),
        ]

        for delta, exp_status, exp_suppressed, exp_email in cases:
            with self.subTest(delta=delta):
                t_prev = t_drop - delta
                prev_iso = trigger_mod.format_iso_timestamp(t_prev)

                def mock_post(url, **kwargs):
                    if "servicebus" in url:
                        return eh_resp
                    csl = kwargs.get("json", {}).get("csl", "")
                    resp = MagicMock()
                    resp.status_code = 200
                    if "summarize max(todatetime(timestamp))" in csl:
                        resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[prev_iso, False]]}]
                    else:
                        resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2025-11-13T02:25:20.000Z"]]}]
                    return resp

                with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
                     patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post), \
                     patch("scripts.trigger_spo2_alert.requests.get", return_value=graph_resp):
                    res = trigger_mod.run_trigger(
                        patient_id="TCGA-G6-A8L6",
                        email="alerts@example.com",
                        dry_run=False,
                        live=True,
                        eventhub_namespace="ns-test",
                        resource_group="rg-test",
                        eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                        cooldown_minutes=10,
                        sleep_fn=lambda _: None,
                        time_fn=lambda: t_drop,
                        monotonic_fn=lambda: t_drop,
                    )
                self.assertEqual(exp_status, res["status"])
                self.assertEqual(exp_suppressed, res["suppressed_by_dedupe"])
                self.assertEqual(exp_email, res["email_expected"])

    def test_live_history_pr_critical_predicate(self):
        """P2 (R-5): History uses the deployed critical PR predicate (pr > 150 or pr < 40, no positivity filter)."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201
        captured_csl = []

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            captured_csl.append(csl)
            resp = MagicMock()
            resp.status_code = 200
            if "summarize max(todatetime(timestamp))" in csl:
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[None]]}]
            else:
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [["2025-11-13T02:25:20.000Z"]]}]
            return resp

        graph_resp = MagicMock()
        graph_resp.status_code = 200
        graph_resp.json.return_value = {"value": []}

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post), \
             patch("scripts.trigger_spo2_alert.requests.get", return_value=graph_resp):
            trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                sleep_fn=lambda _: None,
                time_fn=lambda: 1763000500.0,
                monotonic_fn=lambda: 1763000500.0,
            )

        hist_query = next((q for q in captured_csl if "summarize max(todatetime(timestamp))" in q), "")
        self.assertIn("pr > 150 or pr < 40", hist_query)

    def test_stale_row_timing_not_observed(self):
        """P1 (R-3): Stale row with timestamp older than drop is rejected, resulting in not_observed beat."""
        eh_resp = MagicMock()
        eh_resp.status_code = 201

        t0_live = 1763000500.0  # drop timestamp
        stale_ts = "2025-11-13T02:00:00.000Z"  # older than drop

        def mock_post(url, **kwargs):
            if "servicebus" in url:
                return eh_resp
            csl = kwargs.get("json", {}).get("csl", "")
            resp = MagicMock()
            resp.status_code = 200
            if "summarize max(todatetime(timestamp))" in csl:
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[None]]}]
            elif "TelemetryRaw" in csl:
                # Return stale row older than t0
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[stale_ts]]}]
            elif "fn_ClinicalAlerts" in csl:
                # Return stale alert row older than t0
                resp.json.return_value = [{"TableKind": "PrimaryResult", "Rows": [[stale_ts]]}]
            return resp

        # In calculate_stopwatch, stale t1 < t0 produces None, not 0.0
        sw = trigger_mod.calculate_stopwatch(t0=100.0, t1=90.0, t2=80.0, t3=70.0)
        self.assertIsNone(sw["t_ingest"])
        self.assertIsNone(sw["t_detect"])
        self.assertIsNone(sw["t_action"])
        self.assertIsNone(sw["t_total"])

        clock_val = [t0_live]
        def advancing_sleep(secs):
            clock_val[0] += secs

        with patch("scripts.trigger_spo2_alert.get_msal_token", return_value="tok"), \
             patch("scripts.trigger_spo2_alert.requests.post", side_effect=mock_post):
            res = trigger_mod.run_trigger(
                patient_id="TCGA-G6-A8L6",
                email="alerts@example.com",
                dry_run=False,
                live=True,
                eventhub_namespace="ns-test",
                resource_group="rg-test",
                eventhouse_query_uri="https://eh.kusto.fabric.microsoft.com",
                sleep_fn=advancing_sleep,
                time_fn=lambda: clock_val[0],
                monotonic_fn=lambda: clock_val[0],
            )

        beats_by_id = {b["id"]: b for b in res["beats"]}
        self.assertEqual("not_observed", beats_by_id["eventstream_enqueued"]["status"])
        self.assertEqual("not_observed", beats_by_id["kql_detected"]["status"])
        self.assertIsNone(res["t_ingest"])
        self.assertIsNone(res["t_detect"])

    def test_settle_seconds_and_min_tier_validation_exits_fast(self):
        """P2 (R-6): Invalid settle-seconds or min-tier fails fast with code 2 before external calls."""
        # Non-finite settle_seconds
        for bad_val in [float("nan"), float("inf"), -5.0]:
            with self.assertRaises(SystemExit) as cm:
                trigger_mod.run_trigger(settle_seconds=bad_val)
            self.assertEqual(2, cm.exception.code)

        # Invalid min-tier
        with self.assertRaises(SystemExit) as cm:
            trigger_mod.run_trigger(min_tier="INVALID_TIER")
        self.assertEqual(2, cm.exception.code)

if __name__ == "__main__":
    unittest.main()

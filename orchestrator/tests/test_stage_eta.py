"""Unit tests for Stage-ETA memory recording, retention, atomic write, and hosted pooling."""
import json
import logging
import math
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from shared.stage_eta import (
    CANONICAL_STAGE_KEYS,
    MAX_SAMPLES_PER_STAGE,
    SAMPLES_FILENAME,
    get_stage_etas,
    invalidate_aggregate_cache,
    load_own_samples,
    record_stage_sample,
    resolve_stage_key,
    save_own_samples,
)


class StageEtaTests(unittest.TestCase):
    def setUp(self):
        invalidate_aggregate_cache()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)

    def tearDown(self):
        invalidate_aggregate_cache()
        self.temp_dir.cleanup()

    def test_stage_key_resolution(self):
        """Phase names and add-on names resolve to canonical stage keys."""
        test_cases = [
            ("Phase 1: Fabric Workspace", "phase_1_workspace"),
            ("1a. Data Fabric Foundation: Fabric Workspace", "phase_1_workspace"),
            ("Phase 1: Base Azure Infrastructure", "phase_1_base_infra"),
            ("1b. Data Fabric Foundation: Base Azure Infrastructure", "phase_1_base_infra"),
            ("Phase 1: FHIR Service + Synthea", "phase_1_fhir"),
            ("Phase 1: DICOM Loader", "phase_1_dicom"),
            ("Phase 2: Fabric RTI", "phase_2_rti_ingest"),
            ("Phase 2: Fabric RTI Enrichment", "phase_2_rti_enrichment"),
            ("Phase 2: Fabric RTI Enrichment (auto)", "phase_2_rti_enrichment"),
            ("Phase 3: DICOM Shortcut + HDS Pipelines", "phase_3_hds_pipelines"),
            ("Phase 3: Imaging & Reporting", "phase_4_imaging"),
            ("Phase 4: Ontology", "phase_4_ontology"),
            ("Phase 4: Ontology Deployment", "phase_4_ontology"),
            ("Phase 4: Ontology-Aware Data Agents", "phase_4_agents"),
            ("Phase 2: Data Agents", "phase_2_agents"),
            ("Phase 5: Data Activator", "phase_5_alerts"),
            ("Phase 6: CMS Quality Measures", "phase_6_quality"),
            ("Phase 7: Payer RTI & Ops", "phase_7_payer_ops"),
            ("Add-on: Databricks", "addon_databricks"),
            ("Add-on: Cardiology", "addon_cardiology"),
            ("Add-on: Rayfin", "addon_rayfin"),
            ("databricks", "addon_databricks"),
            ("cardiology", "addon_cardiology"),
            ("rayfin", "addon_rayfin"),
            ("Synthetic FHIR Demo Enrichment", None),
            ("Phase 1: FHIR $export (catch-up)", None),
            ("Databricks: Preserve FHIR export", None),
        ]
        for name, expected in test_cases:
            with self.subTest(name=name):
                self.assertEqual(resolve_stage_key(name), expected)

    def test_stage_title_keys_fixture(self):
        """Verify every entry in the shared stage_title_keys.json fixture (N-5, F-4)."""
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "stage_title_keys.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        emitted_count = 0
        probe_count = 0
        for item in data:
            title = item["title"]
            expected = item["key"]
            is_emitted = item.get("emitted", False)
            if is_emitted:
                emitted_count += 1
            else:
                probe_count += 1
            with self.subTest(title=title, emitted=is_emitted):
                self.assertEqual(resolve_stage_key(title), expected)
        self.assertGreater(emitted_count, 0)
        self.assertGreater(probe_count, 0)
    def test_recording_rules_valid_duration(self):
        """Positive duration samples are recorded with timestamp and duration only."""
        now = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
        recorded = record_stage_sample(
            "Phase 1: Fabric Workspace",
            125.4,
            finished_at=now,
            data_dir=self.data_dir,
        )
        self.assertTrue(recorded)

        samples = load_own_samples(self.data_dir)
        self.assertIn("phase_1_workspace", samples)
        self.assertEqual(len(samples["phase_1_workspace"]), 1)
        sample = samples["phase_1_workspace"][0]
        self.assertEqual(sample["duration_seconds"], 125.4)
        self.assertEqual(sample["finished_at"], "2026-11-13T12:00:00+00:00")
        # Ensure no user/tenant/workspace information is leaked
        self.assertEqual(set(sample.keys()), {"duration_seconds", "finished_at"})

    def test_recording_rules_reject_zero_negative_invalid_duration(self):
        """Zero, negative, nan, and inf durations are rejected."""
        self.assertFalse(record_stage_sample("Phase 1: Fabric Workspace", 0.0, data_dir=self.data_dir))
        self.assertFalse(record_stage_sample("Phase 1: Fabric Workspace", -15.0, data_dir=self.data_dir))
        self.assertFalse(record_stage_sample("Phase 1: Fabric Workspace", float("nan"), data_dir=self.data_dir))
        self.assertFalse(record_stage_sample("Phase 1: Fabric Workspace", float("inf"), data_dir=self.data_dir))
        self.assertFalse(record_stage_sample("Phase 1: Fabric Workspace", "invalid", data_dir=self.data_dir))  # type: ignore

        samples = load_own_samples(self.data_dir)
        self.assertEqual(samples, {})

    def test_recording_rules_reject_unknown_stage(self):
        """Unknown stages without mapping are rejected."""
        self.assertFalse(record_stage_sample("Some Random Unknown Step", 60.0, data_dir=self.data_dir))
        samples = load_own_samples(self.data_dir)
        self.assertEqual(samples, {})

    def test_retention_caps_at_twenty_samples(self):
        """Each stage keeps at most 20 samples (oldest pruned)."""
        stage = "phase_1_base_infra"
        for i in range(1, 26):
            record_stage_sample(stage, float(i * 10), data_dir=self.data_dir)

        samples = load_own_samples(self.data_dir)
        self.assertEqual(len(samples[stage]), MAX_SAMPLES_PER_STAGE)
        # Should keep the last 20 (values 60 to 250)
        durations = [s["duration_seconds"] for s in samples[stage]]
        self.assertEqual(durations, [float(i * 10) for i in range(6, 26)])

    def test_atomic_write_replaces_target_file(self):
        """Atomic write uses temp file + os.replace in target directory, leaving no stale temps."""
        stage = "phase_1_fhir"
        record_stage_sample(stage, 180.0, data_dir=self.data_dir)

        target_file = self.data_dir / SAMPLES_FILENAME
        self.assertTrue(target_file.is_file())

        # Check that no .tmp files remain in data_dir
        tmp_files = list(self.data_dir.glob("*.tmp"))
        self.assertEqual(tmp_files, [])

        # Parse target file directly to confirm valid JSON
        with target_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn(stage, data)
        self.assertEqual(data[stage][0]["duration_seconds"], 180.0)

    def test_peer_aggregation_and_own_dir_skipped(self):
        """Hosted pooling reads peer directories, skips own dir to avoid double-counting, and never writes peers."""
        shared_dir = self.data_dir / "data-share"
        shared_dir.mkdir(parents=True)

        own_sandbox = shared_dir / "sandbox-me"
        own_sandbox.mkdir()

        peer1 = shared_dir / "sandbox-peer-1"
        peer1.mkdir()
        peer2 = shared_dir / "sandbox-peer-2"
        peer2.mkdir()

        # Own sandbox has 1 sample: 120s (2.0 min)
        record_stage_sample("phase_1_workspace", 120.0, data_dir=own_sandbox)

        # Peer 1 has 1 sample: 60s (1.0 min)
        record_stage_sample("phase_1_workspace", 60.0, data_dir=peer1)

        # Peer 2 has 2 samples: 180s (3.0 min), 240s (4.0 min)
        record_stage_sample("phase_1_workspace", 180.0, data_dir=peer2)
        record_stage_sample("phase_1_workspace", 240.0, data_dir=peer2)

        # Aggregate from perspective of own_sandbox
        etas = get_stage_etas(
            data_dir=own_sandbox,
            shared_data_dir=shared_dir,
            force_refresh=True,
        )

        ws_eta = etas["stages"]["phase_1_workspace"]
        # Total samples: 1 (own) + 1 (peer1) + 2 (peer2) = 4 samples
        # Durations: [120, 60, 180, 240] -> median is (120+180)/2 = 150s = 2.5 min
        self.assertEqual(ws_eta["sample_count"], 4)
        self.assertEqual(ws_eta["median_minutes"], 2.5)

        # Ensure peers were never written to (mtime / size check)
        peer1_mtime = (peer1 / SAMPLES_FILENAME).stat().st_mtime
        get_stage_etas(data_dir=own_sandbox, shared_data_dir=shared_dir, force_refresh=True)
        self.assertEqual((peer1 / SAMPLES_FILENAME).stat().st_mtime, peer1_mtime)

    def test_peer_aggregation_corrupt_file_skipped_with_warning(self):
        """Corrupt peer file is skipped with a logged warning without breaking aggregation."""
        shared_dir = self.data_dir / "data-share"
        shared_dir.mkdir(parents=True)

        own_sandbox = shared_dir / "sandbox-me"
        own_sandbox.mkdir()
        record_stage_sample("phase_1_dicom", 300.0, data_dir=own_sandbox)

        # Good peer
        good_peer = shared_dir / "good-peer"
        good_peer.mkdir()
        record_stage_sample("phase_1_dicom", 600.0, data_dir=good_peer)

        # Corrupt peer
        corrupt_peer = shared_dir / "corrupt-peer"
        corrupt_peer.mkdir()
        corrupt_file = corrupt_peer / SAMPLES_FILENAME
        corrupt_file.write_text("{broken json", encoding="utf-8")

        with self.assertLogs("shared.stage_eta", level="WARNING") as cm:
            etas = get_stage_etas(
                data_dir=own_sandbox,
                shared_data_dir=shared_dir,
                force_refresh=True,
            )

        # Warning was logged mentioning corrupt_file
        self.assertTrue(any("Could not read peer stage ETA samples" in log for log in cm.output))

        # Results still aggregated own + good peer: 2 samples [300, 600] -> median 450s = 7.5 min
        dicom_eta = etas["stages"]["phase_1_dicom"]
        self.assertEqual(dicom_eta["sample_count"], 2)
        self.assertEqual(dicom_eta["median_minutes"], 7.5)

    def test_min_sample_threshold(self):
        """When fewer than 3 samples exist, sample_count indicates insufficient data for fallback."""
        stage = "phase_4_ontology"
        # 2 samples
        record_stage_sample(stage, 240.0, data_dir=self.data_dir)
        record_stage_sample(stage, 300.0, data_dir=self.data_dir)

        etas = get_stage_etas(data_dir=self.data_dir, force_refresh=True)
        ont_eta = etas["stages"][stage]
        self.assertEqual(ont_eta["sample_count"], 2)
        # Median calculated correctly but UI knows sample_count < 3 means fallback
        self.assertEqual(ont_eta["median_minutes"], 4.5)

        # Add 3rd sample -> sample_count >= 3
        record_stage_sample(stage, 180.0, data_dir=self.data_dir)
        etas = get_stage_etas(data_dir=self.data_dir, force_refresh=True)
        ont_eta = etas["stages"][stage]
        self.assertEqual(ont_eta["sample_count"], 3)
        self.assertEqual(ont_eta["median_minutes"], 4.0)

    def test_hosted_mode_does_not_double_count_own_samples(self):
        """In hosted mode, samples in own directory inside shared_data_dir are counted once (R-4)."""
        own_dir = self.data_dir / "data"
        own_dir.mkdir(parents=True)
        shared_dir = self.data_dir / "data-share"
        own_on_share = shared_dir / "sbx-me"
        own_on_share.mkdir(parents=True)
        peer_sandbox = shared_dir / "sbx-peer"
        peer_sandbox.mkdir()

        # Record 2 samples in own sandbox and 1 in peer
        record_stage_sample("phase_1_workspace", 120.0, data_dir=own_on_share)
        record_stage_sample("phase_1_workspace", 180.0, data_dir=own_on_share)
        record_stage_sample("phase_1_workspace", 60.0, data_dir=peer_sandbox)
        # Hard link models the bind mount between /data and /data-share/sbx-me
        os.link(own_on_share / SAMPLES_FILENAME, own_dir / SAMPLES_FILENAME)

        # In hosted mode, data_dir is /data and shared_data_dir is /data-share
        etas = get_stage_etas(data_dir=own_dir, shared_data_dir=shared_dir, force_refresh=True)
        ws_eta = etas["stages"]["phase_1_workspace"]
        # Total samples: 2 own + 1 peer = 3 (NOT 5)
        self.assertEqual(ws_eta["sample_count"], 3)
        self.assertEqual(ws_eta["median_minutes"], 2.0)

    def test_step_name_reconciliations_and_enrichment_removal(self):
        """Step names are reconciled per N-1 and unrecorded steps return None."""
        self.assertIsNone(resolve_stage_key("Synthetic FHIR Demo Enrichment"))
        self.assertIsNone(resolve_stage_key("Phase 1: FHIR $export (catch-up)"))
        self.assertIsNone(resolve_stage_key("Databricks: Preserve FHIR export"))
        self.assertIsNone(resolve_stage_key("enrichment"))
        self.assertEqual(resolve_stage_key("Phase 2: Fabric RTI"), "phase_2_rti_ingest")
        self.assertEqual(resolve_stage_key("Phase 2: Fabric RTI Ingest"), "phase_2_rti_ingest")
        self.assertEqual(resolve_stage_key("Shared HDS Infrastructure"), "phase_1_base_infra")
        self.assertEqual(resolve_stage_key("Phase 1: Shared HDS Infrastructure"), "phase_1_base_infra")
        self.assertEqual(resolve_stage_key("FHIR Infrastructure Scaffold"), "phase_1_fhir")
        self.assertEqual(resolve_stage_key("Phase 1: FHIR Infrastructure Scaffold"), "phase_1_fhir")

    def test_data_agents_phase_separation(self):
        """Phase 2 Data Agents and Phase 4 Ontology-Aware Data Agents map to distinct keys (R-6)."""
        self.assertEqual(resolve_stage_key("Phase 2: Data Agents"), "phase_2_agents")
        self.assertEqual(resolve_stage_key("Phase 4: Ontology-Aware Data Agents"), "phase_4_agents")
        self.assertEqual(resolve_stage_key("Phase 4: Data Agents"), "phase_4_agents")

    def test_canonical_stages_only_schema_and_size_cap(self):
        """get_stage_etas returns only {'stages'}, canonical keys only, and skips files > 512 KiB (R-9)."""
        shared_dir = self.data_dir / "data-share"
        shared_dir.mkdir(parents=True)
        peer_dir = shared_dir / "sbx-large"
        peer_dir.mkdir()
        large_file = peer_dir / SAMPLES_FILENAME
        # Create a file over 512 KiB
        large_file.write_text(" " * (513 * 1024), encoding="utf-8")

        good_peer = shared_dir / "sbx-good"
        good_peer.mkdir()
        record_stage_sample("phase_1_workspace", 60.0, data_dir=good_peer)

        with self.assertLogs("shared.stage_eta", level="WARNING") as cm:
            etas = get_stage_etas(shared_data_dir=shared_dir, force_refresh=True)

        # Warning logged for oversized file
        self.assertTrue(any("Skipping oversized peer sample file" in log for log in cm.output))
        # Result has only {"stages": ...}
        self.assertEqual(set(etas.keys()), {"stages"})
        # All keys in stages are canonical
        self.assertEqual(set(etas["stages"].keys()), set(CANONICAL_STAGE_KEYS))
        self.assertEqual(etas["stages"]["phase_1_workspace"]["sample_count"], 1)

    def test_api_endpoint_returns_json(self):
        """Test GET /api/stage-etas returns valid schema and status 200."""
        import asyncio
        try:
            from tests import helpers
        except ImportError:
            import helpers
        local_server = helpers.get_isolated_local_server()
        helpers.assert_database_isolated()

        record_stage_sample("phase_1_workspace", 60.0, data_dir=self.data_dir)
        record_stage_sample("phase_1_workspace", 120.0, data_dir=self.data_dir)
        record_stage_sample("phase_1_workspace", 180.0, data_dir=self.data_dir)

        # Confirm route is registered on local_server.app
        endpoint = None
        for route in local_server.app.routes:
            if getattr(route, "path", None) == "/api/stage-etas" and "GET" in getattr(route, "methods", set()):
                endpoint = route.endpoint
                break
        self.assertIsNotNone(endpoint, "GET /api/stage-etas route not found on local_server.app")

        with patch("shared.stage_eta.DATA_DIR", self.data_dir):
            data = asyncio.run(endpoint())
            self.assertIn("stages", data)
            self.assertIn("phase_1_workspace", data["stages"])
            self.assertEqual(data["stages"]["phase_1_workspace"]["sample_count"], 3)
            self.assertEqual(data["stages"]["phase_1_workspace"]["median_minutes"], 2.0)

if __name__ == "__main__":
    unittest.main()

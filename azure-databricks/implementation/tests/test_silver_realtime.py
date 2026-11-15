"""Unit tests for silver_realtime alert tiering and cooldown logic."""
from __future__ import annotations

import importlib
import os
import pathlib
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch

# Ensure PySpark worker and driver use the active Python interpreter
if "PYSPARK_PYTHON" not in os.environ:
    os.environ["PYSPARK_PYTHON"] = sys.executable
if "PYSPARK_DRIVER_PYTHON" not in os.environ:
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
if "JAVA_HOME" not in os.environ:
    for candidate in [
        "/opt/homebrew/opt/openjdk@21",
        "/opt/homebrew/opt/openjdk@17",
        "/usr/lib/jvm/temurin-17-jdk-amd64",
    ]:
        if os.path.exists(candidate):
            os.environ["JAVA_HOME"] = candidate
            break

try:
    import pyspark
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.readwriter import DataFrameReader
    HAS_PYSPARK = True
except ImportError:
    HAS_PYSPARK = False

# Register stub pyspark.pipelines only when the real module is absent
if HAS_PYSPARK and "pyspark.pipelines" not in sys.modules:
    try:
        from pyspark import pipelines as _dp  # noqa: F401
    except ImportError:
        _dp_mock = types.ModuleType("pyspark.pipelines")
        _dp_mock.table = lambda *a, **kw: (lambda f: f)
        _dp_mock.materialized_view = lambda *a, **kw: (lambda f: f)
        _dp_mock.expect_or_drop = lambda *a, **kw: (lambda f: f)
        _dp_mock.expect = lambda *a, **kw: (lambda f: f)
        sys.modules["pyspark.pipelines"] = _dp_mock

SRC_DIR = pathlib.Path(__file__).resolve().parents[1] / "bundle" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@unittest.skipUnless(HAS_PYSPARK, "pyspark is not installed")
class TestClinicalAlertCooldown(unittest.TestCase):
    """Test suite for clinical alert tiering and 15-minute tumbling window cooldown."""

    spark: SparkSession
    silver_realtime: types.ModuleType

    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder.master("local[1]")
            .appName("test-clinical-alert-cooldown")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.conf.set("hls.catalog", "hls_test")

        import builtins
        builtins.spark = cls.spark

        if "silver_realtime" in sys.modules:
            cls.silver_realtime = importlib.reload(sys.modules["silver_realtime"])
        else:
            cls.silver_realtime = importlib.import_module("silver_realtime")

        # Timestamps for a 15-minute tumbling window starting at 10:00:00
        cls.t0 = datetime(2026, 11, 13, 10, 0, 0)
        cls.t0_plus_2 = datetime(2026, 11, 13, 10, 2, 0)
        cls.t0_plus_5 = datetime(2026, 11, 13, 10, 5, 0)
        cls.t0_plus_3 = datetime(2026, 11, 13, 10, 3, 0)
        cls.t0_plus_20 = datetime(2026, 11, 13, 10, 20, 0)

        # Telemetry dataset:
        # - dev-1 at t0: SpO2 91.0 (WARNING)
        # - dev-1 at t0+2: SpO2 84.0 (CRITICAL, first CRITICAL in window)
        # - dev-1 at t0+5: SpO2 83.0 (CRITICAL, second CRITICAL in window)
        # - dev-2 at t0+3: SpO2 84.0 (CRITICAL, dev-2 first in window)
        # - dev-1 at t0+20: SpO2 84.0 (CRITICAL, next window [10:15, 10:30))
        telemetry_rows = [
            ("dev-1", cls.t0, 91.0, 72.0, 2.5),
            ("dev-1", cls.t0_plus_2, 84.0, 75.0, 2.1),
            ("dev-1", cls.t0_plus_5, 83.0, 78.0, 2.0),
            ("dev-2", cls.t0_plus_3, 84.0, 80.0, 2.2),
            ("dev-1", cls.t0_plus_20, 84.0, 81.0, 1.9),
        ]
        cls.telemetry_df = cls.spark.createDataFrame(
            telemetry_rows,
            ["device_id", "observed_at", "spo2", "pulse_rate", "perfusion_index"],
        )

        # Devices lookup dataframe
        device_rows = [
            ("dev-1", "Patient/p1"),
            ("dev-2", "Patient/p2"),
        ]
        cls.devices_df = cls.spark.createDataFrame(
            device_rows,
            ["device_id", "patient_reference"],
        )

        # Raw device_association table payload for materialized view test
        assoc_raw_rows = [
            ("""{"code":{"coding":[{"code":"device-assoc"}]},"subject":{"reference":"Patient/p1"},"extension":[{"valueReference":{"reference":"Device/dev-1"}}]}""",),
            ("""{"code":{"coding":[{"code":"device-assoc"}]},"subject":{"reference":"Patient/p2"},"extension":[{"valueReference":{"reference":"Device/dev-2"}}]}""",),
        ]
        cls.assoc_raw_df = cls.spark.createDataFrame(assoc_raw_rows, ["resource_json"])

    @classmethod
    def tearDownClass(cls):
        import builtins
        if hasattr(builtins, "spark"):
            delattr(builtins, "spark")
        cls.spark.stop()

    def _run_pipeline(self, telemetry_df=None, devices_df=None):
        t_df = telemetry_df if telemetry_df is not None else self.telemetry_df
        d_df = devices_df if devices_df is not None else self.devices_df
        return self.silver_realtime.compute_clinical_alert_candidates(t_df, d_df)

    def test_missing_hls_catalog_fails_loudly(self):
        """Test that importing silver_realtime fails loudly if hls.catalog is not configured."""
        orig_catalog = self.spark.conf.get("hls.catalog")
        try:
            self.spark.conf.unset("hls.catalog")
            with self.assertRaises(Exception) as ctx:
                importlib.reload(self.silver_realtime)
            err_msg = str(ctx.exception)
            self.assertTrue(
                "hls.catalog" in err_msg or "SQL_CONF_NOT_FOUND" in err_msg,
                f"Expected hls.catalog configuration error, got: {err_msg}",
            )
        finally:
            self.spark.conf.set("hls.catalog", orig_catalog)
            importlib.reload(self.silver_realtime)

    def test_alert_tier_escalation_not_suppressed_by_prior_warning(self):
        """Test that a CRITICAL alert is not suppressed by an earlier WARNING in the same window."""
        result_df = self._run_pipeline()
        rows = {(r.device_id, r.observed_at): r for r in result_df.collect()}

        # Row at t0 is WARNING and must not be suppressed
        r_t0 = rows[("dev-1", self.t0)]
        self.assertEqual(r_t0.alert_tier, "WARNING")
        self.assertFalse(r_t0.suppressed_by_cooldown, "First WARNING in window must not be suppressed")

        # Row at t0+2 is CRITICAL escalation and must not be suppressed
        r_t0_plus_2 = rows[("dev-1", self.t0_plus_2)]
        self.assertEqual(r_t0_plus_2.alert_tier, "CRITICAL")
        self.assertFalse(
            r_t0_plus_2.suppressed_by_cooldown,
            "First CRITICAL alert must not be suppressed by earlier WARNING in the same window",
        )

        # Row at t0+5 is second CRITICAL in same window and must be suppressed
        r_t0_plus_5 = rows[("dev-1", self.t0_plus_5)]
        self.assertEqual(r_t0_plus_5.alert_tier, "CRITICAL")
        self.assertTrue(
            r_t0_plus_5.suppressed_by_cooldown,
            "Second CRITICAL alert in same window must be suppressed by cooldown",
        )

    def test_device_independence_within_same_window(self):
        """Test that cooldown for one device does not suppress alerts for another device."""
        result_df = self._run_pipeline()
        rows = {(r.device_id, r.observed_at): r for r in result_df.collect()}

        r_dev2 = rows[("dev-2", self.t0_plus_3)]
        self.assertEqual(r_dev2.alert_tier, "CRITICAL")
        self.assertFalse(
            r_dev2.suppressed_by_cooldown,
            "Alert on dev-2 must not be suppressed by dev-1 alerts in the same window",
        )

    def test_subsequent_window_not_suppressed(self):
        """Test that an alert in the next tumbling window is not suppressed."""
        result_df = self._run_pipeline()
        rows = {(r.device_id, r.observed_at): r for r in result_df.collect()}

        r_next_win = rows[("dev-1", self.t0_plus_20)]
        self.assertEqual(r_next_win.alert_tier, "CRITICAL")
        self.assertFalse(
            r_next_win.suppressed_by_cooldown,
            "Alert in the next 15-minute tumbling window must not be suppressed",
        )

    def test_materialized_view_clinical_alert_candidates(self):
        """Test that the production materialized view function returns the expected schema and alert states."""
        def mock_table(reader_self, name):
            if "telemetry" in name:
                return self.telemetry_df
            elif "device_association" in name:
                return self.assoc_raw_df
            raise ValueError(f"Unexpected table: {name}")

        with patch.object(DataFrameReader, "table", mock_table):
            result_df = self.silver_realtime.clinical_alert_candidates()
            expected_cols = [
                "device_id",
                "patient_reference",
                "observed_at",
                "spo2",
                "pulse_rate",
                "perfusion_index",
                "alert_tier",
                "suppressed_by_cooldown",
            ]
            self.assertEqual(result_df.columns, expected_cols)
            rows = {(r.device_id, r.observed_at): r for r in result_df.collect()}
            self.assertEqual(rows[("dev-1", self.t0)].patient_reference, "Patient/p1")
            self.assertEqual(rows[("dev-2", self.t0_plus_3)].patient_reference, "Patient/p2")
            self.assertFalse(
                rows[("dev-1", self.t0_plus_2)].suppressed_by_cooldown,
                "Materialized view must not suppress second-tier escalation in same window",
            )


if __name__ == "__main__":
    unittest.main()

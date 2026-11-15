from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

PHASE5_DIR = Path(__file__).resolve().parents[1]


def load_materialize_module(script_path: Path | None = None):
    """Load materialize_claims_quality.py as a module under test."""
    target_path = script_path or (PHASE5_DIR / "materialize_claims_quality.py")
    module_name = "materialize_claims_quality_under_test"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, target_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load {target_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class MaterializeDimPatientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_materialize_module()
        self.mod.F = MagicMock()
        self.addCleanup(sys.modules.pop, "materialize_claims_quality_under_test", None)

    def test_missing_table_is_skipped_and_listed(self) -> None:
        """Case (a): A missing optional table is skipped and listed in output, and dim_patient is built from other tables."""
        mock_spark = MagicMock()

        class FakeAnalysisException(Exception):
            def getErrorClass(self):
                return "TABLE_OR_VIEW_NOT_FOUND"

        mock_care_gaps = MagicMock()
        mock_care_gaps.columns = ["patient_id"]
        mock_care_gaps.select.return_value.filter.return_value.distinct.return_value.collect.return_value = [
            ("patient_1",),
            ("patient_2",),
        ]

        def fake_table(table_name):
            if "agg_medication_adherence" in table_name:
                raise FakeAnalysisException("Table not found: agg_medication_adherence")
            if "care_gaps" in table_name:
                return mock_care_gaps
            return MagicMock(columns=[])

        mock_spark.read.format.return_value.table.side_effect = fake_table

        mock_df = MagicMock()
        mock_spark.createDataFrame.return_value = mock_df
        mock_df.withColumn.return_value = mock_df

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rows = self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["agg_medication_adherence", "care_gaps"],
            )

        output = stdout.getvalue()
        self.assertIn("agg_medication_adherence", output)
        self.assertIn("Skipping missing table", output)
        self.assertIn("Skipped missing patient source tables: agg_medication_adherence", output)
        self.assertEqual(rows, [("patient_1",), ("patient_2",)])
        mock_df.write.format.return_value.mode.return_value.option.return_value.saveAsTable.assert_called_once_with(
            "gold.dim_patient"
        )

    def test_read_error_on_existing_table_fails_and_names_table(self) -> None:
        """Case (b): A read error on an existing table fails the run and names the table."""
        mock_spark = MagicMock()

        mock_spark.read.format.return_value.table.side_effect = RuntimeError(
            "Simulated I/O disk failure reading delta log"
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["agg_quality_measures"],
            )

        self.assertIn("agg_quality_measures", str(ctx.exception))
        self.assertIn("Failed to read patient source table", str(ctx.exception))

    def test_count_error_fails_the_run(self) -> None:
        """Case (c): A count error fails the run and names the table."""
        mock_spark = MagicMock()

        mock_df = MagicMock()
        mock_df.columns = ["patient_id"]
        # Empty rows collected so patient_rows remains empty
        mock_df.select.return_value.filter.return_value.distinct.return_value.collect.return_value = []
        mock_df.count.side_effect = RuntimeError("Simulated count failure")

        mock_spark.read.format.return_value.table.return_value = mock_df

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["fact_claim"],
            )

        self.assertIn("fact_claim", str(ctx.exception))
        self.assertIn("Failed to count rows", str(ctx.exception))

    def test_missing_table_error_class_is_skipped(self) -> None:
        """Spark AnalysisException with TABLE_OR_VIEW_NOT_FOUND error class is skipped for optional table."""
        mock_spark = MagicMock()

        class FakeAnalysisException(Exception):
            def getErrorClass(self):
                return "TABLE_OR_VIEW_NOT_FOUND"

        mock_care_gaps = MagicMock()
        mock_care_gaps.columns = ["patient_id"]
        mock_care_gaps.select.return_value.filter.return_value.distinct.return_value.collect.return_value = [
            ("patient_1",),
        ]

        def fake_table(table_name):
            if "agg_medication_adherence" in table_name:
                raise FakeAnalysisException("Table not found: agg_medication_adherence")
            if "care_gaps" in table_name:
                return mock_care_gaps
            return MagicMock(columns=[])

        mock_spark.read.format.return_value.table.side_effect = fake_table

        mock_df = MagicMock()
        mock_spark.createDataFrame.return_value = mock_df
        mock_df.withColumn.return_value = mock_df

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rows = self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["agg_medication_adherence", "care_gaps"],
            )

        output = stdout.getvalue()
        self.assertIn("agg_medication_adherence", output)
        self.assertIn("Skipping missing table", output)
        self.assertIn("Skipped missing patient source tables: agg_medication_adherence", output)
        self.assertEqual(rows, [("patient_1",)])

    def test_read_non_missing_error_fails_and_no_table_written(self) -> None:
        """Read non-missing error raises RuntimeError naming table and writes no table."""
        mock_spark = MagicMock()

        class FakePermissionException(Exception):
            def getErrorClass(self):
                return "INSUFFICIENT_PERMISSIONS"

        mock_spark.read.format.return_value.table.side_effect = FakePermissionException(
            "User does not have permission on table"
        )
        mock_df = MagicMock()
        mock_df.withColumn.return_value = mock_df
        mock_spark.createDataFrame.return_value = mock_df

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["agg_quality_measures"],
            )

        self.assertIn("agg_quality_measures", str(ctx.exception))
        mock_df.write.format.return_value.mode.return_value.option.return_value.saveAsTable.assert_not_called()

    def test_missing_table_path_not_found_is_skipped(self) -> None:
        """Spark AnalysisException with PATH_NOT_FOUND (OneLake read route) is skipped for optional table."""
        mock_spark = MagicMock()

        class FakePathNotFoundException(Exception):
            def getErrorClass(self):
                return "PATH_NOT_FOUND"

        mock_care_gaps = MagicMock()
        mock_care_gaps.columns = ["patient_id"]
        mock_care_gaps.select.return_value.filter.return_value.distinct.return_value.collect.return_value = [
            ("patient_1",),
        ]

        def fake_table(table_name):
            if "agg_medication_adherence" in table_name:
                raise FakePathNotFoundException(
                    "[PATH_NOT_FOUND] Path does not exist: abfss://.../agg_medication_adherence"
                )
            if "care_gaps" in table_name:
                return mock_care_gaps
            return MagicMock(columns=[])

        mock_spark.read.format.return_value.table.side_effect = fake_table

        mock_df = MagicMock()
        mock_spark.createDataFrame.return_value = mock_df
        mock_df.withColumn.return_value = mock_df

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rows = self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["agg_medication_adherence", "care_gaps"],
            )

        output = stdout.getvalue()
        self.assertIn("agg_medication_adherence", output)
        self.assertIn("Skipping missing table", output)
        self.assertIn("Skipped missing patient source tables: agg_medication_adherence", output)
        self.assertEqual(rows, [("patient_1",)])

    def test_invalid_delta_folder_without_delta_log_fails(self) -> None:
        """DELTA_TABLE_NOT_FOUND (existing directory lacking _delta_log) fails and is not skipped."""
        mock_spark = MagicMock()

        class FakeDeltaTableNotFoundException(Exception):
            def getErrorClass(self):
                return "DELTA_TABLE_NOT_FOUND"

        mock_spark.read.format.return_value.table.side_effect = FakeDeltaTableNotFoundException(
            "Delta table does not exist"
        )
        mock_df = MagicMock()
        mock_spark.createDataFrame.return_value = mock_df

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["empty_folder"],
            )

        self.assertIn("empty_folder", str(ctx.exception))
        self.assertIn("Failed to read patient source table", str(ctx.exception))
        mock_df.write.format.return_value.mode.return_value.option.return_value.saveAsTable.assert_not_called()

    def test_action_time_lost_data_file_fails(self) -> None:
        """Action-time failure (e.g. deleted Parquet data file) fails and names the table."""
        mock_spark = MagicMock()

        mock_df = MagicMock()
        mock_df.columns = ["patient_id"]
        mock_df.select.return_value.filter.return_value.distinct.return_value.collect.side_effect = (
            RuntimeError("java.io.FileNotFoundException: lost parquet file")
        )
        mock_spark.read.format.return_value.table.return_value = mock_df

        mock_out = MagicMock()
        mock_spark.createDataFrame.return_value = mock_out

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["lost_file_table"],
            )

        self.assertIn("lost_file_table", str(ctx.exception))
        self.assertIn("Failed to read patient source table", str(ctx.exception))
        mock_out.write.format.return_value.mode.return_value.option.return_value.saveAsTable.assert_not_called()

    def test_missing_required_source_fails_and_preserves_dim_patient(self) -> None:
        """A missing required table fails and preserves existing dim_patient."""
        mock_spark = MagicMock()

        class FakeAnalysisException(Exception):
            def getErrorClass(self):
                return "TABLE_OR_VIEW_NOT_FOUND"

        mock_care_gaps = MagicMock()
        mock_care_gaps.columns = ["patient_id"]
        mock_care_gaps.select.return_value.filter.return_value.distinct.return_value.collect.return_value = [
            ("patient_1",),
        ]

        def fake_table(table_name):
            if "agg_quality_measures" in table_name:
                raise FakeAnalysisException("Table not found: agg_quality_measures")
            if "care_gaps" in table_name:
                return mock_care_gaps
            return MagicMock(columns=[])

        mock_spark.read.format.return_value.table.side_effect = fake_table
        mock_df = MagicMock()
        mock_spark.createDataFrame.return_value = mock_df

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["agg_quality_measures", "care_gaps"],
            )

        self.assertIn("agg_quality_measures", str(ctx.exception))
        self.assertIn("Required patient source table", str(ctx.exception))
        mock_df.write.format.return_value.mode.return_value.option.return_value.saveAsTable.assert_not_called()

    def test_all_patient_sources_unavailable_fails_and_preserves_dim_patient(self) -> None:
        """When all patient sources are unavailable, fail before writing dim_patient."""
        mock_spark = MagicMock()

        class FakePathNotFoundException(Exception):
            def getErrorClass(self):
                return "PATH_NOT_FOUND"

        mock_spark.read.format.return_value.table.side_effect = FakePathNotFoundException(
            "[PATH_NOT_FOUND] Path does not exist: abfss://.../agg_medication_adherence"
        )
        mock_df = MagicMock()
        mock_spark.createDataFrame.return_value = mock_df

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["agg_medication_adherence"],
            )

        self.assertIn("All patient source tables are unavailable", str(ctx.exception))
        mock_df.write.format.return_value.mode.return_value.option.return_value.saveAsTable.assert_not_called()

    def test_patient_source_lacking_patient_id_and_patient_ref_fails_and_preserves_dim_patient(self) -> None:
        """R-2: A present patient source lacking both patient_id and patient_ref fails and preserves dim_patient."""
        mock_spark = MagicMock()

        mock_bad_source = MagicMock()
        mock_bad_source.columns = ["encounter_id", "some_score"]

        mock_care_gaps = MagicMock()
        mock_care_gaps.columns = ["patient_id"]
        mock_care_gaps.select.return_value.filter.return_value.distinct.return_value.collect.return_value = [
            ("patient_1",),
        ]

        def fake_table(table_name):
            if "agg_risk_scores" in table_name:
                return mock_bad_source
            if "care_gaps" in table_name:
                return mock_care_gaps
            return MagicMock(columns=[])

        mock_spark.read.format.return_value.table.side_effect = fake_table
        mock_df = MagicMock()
        mock_spark.createDataFrame.return_value = mock_df

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["agg_risk_scores", "care_gaps"],
            )

        self.assertIn("agg_risk_scores", str(ctx.exception))
        self.assertIn("has no patient_id or patient_ref column", str(ctx.exception))
        mock_df.write.format.return_value.mode.return_value.option.return_value.saveAsTable.assert_not_called()

    def test_all_present_sources_empty_fails_and_preserves_dim_patient(self) -> None:
        """Empty patient sources fail before the write, so the previous dim_patient stays."""
        mock_spark = MagicMock()

        def empty_source():
            source = MagicMock()
            source.columns = ["patient_id"]
            source.select.return_value.filter.return_value.distinct.return_value.collect.return_value = []
            source.count.return_value = 0
            return source

        sources = {"agg_quality_measures": empty_source(), "care_gaps": empty_source()}
        mock_spark.read.format.return_value.table.side_effect = lambda name: sources[name.split(".")[-1]]

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.materialize_dim_patient(
                mock_spark,
                "gold",
                patient_source_tables=["agg_quality_measures", "care_gaps"],
            )

        self.assertIn("every patient-level source table is empty", str(ctx.exception))
        mock_spark.createDataFrame.assert_not_called()


class CountOrCreateGoldTableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_materialize_module()
        self.mod.F = MagicMock()
        self.addCleanup(sys.modules.pop, "materialize_claims_quality_under_test", None)

    def test_existing_table_returns_count_without_overwriting(self) -> None:
        mock_spark = MagicMock()
        mock_df = MagicMock()
        mock_df.count.return_value = 150
        mock_spark.read.format.return_value.table.return_value = mock_df

        count, created = self.mod.count_or_create_gold_table(mock_spark, "gold", "care_gaps")
        self.assertEqual(count, 150)
        self.assertFalse(created)
        mock_spark.read.format.assert_called_with("delta")
        mock_spark.read.format.return_value.table.assert_called_once_with("gold.care_gaps")
        mock_spark.createDataFrame.assert_not_called()

    def test_read_failure_preserves_target_and_names_table(self) -> None:
        """Permission or corruption error on opening table fails and does not create an empty table."""
        mock_spark = MagicMock()
        mock_spark.read.format.return_value.table.side_effect = RuntimeError(
            "AccessDenied: Insufficient permissions to read delta table"
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.count_or_create_gold_table(mock_spark, "gold", "agg_medication_adherence")

        self.assertIn("agg_medication_adherence", str(ctx.exception))
        self.assertIn("Failed to read gold table", str(ctx.exception))
        mock_spark.createDataFrame.assert_not_called()

    def test_count_failure_preserves_target_and_names_table(self) -> None:
        """Action-time / count failure preserves target and raises RuntimeError naming the table."""
        mock_spark = MagicMock()
        mock_df = MagicMock()
        mock_df.count.side_effect = RuntimeError("java.io.FileNotFoundException: corrupted parquet part")
        mock_spark.read.format.return_value.table.return_value = mock_df

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.count_or_create_gold_table(mock_spark, "gold", "agg_medication_adherence")

        self.assertIn("agg_medication_adherence", str(ctx.exception))
        self.assertIn("Failed to count rows in gold table", str(ctx.exception))
        mock_spark.createDataFrame.assert_not_called()

    def test_missing_required_table_fails_and_not_created_empty(self) -> None:
        """A missing required table fails and is not created as an empty table."""
        mock_spark = MagicMock()

        class FakeTableNotFoundException(Exception):
            def getErrorClass(self):
                return "TABLE_OR_VIEW_NOT_FOUND"

        mock_spark.read.format.return_value.table.side_effect = FakeTableNotFoundException(
            "Table not found: care_gaps"
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.count_or_create_gold_table(mock_spark, "gold", "care_gaps")

        self.assertIn("care_gaps", str(ctx.exception))
        self.assertIn("Required gold table 'care_gaps' is missing and cannot be created empty", str(ctx.exception))
        mock_spark.createDataFrame.assert_not_called()

    def test_missing_optional_table_creates_schema_correct_empty_table_with_error_mode(self) -> None:
        """A genuine missing optional table creates a schema-correct empty table in mode('error')."""
        mock_spark = MagicMock()

        class FakePathNotFoundException(Exception):
            def getErrorClass(self):
                return "PATH_NOT_FOUND"

        mock_spark.read.format.return_value.table.side_effect = FakePathNotFoundException(
            "[PATH_NOT_FOUND] abfss://.../agg_medication_adherence"
        )

        mock_empty_df = MagicMock()
        mock_spark.createDataFrame.return_value = mock_empty_df

        count, created = self.mod.count_or_create_gold_table(mock_spark, "gold", "agg_medication_adherence")
        self.assertEqual(count, 0)
        self.assertTrue(created)

        # Verify lazy schema construction with expected columns
        mock_spark.createDataFrame.assert_called_once()
        args, _ = mock_spark.createDataFrame.call_args
        self.assertEqual(args[0], [])
        schema = args[1]
        expected_cols = [col_name for col_name, _ in self.mod.EXPECTED_TABLE_SCHEMAS["agg_medication_adherence"]]
        actual_cols = [f.name for f in schema.fields]
        self.assertEqual(actual_cols, expected_cols)

        # Verify non-overwriting semantics: mode("error")
        mock_empty_df.write.format.assert_called_with("delta")
        mock_empty_df.write.format.return_value.mode.assert_called_with("error")
        mock_empty_df.write.format.return_value.mode.return_value.saveAsTable.assert_called_once_with(
            "gold.agg_medication_adherence"
        )

    def test_placeholder_create_failure_names_create_and_table(self) -> None:
        """Only an attempted create is reported as a create failure, naming the table."""
        mock_spark = MagicMock()

        class FakePathNotFoundException(Exception):
            def getErrorClass(self):
                return "PATH_NOT_FOUND"

        mock_spark.read.format.return_value.table.side_effect = FakePathNotFoundException(
            "[PATH_NOT_FOUND] abfss://.../agg_condition_pmpm"
        )
        mock_spark.createDataFrame.return_value.write.format.return_value.mode.return_value.saveAsTable.side_effect = (
            RuntimeError("[DELTA_TABLE_ALREADY_EXISTS] concurrent writer")
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.count_or_create_gold_table(mock_spark, "gold", "agg_condition_pmpm")

        self.assertIn(
            "Failed to create empty placeholder for optional gold table 'agg_condition_pmpm'", str(ctx.exception)
        )
        self.assertIn("DELTA_TABLE_ALREADY_EXISTS", str(ctx.exception))


class FakeMissing(Exception):
    def getErrorClass(self):
        return "PATH_NOT_FOUND"


class GoldStepErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = load_materialize_module()
        self.addCleanup(sys.modules.pop, "materialize_claims_quality_under_test", None)

    def test_read_step_source_missing_table_is_typed(self) -> None:
        def read(_):
            raise FakeMissing("[PATH_NOT_FOUND] silver/MedicationRequest")

        with self.assertRaises(self.mod.MissingSourceTableError) as ctx:
            self.mod.read_step_source(read, "silver.MedicationRequest")
        self.assertEqual(ctx.exception.table_ident, "silver.MedicationRequest")

    def test_read_step_source_other_failure_is_not_missing(self) -> None:
        def read(_):
            raise RuntimeError("AccessDenied")

        with self.assertRaises(RuntimeError) as ctx:
            self.mod.read_step_source(read, "silver.Coverage")
        self.assertNotIsInstance(ctx.exception, self.mod.MissingSourceTableError)
        self.assertIn("Failed to read source table 'silver.Coverage'", str(ctx.exception))

    def test_missing_source_for_optional_step_is_skipped_and_named(self) -> None:
        error = self.mod.MissingSourceTableError("silver.MedicationRequest", FakeMissing("gone"))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.mod.handle_gold_step_error("Step 6: Medication Adherence", ["agg_medication_adherence"], error)
        self.assertIn("Step 6: Medication Adherence skipped", output.getvalue())
        self.assertIn("agg_medication_adherence", output.getvalue())

    def test_missing_source_for_step_with_required_output_fails(self) -> None:
        error = self.mod.MissingSourceTableError("silver.Condition", FakeMissing("gone"))
        with self.assertRaises(RuntimeError) as ctx:
            self.mod.handle_gold_step_error("Step 9: HCC", ["dim_hcc", "fact_patient_hcc"], error)
        self.assertIn("required Gold tables not refreshed: dim_hcc", str(ctx.exception))
        self.assertNotIn("fact_patient_hcc", str(ctx.exception).split("not refreshed:")[1])

    def test_write_failure_for_optional_step_fails_and_names_tables(self) -> None:
        """With the source present, a failed write of an optional table still fails the run."""
        error = RuntimeError("Failed to write gold table 'agg_medication_adherence': DELTA_FAILED_TO_MERGE_FIELDS")
        with self.assertRaises(RuntimeError) as ctx:
            self.mod.handle_gold_step_error("Step 6: Medication Adherence", ["agg_medication_adherence"], error)
        self.assertIn("Step 6: Medication Adherence failed", str(ctx.exception))
        self.assertIn("agg_medication_adherence", str(ctx.exception))
        self.assertIs(ctx.exception.__cause__, error)

    def test_overwrite_failure_names_table(self) -> None:
        df = MagicMock()
        df.write.format.return_value.mode.return_value.option.return_value.saveAsTable.side_effect = (
            RuntimeError("commit conflict")
        )
        with self.assertRaises(RuntimeError) as ctx:
            self.mod.overwrite_gold_table(df, "gold", "care_gaps")
        self.assertIn("Failed to write gold table 'care_gaps': commit conflict", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

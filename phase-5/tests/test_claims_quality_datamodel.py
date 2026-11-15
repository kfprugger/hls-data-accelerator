"""Tests for Phase 5 Population Health & Quality data model, dimensions, and relationships."""
from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

PHASE5_DIR = Path(__file__).resolve().parents[1]
TMDL_DIR = PHASE5_DIR / "cms-quality-report/Population Health & Quality Dashboard.SemanticModel/definition"


def _load_materialize_module():
    module_name = "materialize_claims_quality_under_test"
    spec = importlib.util.spec_from_file_location(module_name, PHASE5_DIR / "materialize_claims_quality.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_tmdl_relationships(tmdl_path: Path) -> list[dict[str, str]]:
    rels = []
    current: dict[str, str] = {}
    for line in tmdl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("relationship "):
            if current:
                rels.append(current)
            current = {"name": line.split(maxsplit=1)[1]}
        elif line.startswith("fromColumn:"):
            current["fromColumn"] = line.split(":", 1)[1].strip()
        elif line.startswith("toColumn:"):
            current["toColumn"] = line.split(":", 1)[1].strip()
    if current:
        rels.append(current)
    return rels


class ClaimsQualityDataModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mcq = _load_materialize_module()

    def test_dim_hcc_unique_and_count_equals_distinct_codes(self):
        """Rayfi-F2: dim_hcc must be keyed by hcc_code with exactly one row per code."""
        mappings = self.mcq.HCC_MAPPINGS
        distinct_codes_in_mappings = {m[2] for m in mappings}
        self.assertEqual(len(distinct_codes_in_mappings), 19)

        # Baseline logic resulted in 23 rows for 19 codes because of alternate names
        baseline_rows = list({(m[2], m[3], m[4], m[5]) for m in mappings})
        self.assertEqual(len(baseline_rows), 23, "Baseline produced 23 rows for 19 keys")

        # Repaired row builder must produce exactly 19 unique rows
        hcc_rows = self.mcq.build_dim_hcc_rows()
        self.assertEqual(len(hcc_rows), 19)

        # Every code in dim_hcc must be unique and match the distinct codes in mappings
        codes = [r[0] for r in hcc_rows]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(set(codes), distinct_codes_in_mappings)

        # Canonical names must be assigned
        for hcc_code, hcc_name, coef, group in hcc_rows:
            self.assertEqual(hcc_name, self.mcq.HCC_CANONICAL_NAMES[hcc_code])
            self.assertIsInstance(coef, float)
            self.assertTrue(group)

    def test_dim_patient_unique_and_covers_all_sources(self):
        """Rayfi-F1: dim_patient row-building logic must deduplicate and cover all patient IDs."""
        agg_quality_measures = [{"patient_id": "pt-01"}, {"patient_id": "pt-02"}, {"patient_id": "pt-01"}]
        fact_claim = [{"patient_id": "pt-02"}, {"patient_id": "pt-03"}]
        care_gaps = [{"patient_id": "pt-04"}]
        agg_medication_adherence = [{"patient_id": "pt-01"}, {"patient_id": "pt-03"}]
        agg_risk_scores = [{"patient_id": "pt-02"}]
        revenue_opportunity = [{"patient_id": "pt-05"}]
        readmission_risk_scores = [{"patient_id": "pt-04"}]
        agg_high_cost_claimants = [{"patient_id": "pt-05"}]
        fact_patient_hcc = [{"patient_id": "pt-03"}]
        silver_patient = [("pt-06",), ("pt-01",)]

        all_input_pids = {"pt-01", "pt-02", "pt-03", "pt-04", "pt-05", "pt-06"}

        patient_rows = self.mcq.build_dim_patient_rows(
            agg_quality_measures,
            fact_claim,
            care_gaps,
            agg_medication_adherence,
            agg_risk_scores,
            revenue_opportunity,
            readmission_risk_scores,
            agg_high_cost_claimants,
            fact_patient_hcc,
            silver_patient,
            None,  # Handles empty/missing sources safely
            [],
        )

        extracted_pids = [r[0] for r in patient_rows]
        # Must be strictly unique
        self.assertEqual(len(extracted_pids), len(set(extracted_pids)))
        # Must cover all input patient IDs
        self.assertEqual(set(extracted_pids), all_input_pids)
        # Must be sorted
        self.assertEqual(extracted_pids, sorted(all_input_pids))

    def test_tmdl_relationships_one_side_is_unique_key(self):
        """Rayfi-F1: Every relationship's one side (toColumn) must be a verified unique-key table."""
        relationships_file = TMDL_DIR / "relationships.tmdl"
        self.assertTrue(relationships_file.exists(), f"Missing {relationships_file}")

        rels = _parse_tmdl_relationships(relationships_file)
        self.assertGreaterEqual(len(rels), 8, "Expected at least 8 relationships in PHQ model")

        # Verified unique keys by construction
        valid_one_sides = {
            "dim_patient.patient_id",
            "dim_diagnosis.icd_code",
            "dim_hcc.hcc_code",
            "agg_risk_scores.patient_id",
        }

        for rel in rels:
            to_col = rel["toColumn"]
            self.assertIn(
                to_col,
                valid_one_sides,
                f"Relationship {rel['name']} targets '{to_col}' which is NOT a unique-key column",
            )
            # Crucially: agg_quality_measures.patient_id must NOT be the one side
            self.assertNotEqual(
                to_col,
                "agg_quality_measures.patient_id",
                f"Relationship {rel['name']} targets non-unique agg_quality_measures.patient_id",
            )

    def test_dim_patient_tmdl_and_registration(self):
        """dim_patient table TMDL exists, Direct Lake partition configured, and referenced in model."""
        dim_patient_file = TMDL_DIR / "tables/dim_patient.tmdl"
        self.assertTrue(dim_patient_file.exists(), f"Missing {dim_patient_file}")

        tmdl_content = dim_patient_file.read_text(encoding="utf-8")
        self.assertIn("table dim_patient", tmdl_content)
        self.assertIn("mode: directLake", tmdl_content)
        self.assertIn("entityName: dim_patient", tmdl_content)
        self.assertIn("column patient_id", tmdl_content)

        model_file = TMDL_DIR / "model.tmdl"
        model_content = model_file.read_text(encoding="utf-8")
        self.assertIn("ref table dim_patient", model_content)
        self.assertIn('"dim_patient"', model_content)

        # Check Python materializer schema registration
        self.assertIn("dim_patient", self.mcq.TABLES)
        self.assertNotIn("dim_patient", self.mcq.ALLOW_EMPTY_TABLES)
        self.assertIn("dim_patient", self.mcq.EXPECTED_TABLE_SCHEMAS)


    def _build_pipeline_mocks(self, saved_tables, missing_tables=(), failing_writes=()):
        """Mock Spark/Fabric for run_pipeline.

        Gold and Silver reads go through the DataFrameReader.table patch that
        run_pipeline installs, so every read ends in the OneLake ``load`` path.
        ``missing_tables`` holds bare table names whose path does not exist (the load
        raises PATH_NOT_FOUND) until a write creates them. ``failing_writes`` holds
        bare table names whose save raises.
        """
        missing_tables = set(missing_tables)

        class FakePathNotFound(Exception):
            def getErrorClass(self):
                return "PATH_NOT_FOUND"

        class ColumnMock:
            def __getattr__(self, name): return lambda *a, **k: ColumnMock()
            def __ge__(self, o): return ColumnMock()
            def __le__(self, o): return ColumnMock()
            def __gt__(self, o): return ColumnMock()
            def __lt__(self, o): return ColumnMock()
            def __eq__(self, o): return ColumnMock()
            def __ne__(self, o): return ColumnMock()
            def __and__(self, o): return ColumnMock()
            def __rand__(self, o): return ColumnMock()
            def __or__(self, o): return ColumnMock()
            def __ror__(self, o): return ColumnMock()
            def __invert__(self): return ColumnMock()
            def __add__(self, o): return ColumnMock()
            def __radd__(self, o): return ColumnMock()
            def __sub__(self, o): return ColumnMock()
            def __rsub__(self, o): return ColumnMock()
            def __mul__(self, o): return ColumnMock()
            def __rmul__(self, o): return ColumnMock()
            def __truediv__(self, o): return ColumnMock()
            def __rtruediv__(self, o): return ColumnMock()
            def __getitem__(self, item): return ColumnMock()

        class RowMock(dict):
            def __init__(self, d=None, **kwargs):
                super().__init__(d or {})
                self.update(kwargs)
            def __getattr__(self, key):
                return self.get(key, 0.5)
            def __getitem__(self, key):
                if isinstance(key, int):
                    return 0.5
                return super().get(key, 0.5)

        class WriterMock:
            def __init__(self, parent_df):
                self.parent_df = parent_df
                self._mode = None
                self._options = {}
            def format(self, fmt): return self
            def mode(self, m):
                self._mode = m
                return self
            def option(self, k, v):
                self._options[k] = v
                return self
            def saveAsTable(self, table_name):
                bare_name = table_name.split(".")[-1]
                if bare_name in failing_writes:
                    raise RuntimeError(f"Simulated Delta commit failure for {table_name}")
                saved_tables[table_name] = {
                    "mode": self._mode,
                    "options": dict(self._options),
                    "rows": getattr(self.parent_df, "rows", None)
                }
                missing_tables.discard(bare_name)

        class DFMock:
            columns = ["patient_id", "patient_ref", "claim_id", "icd_code"]
            def __init__(self, rows=None):
                if rows is not None and not isinstance(rows, list):
                    self.rows = [RowMock({"readmitted_30d": 1, "patient_id": "pt-01", 0: 0.5})]
                elif rows is not None:
                    self.rows = rows
                else:
                    self.rows = [RowMock({"patient_id": "pt-01", "total_paid": 10.0}), RowMock({"patient_id": "pt-02", "total_paid": 20.0})]
                self.write = WriterMock(self)
            def select(self, *a, **k): return self
            def filter(self, *a, **k): return self
            def where(self, *a, **k): return self
            def withColumn(self, *a, **k): return self
            def join(self, *a, **k): return self
            def crossJoin(self, *a, **k): return self
            def groupBy(self, *a, **k): return self
            def agg(self, *a, **k): return self
            def distinct(self): return self
            def dropDuplicates(self, *a, **k): return self
            def drop(self, *a, **k): return self
            def fillna(self, *a, **k): return self
            def count(self): return len(self.rows) if self.rows is not None else 5
            def collect(self): return self.rows or []
            def __getitem__(self, item): return ColumnMock()
            def alias(self, *a, **k): return self
            def union(self, *a, **k): return self
            def unionByName(self, *a, **k): return self
            def orderBy(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def approxQuantile(self, *a, **k): return [100.0]

        mock_spark = MagicMock()
        pyspark_sql = MagicMock()
        readwriter = MagicMock()
        pyspark_sql.SparkSession.builder.getOrCreate.return_value = mock_spark

        def load(path, *a, **k):
            if path.rstrip("/").split("/")[-1] in missing_tables:
                raise FakePathNotFound(f"[PATH_NOT_FOUND] Path does not exist: {path}.")
            return DFMock()

        mock_spark.read.format.return_value.load.side_effect = load
        # Route spark.read.format("delta").table(...) through run_pipeline's own patch.
        mock_spark.read.format.return_value.table.side_effect = (
            lambda name: readwriter.DataFrameReader.table(None, name)
        )
        mock_spark.createDataFrame.side_effect = lambda rows, schema=None: DFMock(rows)

        mock_notebookutils = MagicMock()
        mock_notebookutils.fabric.resolve_workspace_id.return_value = "ws-test-123"
        mock_notebookutils.credentials.getToken.return_value = "token-123"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "value": [
                {"displayName": "healthcare1_msft_silver", "id": "silver-id"},
                {"displayName": "healthcare1_reporting_gold", "id": "gold-id"}
            ]
        }

        mock_y = MagicMock()
        mock_y.mean.return_value = 0.1
        mock_y.__len__.return_value = 10

        class MockSeries:
            def __eq__(self, other): return self
            def sum(self): return 2
            def mean(self): return 0.1
            def __len__(self): return 10
            values = mock_y
            def apply(self, fn): return self
            def clip(self, *a, **k): return self
            def __add__(self, o): return self
            def __radd__(self, o): return self
            def __mul__(self, o): return self
            def __rmul__(self, o): return self

        class MockPandasDF(dict):
            def __len__(self): return 12
            def __getitem__(self, item):
                return MockSeries()

        DFMock.toPandas = lambda self: MockPandasDF()

        class SparkFunctions:
            def __getattr__(self, name): return lambda *a, **k: ColumnMock()

        modules_patch = {
            "pyspark": MagicMock(),
            "pyspark.sql": pyspark_sql,
            "pyspark.sql.types": MagicMock(),
            "pyspark.sql.readwriter": readwriter,
            "pyspark.sql.functions": SparkFunctions(),
            "sklearn": MagicMock(),
            "sklearn.linear_model": MagicMock(),
            "sklearn.model_selection": MagicMock(),
            "sklearn.metrics": MagicMock(),
            "numpy": MagicMock(),
            "notebookutils": mock_notebookutils,
        }
        return modules_patch, mock_resp

    def test_run_pipeline_writes_dim_patient(self):
        """R-1: run_pipeline writes dim_patient with overwrite + overwriteSchema from patient-level tables."""
        saved_tables = {}
        modules_patch, mock_resp = self._build_pipeline_mocks(saved_tables)

        with patch.dict(sys.modules, modules_patch), patch("requests.get", return_value=mock_resp):
            mod = _load_materialize_module()
            mod.F = modules_patch["pyspark.sql.functions"]
            with patch.object(mod, "build_dim_patient_rows", wraps=mod.build_dim_patient_rows) as spy_build:
                mod.run_pipeline()
                spy_build.assert_called_once()

        dim_patient_save = saved_tables.get("healthcare1_reporting_gold.dim_patient")
        self.assertIsNotNone(dim_patient_save, "dim_patient was not saved in run_pipeline()")
        self.assertEqual(dim_patient_save["mode"], "overwrite")
        self.assertEqual(dim_patient_save["options"].get("overwriteSchema"), "true")
        self.assertEqual(dim_patient_save["rows"], [("pt-01",), ("pt-02",)])

    def test_run_pipeline_fails_when_fact_tables_have_rows_and_dim_patient_empty(self):
        """R-1: run_pipeline raises RuntimeError when fact tables have rows but dim_patient is empty."""
        saved_tables = {}
        modules_patch, mock_resp = self._build_pipeline_mocks(saved_tables)

        with patch.dict(sys.modules, modules_patch), patch("requests.get", return_value=mock_resp):
            mod = _load_materialize_module()
            mod.F = modules_patch["pyspark.sql.functions"]
            with patch.object(mod, "build_dim_patient_rows", return_value=[]):
                with self.assertRaises(RuntimeError) as ctx:
                    mod.run_pipeline()
                self.assertIn("dim_patient is empty despite non-empty patient-level fact tables", str(ctx.exception))

    def _run_pipeline(self, saved_tables, missing_tables=(), failing_writes=()):
        """Run run_pipeline on the Spark/Fabric mocks."""
        modules_patch, mock_resp = self._build_pipeline_mocks(saved_tables, missing_tables, failing_writes)
        output = io.StringIO()
        with patch.dict(sys.modules, modules_patch), patch("requests.get", return_value=mock_resp), \
                contextlib.redirect_stdout(output):
            mod = _load_materialize_module()
            mod.F = modules_patch["pyspark.sql.functions"]
            try:
                mod.run_pipeline()
            except Exception as error:
                return error, output.getvalue()
        return None, output.getvalue()


    def test_run_pipeline_fails_and_names_table_when_present_source_write_fails(self):
        """A failed write of a step whose sources are present fails the run and names the table."""
        saved_tables = {}
        error, _ = self._run_pipeline(saved_tables, failing_writes={"agg_medication_adherence"})

        self.assertIsInstance(error, RuntimeError)
        self.assertIn("Step 6: Medication Adherence", str(error))
        self.assertIn("agg_medication_adherence", str(error))
        self.assertNotIn("healthcare1_reporting_gold.agg_medication_adherence", saved_tables)
        # The run stopped at Step 6: later steps and dim_patient were not written.
        self.assertNotIn("healthcare1_reporting_gold.star_rating_detail", saved_tables)
        self.assertNotIn("healthcare1_reporting_gold.dim_patient", saved_tables)

    def test_run_pipeline_fails_when_required_step_source_is_missing(self):
        """A missing Silver source for a step with required outputs fails the run and names the step."""
        saved_tables = {}
        error, _ = self._run_pipeline(saved_tables, missing_tables={"ExplanationOfBenefit"})

        self.assertIsInstance(error, RuntimeError)
        self.assertIn("Step 3: fact_claim", str(error))
        self.assertIn("ExplanationOfBenefit", str(error))
        self.assertNotIn("healthcare1_reporting_gold.fact_claim", saved_tables)


if __name__ == "__main__":
    unittest.main()

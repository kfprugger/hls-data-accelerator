"""Unit tests for demo_zero_copy_edit.py CLI tool."""
from __future__ import annotations

import io
import pathlib
import sys
import unittest
from unittest.mock import patch

# Ensure pipeline dir is in sys.path
TESTS_DIR = pathlib.Path(__file__).resolve().parent
PIPELINE_DIR = TESTS_DIR.parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import demo_zero_copy_edit


class TestDemoZeroCopyEdit(unittest.TestCase):
    def setUp(self) -> None:
        self.patient_id = "TCGA-G6-A8L6"
        self.baseline_name = "Marcus Vance"
        self.target_name = "Marcus Vance (Zero-Copy Proof)"

    def test_sql_injection_defense(self) -> None:
        """Verify inputs containing SQL injection vectors are rejected before query dispatch."""
        injection_vectors = [
            "' OR '1'='1",
            "; DROP TABLE dbo.patient; --",
            "TCGA-G6-A8L6' OR '1'='1",
            "TCGA-G6-A8L6; DROP TABLE patient",
            "Marcus Vance' UNION SELECT * FROM secret --",
            "admin'--",
            "/* inline comment */ test",
        ]
        for vector in injection_vectors:
            with self.subTest(vector=vector):
                with self.assertRaises(ValueError):
                    # Should fail patient ID validation or parameter sanitization
                    if demo_zero_copy_edit.PATIENT_ID_RE.match(vector):
                        demo_zero_copy_edit.sanitize_parameter(vector, "test")
                    else:
                        demo_zero_copy_edit.validate_patient_id(vector)

    def test_patient_id_validation_valid(self) -> None:
        """Verify valid TCGA patient IDs pass validation."""
        valid_ids = ["TCGA-G6-A8L6", "TCGA-BP-4963", "TCGA-A2-A0T2", "TCGA-12-3456"]
        for pid in valid_ids:
            with self.subTest(pid=pid):
                self.assertEqual(demo_zero_copy_edit.validate_patient_id(pid), pid)

    def test_patient_id_validation_invalid(self) -> None:
        """Verify invalid patient IDs raise ValueError."""
        invalid_ids = ["INVALID_ID_123", "TCGA-1-1234", "TCGA-ABC-12345", "patient_1", ""]
        for pid in invalid_ids:
            with self.subTest(pid=pid):
                with self.assertRaises(ValueError) as ctx:
                    demo_zero_copy_edit.validate_patient_id(pid)
                self.assertIn("Invalid patient ID format", str(ctx.exception))
                self.assertIn(pid, str(ctx.exception))

    def test_dry_run_execution(self) -> None:
        """Verify dry-run performs read-only inspection without altering tables."""
        stdout_capture = io.StringIO()
        with patch("sys.stdout", stdout_capture):
            code = demo_zero_copy_edit.main(["--dry-run"])
        self.assertEqual(code, 0)
        output = stdout_capture.getvalue()
        self.assertIn("[DRY-RUN] Target: TCGA-G6-A8L6 (Marcus Vance) in clinical_lakehouse.patient", output)
        self.assertIn("Planned update: Marcus Vance (Zero-Copy Proof)", output)
        self.assertIn("Verified: No database or parquet files were altered.", output)

    def test_apply_and_revert_cycle(self) -> None:
        """Verify apply modifies value, reads back immediately, and revert restores it."""
        try:
            # Apply
            stdout_apply = io.StringIO()
            with patch("sys.stdout", stdout_apply):
                code_apply = demo_zero_copy_edit.main(["--apply"])
            self.assertEqual(code_apply, 0)
            out_apply = stdout_apply.getvalue()
            self.assertIn("Applied: Marcus Vance (Zero-Copy Proof)", out_apply)
            self.assertIn("Read back via patient360: Marcus Vance (Zero-Copy Proof)", out_apply)
            self.assertIn("Elapsed:", out_apply)

            # Revert
            stdout_revert = io.StringIO()
            with patch("sys.stdout", stdout_revert):
                code_revert = demo_zero_copy_edit.main(["--revert"])
            self.assertEqual(code_revert, 0)
            out_revert = stdout_revert.getvalue()
            self.assertIn("Reverted: Marcus Vance", out_revert)
            self.assertIn("Read back via patient360: Marcus Vance", out_revert)
            self.assertIn("Elapsed:", out_revert)
        finally:
            # Ensure always reverted
            demo_zero_copy_edit.main(["--revert"])

    def test_idempotent_revert(self) -> None:
        """Verify running revert when already at baseline reports no-op."""
        # Ensure at baseline first
        demo_zero_copy_edit.main(["--revert"])

        stdout_capture = io.StringIO()
        with patch("sys.stdout", stdout_capture):
            code = demo_zero_copy_edit.main(["--revert"])
        self.assertEqual(code, 0)
        output = stdout_capture.getvalue()
        self.assertIn("Record is already at baseline value 'Marcus Vance'. No changes needed.", output)

    def test_idempotent_apply(self) -> None:
        """Verify running apply when already at target value reports no-op."""
        try:
            demo_zero_copy_edit.main(["--apply"])
            stdout_capture = io.StringIO()
            with patch("sys.stdout", stdout_capture):
                code = demo_zero_copy_edit.main(["--apply"])
            self.assertEqual(code, 0)
            output = stdout_capture.getvalue()
            self.assertIn("Record is already at target value 'Marcus Vance (Zero-Copy Proof)'. No changes needed.", output)
            self.assertIn("Read back via patient360: Marcus Vance (Zero-Copy Proof)", output)
        finally:
            demo_zero_copy_edit.main(["--revert"])

    def test_missing_tables_error(self) -> None:
        """Verify clear error message and exit 1 when tables directory is missing."""
        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            with self.assertRaises(SystemExit) as ctx:
                demo_zero_copy_edit.check_local_tables(pathlib.Path("/tmp/nonexistent_path_xyz"))
            self.assertEqual(ctx.exception.code, 1)
        err = stderr_capture.getvalue()
        self.assertIn("No tables found in work/tables/clinical. Run build_local_tables.py first.", err)


if __name__ == "__main__":
    unittest.main()

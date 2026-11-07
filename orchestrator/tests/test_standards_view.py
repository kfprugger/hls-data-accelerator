"""Unit tests for the Rayfin Standards View (FHIR R4 & DICOM to Delta Lake Lineage) verification script."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXEC = "/Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python"
SCRIPT_PATH = ROOT / "rayfin-imaging" / "scripts" / "verify_standards_view.py"


class TestStandardsViewVerification(unittest.TestCase):
    def test_verify_standards_view_dry_run(self):
        """Test that verify_standards_view.py runs successfully in dry-run mode for default patient Marcus Vance."""
        self.assertTrue(SCRIPT_PATH.exists(), f"Script not found at {SCRIPT_PATH}")

        proc = subprocess.run(
            [PYTHON_EXEC, str(SCRIPT_PATH), "--patient-id", "TCGA-G6-A8L6", "--dry-run"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"Script failed with stderr:\n{proc.stderr}")

        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "verified")
        self.assertEqual(data.get("patient_id"), "TCGA-G6-A8L6")

        verified_cols = data.get("verified_columns", [])
        expected_cols = [
            "patient_id",
            "display_name",
            "primary_diagnosis",
            "study_uid",
            "series_uid",
        ]
        for col in expected_cols:
            self.assertIn(col, verified_cols, f"Missing verified column: {col}")

        fhir_mapping = data.get("fhir_mapping", {})
        self.assertEqual(fhir_mapping.get("display_name"), "Marcus Vance")
        self.assertEqual(fhir_mapping.get("primary_diagnosis"), "Clear cell renal cell carcinoma")

        dicom_mapping = data.get("dicom_mapping", {})
        self.assertEqual(dicom_mapping.get("study_uid"), "1.3.6.1.4.1.14519.5.2.1.4872083899")
        self.assertEqual(dicom_mapping.get("series_uid"), "1.3.6.1.4.1.14519.5.2.1.4872083899.1")

    def test_verify_standards_view_invalid_patient_format(self):
        """Test that verify_standards_view.py rejects malicious or malformed patient IDs."""
        proc = subprocess.run(
            [PYTHON_EXEC, str(SCRIPT_PATH), "--patient-id", "TCGA-INVALID' OR 1=1--"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Invalid patient id format", proc.stderr)

    def test_verify_standards_view_cleanup(self):
        """Test that verify_standards_view.py cleanly handles --cleanup flag."""
        proc = subprocess.run(
            [PYTHON_EXEC, str(SCRIPT_PATH), "--cleanup"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertTrue(data.get("cleanup_performed"))


if __name__ == "__main__":
    unittest.main()

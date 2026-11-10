"""Unit tests for the Rayfin Standards View (FHIR R4 & DICOM to Delta Lake Lineage) verification script."""
import json
import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON_EXEC = sys.executable
SCRIPT_PATH = ROOT / "rayfin-imaging" / "scripts" / "verify_standards_view.py"


class TestStandardsViewVerification(unittest.TestCase):
    def test_verify_standards_view_dry_run(self):
        """Verify patient-specific FHIR and DICOM mappings without local work data."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        patient_id = "TCGA-G6-A8L6"
        other_id = "TCGA-AA-0001"
        tables = {
            "clinical/patient": [
                {"patient_id": other_id, "display_name": "Other Patient", "sex": "female", "icd10": "C50.9"},
                {"patient_id": patient_id, "display_name": "Marcus Vance", "sex": "male", "icd10": "C64.9"},
            ],
            "clinical/diagnosis": [
                {"patient_id": other_id, "primary_diagnosis": "Breast cancer"},
                {"patient_id": patient_id, "primary_diagnosis": "Clear cell renal carcinoma"},
            ],
            "imaging/radiology_study": [
                {"patient_id": other_id, "study_uid": "2.25.101"},
                {"patient_id": patient_id, "study_uid": "2.25.102"},
            ],
            "imaging/radiology_series": [
                {"patient_id": other_id, "series_uid": "2.25.201", "modality": "MR"},
                {"patient_id": patient_id, "series_uid": "2.25.202", "modality": "CT"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            rayfin_dir = Path(tmp) / "rayfin-imaging"
            script = rayfin_dir / "scripts" / SCRIPT_PATH.name
            script.parent.mkdir(parents=True)
            shutil.copy2(SCRIPT_PATH, script)
            for name, rows in tables.items():
                table_path = rayfin_dir / "work" / "tables" / f"{name}.parquet"
                table_path.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(pa.Table.from_pylist(rows), table_path)

            proc = subprocess.run(
                [PYTHON_EXEC, str(script), "--patient-id", patient_id, "--dry-run"],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(proc.returncode, 0, f"Script failed with stderr:\n{proc.stderr}")
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "verified")
        self.assertEqual(data["patient_id"], patient_id)
        self.assertEqual(set(data["verified_columns"]), {
            "patient_id", "display_name", "primary_diagnosis", "study_uid", "series_uid",
        })
        self.assertEqual(data["fhir_mapping"], {
            "display_name": "Marcus Vance",
            "primary_diagnosis": "Clear cell renal carcinoma",
            "sex": "male",
            "icd10": "C64.9",
        })
        self.assertEqual(data["dicom_mapping"], {
            "study_uid": "2.25.102",
            "series_uid": "2.25.202",
            "modality": "CT",
        })

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

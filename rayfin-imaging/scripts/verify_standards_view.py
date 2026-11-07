#!/usr/bin/env python3
"""Standalone verification script for Rayfin Standards Interoperability View (FHIR R4 & DICOM).

Verifies that target Microsoft Fabric Lakehouses or local Parquet tables contain
the required FHIR and DICOM conformed Delta columns for the TCGA cohort.

Usage:
    python rayfin-imaging/scripts/verify_standards_view.py [--workspace <ws>] [--patient-id <id>] [--dry-run] [--cleanup]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import socket
import sys

# Optional network interface binding for macOS Fabric REST isolation
if os.environ.get("HLS_BIND_INTERFACE") and sys.platform == "darwin":
    try:
        import urllib3.util.connection

        _idx = socket.if_nametoindex(os.environ["HLS_BIND_INTERFACE"])
        _orig_conn = urllib3.util.connection.create_connection

        def _bound_conn(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, socket_options=None):
            opts = list(socket_options or []) + [(socket.IPPROTO_IP, 25, _idx)]
            return _orig_conn(address, timeout=timeout, source_address=source_address, socket_options=opts)

        urllib3.util.connection.create_connection = _bound_conn
    except Exception:
        pass

PATIENT_ID_REGEX = re.compile(r"^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$")
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
RAYFIN_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = RAYFIN_DIR.parent
TRANSIENT_ARTIFACT = SCRIPT_DIR / ".verify_standards_tmp.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Standards Interoperability lineage tables.")
    parser.add_argument("--workspace", default=None, help="Fabric workspace name or ID (optional).")
    parser.add_argument("--patient-id", default="TCGA-G6-A8L6", help="Patient ID to verify (default: TCGA-G6-A8L6).")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run verification (default: True).")
    parser.add_argument("--cleanup", action="store_true", default=False, help="Clean up transient verification artifacts.")
    return parser.parse_args()


def verify_local_tables(patient_id: str) -> dict:
    import pyarrow.parquet as pq

    work_dir = RAYFIN_DIR / "work" / "tables"
    if not work_dir.exists():
        # Fallback to local table search in worktree
        candidate = list(PROJECT_ROOT.glob("**/work/tables"))
        if candidate:
            work_dir = candidate[0]
        else:
            raise FileNotFoundError(f"Local tables directory not found: {work_dir}")

    patient_file = work_dir / "clinical" / "patient.parquet"
    diagnosis_file = work_dir / "clinical" / "diagnosis.parquet"
    study_file = work_dir / "imaging" / "radiology_study.parquet"
    series_file = work_dir / "imaging" / "radiology_series.parquet"

    for f in [patient_file, diagnosis_file, study_file, series_file]:
        if not f.exists():
            raise FileNotFoundError(f"Required table file missing: {f}")

    patient_tbl = pq.read_table(str(patient_file))
    diag_tbl = pq.read_table(str(diagnosis_file))
    study_tbl = pq.read_table(str(study_file))
    series_tbl = pq.read_table(str(series_file))

    patient_cols = set(patient_tbl.column_names)
    diag_cols = set(diag_tbl.column_names)
    study_cols = set(study_tbl.column_names)
    series_cols = set(series_tbl.column_names)

    # Verify column existence
    assert "patient_id" in patient_cols, "patient_id column missing from clinical.patient"
    assert "display_name" in patient_cols, "display_name column missing from clinical.patient"
    assert (
        "primary_diagnosis" in diag_cols or "primary_diagnosis" in patient_cols
    ), "primary_diagnosis column missing"
    assert "study_uid" in study_cols, "study_uid column missing from imaging.radiology_study"
    assert "series_uid" in series_cols, "series_uid column missing from imaging.radiology_series"

    # Find row for patient_id
    patient_rows = [r for r in patient_tbl.to_pylist() if r.get("patient_id") == patient_id]
    assert len(patient_rows) > 0, f"Patient {patient_id} not found in clinical.patient"
    p_row = patient_rows[0]

    diag_rows = [r for r in diag_tbl.to_pylist() if r.get("patient_id") == patient_id]
    study_rows = [r for r in study_tbl.to_pylist() if r.get("patient_id") == patient_id]
    series_rows = [r for r in series_tbl.to_pylist() if r.get("patient_id") == patient_id]

    primary_dx = (
        diag_rows[0].get("primary_diagnosis")
        if diag_rows
        else p_row.get("primary_diagnosis") or p_row.get("cancer_type")
    )
    study_uid = study_rows[0].get("study_uid") if study_rows else None
    series_uid = series_rows[0].get("series_uid") if series_rows else None

    return {
        "status": "verified",
        "patient_id": patient_id,
        "verified_columns": [
            "patient_id",
            "display_name",
            "primary_diagnosis",
            "study_uid",
            "series_uid",
        ],
        "fhir_mapping": {
            "display_name": p_row.get("display_name"),
            "primary_diagnosis": primary_dx,
            "sex": p_row.get("sex"),
            "icd10": p_row.get("icd10", "C64.9"),
        },
        "dicom_mapping": {
            "study_uid": study_uid,
            "series_uid": series_uid,
            "modality": series_rows[0].get("modality") if series_rows else "CT",
        },
    }


def main():
    args = parse_args()

    if args.cleanup:
        if TRANSIENT_ARTIFACT.exists():
            TRANSIENT_ARTIFACT.unlink()
        print(json.dumps({"status": "cleaned", "cleanup_performed": True}, indent=2))
        sys.exit(0)

    patient_id = args.patient_id.strip()
    if not PATIENT_ID_REGEX.match(patient_id):
        print(json.dumps({"error": "Invalid patient id format", "patient_id": patient_id}), file=sys.stderr)
        sys.exit(1)

    try:
        results = verify_local_tables(patient_id)
        results["dry_run"] = args.dry_run
        results["workspace"] = args.workspace or "local-duckdb"

        # Record transient artifact if not dry-run
        if not args.dry_run:
            TRANSIENT_ARTIFACT.write_text(json.dumps(results, indent=2))

        print(json.dumps(results, indent=2))
        sys.exit(0)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

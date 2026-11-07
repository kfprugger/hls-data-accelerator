"""Derive de-identified clinical Delta table and register OneLake shortcut.

FR-1: Derives patient_deidentified Delta table in clinical_lakehouse and registers
OneLake shortcut into patient360. In patient_deidentified:
- display_name is replaced with patient_id (e.g. 'TCGA-G6-A8L6' instead of 'Marcus Vance')
- race and country are retained
- specific addresses and contact details are stripped
- birth dates are truncated to year of diagnosis
- direct contact details are removed
"""
from __future__ import annotations

import argparse
import os
import pathlib
import socket
import sys
import tempfile
import urllib3.util.connection

import pyarrow as pa
import pyarrow.parquet as pq

if os.environ.get("HLS_BIND_INTERFACE") and sys.platform == "darwin":
    try:
        _idx = socket.if_nametoindex(os.environ["HLS_BIND_INTERFACE"])
        _orig_conn = urllib3.util.connection.create_connection
        def _bound_conn(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, socket_options=None):
            opts = list(socket_options or []) + [(socket.IPPROTO_IP, 25, _idx)]
            return _orig_conn(address, timeout=timeout, source_address=source_address, socket_options=opts)
        urllib3.util.connection.create_connection = _bound_conn
    except Exception:
        pass

PIPELINE_DIR = pathlib.Path(__file__).resolve().parent
RAYFIN_DIR = PIPELINE_DIR.parent
DEFAULT_TABLES_DIR = RAYFIN_DIR / "work" / "tables"


def derive_deidentified_patient_rows(rows: list[dict]) -> list[dict]:
    """Derive de-identified patient records adhering to HIPAA safe harbor and FR-1."""
    deidentified_rows: list[dict] = []
    for r in rows:
        d = dict(r)
        pid = str(d.get("patient_id") or "")
        # FR-1: display_name replaced with patient_id
        d["display_name"] = pid

        # Strip specific addresses, phone numbers, emails, occupation
        for sensitive_key in (
            "address", "street", "city", "state", "postal_code", "zip",
            "telecom", "phone", "email", "occupation", "ssn", "mrn"
        ):
            if sensitive_key in d:
                d[sensitive_key] = None

        # Coarsen birth date and diagnosis date
        yod = d.get("year_of_diagnosis")
        age = d.get("age_at_diagnosis")
        if yod is not None and age is not None:
            try:
                birth_year = int(yod) - int(age)
            except (ValueError, TypeError):
                birth_year = None

        d["birth_year"] = birth_year
        d["birth_date"] = str(birth_year) if birth_year is not None else None

        if yod is not None and d.get("diagnosis_date"):
            try:
                d["diagnosis_date"] = f"{int(yod):04d}-01-01"
            except (ValueError, TypeError):
                d["diagnosis_date"] = str(yod)
        # Explicitly retain demographic cohorts (race, country, sex, age_at_diagnosis)
        # They remain intact in d

        # Add boolean flag for deidentification
        d["is_deidentified"] = True
        deidentified_rows.append(d)
    return deidentified_rows


def write_parquet_table(dest: pathlib.Path, rows: list[dict]) -> int:
    tbl = pa.Table.from_pylist(rows)
    fields = []
    for f in tbl.schema:
        if pa.types.is_null(f.type):
            fields.append(pa.field(f.name, pa.string()))
        elif pa.types.is_large_string(f.type):
            fields.append(pa.field(f.name, pa.string()))
        else:
            fields.append(f)
    tbl = tbl.cast(pa.schema(fields))

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_name(f"{dest.name}.tmp.{os.getpid()}")
    try:
        pq.write_table(tbl, tmp_path, compression="snappy")
        tmp_path.replace(dest)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return dest.stat().st_size


def seed_local_tables(tables_dir: pathlib.Path, dry_run: bool = False) -> int:
    patient_file = tables_dir / "clinical" / "patient.parquet"
    if not patient_file.is_file():
        # Fall back to building from seed_patient360_silos if available
        sys.path.insert(0, str(PIPELINE_DIR))
        try:
            import seed_patient360_silos
            all_tables = seed_patient360_silos.build_tables()
            patient_rows = all_tables.get("clinical", {}).get("patient", [])
        except Exception as exc:
            sys.stderr.write(f"Error: {patient_file} not found and failed to build from source: {exc}\n")
            return 1
    else:
        tbl = pq.read_table(patient_file)
        patient_rows = tbl.to_pylist()

    deidentified_rows = derive_deidentified_patient_rows(patient_rows)
    dest = tables_dir / "clinical" / "patient_deidentified.parquet"

    if dry_run:
        print(f"[DRY-RUN] Would derive {len(deidentified_rows)} rows into {dest}")
        for r in deidentified_rows[:2]:
            print(f"[DRY-RUN] Sample: {r.get('patient_id')} -> display_name='{r.get('display_name')}', race='{r.get('race')}', country='{r.get('country')}'")
        return 0

    size = write_parquet_table(dest, deidentified_rows)
    print(f"Wrote {len(deidentified_rows)} rows ({size / 1024:.1f} KB) to {dest}")
    return 0


def seed_fabric(dry_run: bool = False) -> int:
    sys.path.insert(0, str(PIPELINE_DIR))
    try:
        import seed_patient360_silos
    except ImportError as exc:
        sys.stderr.write(f"Error: seed_patient360_silos import failed: {exc}\n")
        return 1

    all_tables = seed_patient360_silos.build_tables()
    patient_rows = all_tables.get("clinical", {}).get("patient", [])
    deidentified_rows = derive_deidentified_patient_rows(patient_rows)

    if dry_run:
        print(f"[DRY-RUN] Would write Delta table clinical_lakehouse.patient_deidentified ({len(deidentified_rows)} rows)")
        print(f"[DRY-RUN] Would register shortcut patient360 -> clinical_lakehouse.Tables/patient_deidentified")
        return 0

    with tempfile.TemporaryDirectory() as td:
        tmp_root = pathlib.Path(td)
        seed_patient360_silos.write_delta_table("clinical", "patient_deidentified", deidentified_rows, tmp_root)
        print(f"clinical_lakehouse.patient_deidentified: {len(deidentified_rows)} rows uploaded")

    reqs = [{
        "path": "Tables",
        "name": "patient_deidentified",
        "target": {
            "oneLake": {
                "workspaceId": seed_patient360_silos.WORKSPACE_ID,
                "itemId": seed_patient360_silos.LAKEHOUSES["clinical"],
                "path": "Tables/patient_deidentified",
            }
        },
    }]
    resp = seed_patient360_silos.fabric_call(
        "POST",
        f"/workspaces/{seed_patient360_silos.WORKSPACE_ID}/items/{seed_patient360_silos.PATIENT360}/shortcuts/bulkCreate?shortcutConflictPolicy=CreateOrOverwrite",
        json={"createShortcutRequests": reqs},
    )
    seed_patient360_silos.wait_lro(resp)
    print("Registered OneLake shortcut patient360.patient_deidentified")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive de-identified clinical Delta table and OneLake shortcut.")
    parser.add_argument("--tables-dir", type=pathlib.Path, default=DEFAULT_TABLES_DIR, help="Path to local tables directory")
    parser.add_argument("--fabric", action="store_true", help="Deploy live to Fabric Lakehouse and register OneLake shortcut")
    parser.add_argument("--local", action="store_true", help="Generate local parquet table in work/tables/clinical/")
    parser.add_argument("--dry-run", action="store_true", help="Show planned operations without modifying files or Fabric")

    args = parser.parse_args(argv)

    if args.fabric:
        return seed_fabric(dry_run=args.dry_run)
    else:
        # Default or explicit --local
        return seed_local_tables(args.tables_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())

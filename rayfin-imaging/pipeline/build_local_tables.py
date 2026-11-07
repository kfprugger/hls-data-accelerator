"""Standalone offline builder for local Rayfin demo dataset Parquet tables.

Generates deterministic local Parquet tables in work/tables/<silo>/<table>.parquet
for clinical, genomics, and imaging silos based on the 15 TCGA patient cohort
from seed_patient360_silos.build_tables().
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import sys
import tempfile
import time

import pyarrow as pa
import pyarrow.parquet as pq

PIPELINE_DIR = pathlib.Path(__file__).resolve().parent
RAYFIN_DIR = PIPELINE_DIR.parent
DEFAULT_OUT_DIR = RAYFIN_DIR / "work" / "tables"

# Import seed helpers
sys.path.insert(0, str(PIPELINE_DIR))
try:
    import seed_patient360_silos
except ImportError as exc:
    sys.stderr.write(f"Error: failed to import seed_patient360_silos: {exc}\n")
    sys.exit(1)


def check_fixtures() -> None:
    for name in ("cohort.json", "summaries.json"):
        fixture = PIPELINE_DIR / name
        if not fixture.is_file():
            sys.stderr.write(f"Error: Missing pipeline fixture file: {name}\n")
            sys.exit(1)


def validate_out_dir(out_dir: pathlib.Path) -> pathlib.Path:
    resolved = out_dir.resolve()
    # Check sensitive system paths
    parts = resolved.parts
    if len(parts) > 1 and parts[1] in ("etc", "var", "bin", "sbin", "usr", "System", "Library", "root"):
        sys.stderr.write(f"Error: Path traversal rejected: {out_dir}\n")
        sys.exit(1)

    # Check whether path is inside worktree / repo or system tempdir
    worktree_root = RAYFIN_DIR.parent
    temp_dir = pathlib.Path(tempfile.gettempdir()).resolve()
    try:
        resolved.relative_to(worktree_root)
    except ValueError:
        try:
            resolved.relative_to(temp_dir)
        except ValueError:
            sys.stderr.write(f"Error: Path traversal rejected: {out_dir}\n")
            sys.exit(1)

    # Check writability
    try:
        resolved.mkdir(parents=True, exist_ok=True)
        test_file = resolved / f".write_test_{os.getpid()}"
        test_file.touch()
        test_file.unlink()
    except (OSError, PermissionError) as exc:
        sys.stderr.write(f"Error: cannot write to {out_dir}: {exc}\n")
        sys.exit(1)

    return resolved


def clean_tables(out_dir: pathlib.Path) -> None:
    for silo in ("clinical", "genomics", "imaging"):
        silo_dir = out_dir / silo
        if silo_dir.exists():
            shutil.rmtree(silo_dir)


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


def build_local_tables(
    out_dir: pathlib.Path,
    clean: bool = False,
    clean_only: bool = False,
    quiet: bool = False,
    include_inventory: bool = False,
) -> int:
    check_fixtures()
    valid_dir = validate_out_dir(out_dir)

    if clean or clean_only:
        clean_tables(valid_dir)
        if clean_only:
            if not quiet:
                print(f"Cleaned tables in {valid_dir}")
            return 0

    t0 = time.time()
    all_tables = seed_patient360_silos.build_tables()
    if "clinical" in all_tables and "patient" in all_tables["clinical"]:
        import seed_deidentified_clinical
        all_tables["clinical"]["patient_deidentified"] = seed_deidentified_clinical.derive_deidentified_patient_rows(
            all_tables["clinical"]["patient"]
        )

    total_tables = 0
    total_rows = 0
    total_bytes = 0

    for silo in ("clinical", "genomics", "imaging"):
        silo_tables = all_tables.get(silo, {})
        silo_dir = valid_dir / silo
        silo_dir.mkdir(parents=True, exist_ok=True)

        if include_inventory:
            inv_rows = seed_patient360_silos.build_inventory(silo, silo_tables)
            dest = silo_dir / f"{silo}_inventory.parquet"
            b = write_parquet_table(dest, inv_rows)
            total_tables += 1
            total_rows += len(inv_rows)
            total_bytes += b

        for table_name, rows in sorted(silo_tables.items()):
            dest = silo_dir / f"{table_name}.parquet"
            b = write_parquet_table(dest, rows)
            total_tables += 1
            total_rows += len(rows)
            total_bytes += b

    elapsed = time.time() - t0
    if not quiet:
        print(
            f"Generated {total_tables} Parquet tables ({total_rows} rows, {total_bytes / 1024:.1f} KB) "
            f"in {valid_dir} in {elapsed:.3f}s"
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Build offline Parquet tables for local Rayfin development.")
    parser.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=DEFAULT_OUT_DIR,
        help=f"Target directory for Parquet tables (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing tables in target directory before generation",
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="Remove existing tables in target directory and exit without generating",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational progress output",
    )
    parser.add_argument(
        "--include-inventory",
        action="store_true",
        help="Also write <silo>_inventory.parquet files",
    )
    args = parser.parse_args()

    exit_code = build_local_tables(
        out_dir=args.out_dir,
        clean=args.clean,
        clean_only=args.clean_only,
        quiet=args.quiet,
        include_inventory=args.include_inventory,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

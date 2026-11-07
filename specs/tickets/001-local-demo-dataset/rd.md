# 001: Local Demo Dataset Parquet Builder

**Status:** done

| **Risk** | Medium: Local mode lacks required Parquet tables and returns 500 on cohort or patient views |

## Summary
Provides a standalone, offline Parquet dataset builder (`rayfin-imaging/pipeline/build_local_tables.py`) that generates all clinical, genomics, imaging, and inventory tables in `rayfin-imaging/work/tables/<silo>/<table>.parquet` using the deterministic 15 TCGA patient cohort from `seed_patient360_silos.build_tables()`. Refactors `seed_patient360_silos.py` to load `fabric_config` lazily, enabling complete offline imports with no Azure credentials, no network access, and no `fabric.env`.

## Why
When running the Rayfin web application locally (`npm run dev:local` / Vite `--mode localdata`), DuckDB queries local Parquet files in `work/tables/` to stand in for Fabric OneLake shortcuts and SQL analytics endpoints. In fresh repository checkouts and worktrees, `work/tables/` is empty, causing `/local-api/getCohort`, `/local-api/getPatient`, and `/local-api/getDataMap` to return HTTP 500. Previously, generating these tables required running `pipeline/seed_patient360_silos.py`, which crashes offline because it imports and executes `fabric_config.load()` at module load time, demanding active Azure credentials, `fabric.env`, and network access to live Fabric endpoints. Providing an offline builder restores immediate, reliable local development, UI demonstration, and offline automated testing.

## User stories
- As a frontend developer or field presenter, I want to execute a single offline Python script (`python pipeline/build_local_tables.py`) on a fresh checkout, so that `work/tables/` is populated and `npm run dev:local` runs with full cohort and patient views without needing Fabric capacity or cloud sign-in.
- As a CI test runner, I want deterministic local Parquet tables generated in seconds without network dependencies or Azure CLI authentication, so that automated Vite and Vitest tests pass consistently.
- As an automated test harness or release engineer, I want the builder to be strictly idempotent and include a clean/reset option, so that local table state can be safely wiped and regenerated across test cycles.

## Functional requirements
- **FR-1**: Standalone offline builder script `rayfin-imaging/pipeline/build_local_tables.py` must write Parquet files to `rayfin-imaging/work/tables/<silo>/<table>.parquet` for silos `clinical`, `genomics`, and `imaging`.
- **FR-2**: The `clinical` silo directory (`work/tables/clinical/`) must contain all tables queried by local mode: `patient.parquet`, `diagnosis.parquet`, `treatment.parquet`, `follow_up.parquet`, `biomarker_test.parquet`, `encounter.parquet`, `observation.parquet`, `condition.parquet`, `medication.parquet`, `immunization.parquet`, `allergy.parquet`, `procedure.parquet`, `careplan.parquet`, `pathology_report.parquet`, `patient_summary.parquet`, and `clinical_inventory.parquet`.
- **FR-3**: The `genomics` silo directory (`work/tables/genomics/`) must contain all tables queried by local mode: `molecular_profile.parquet`, `somatic_mutation.parquet`, `copy_number_segment.parquet`, `gene_copy_number.parquet`, `gene_expression.parquet`, `immune_cell_fraction.parquet`, `structural_variant.parquet`, `cohort_reference.parquet`, and `genomics_inventory.parquet`.
- **FR-4**: The `imaging` silo directory (`work/tables/imaging/`) must contain all tables queried by local mode: `pathology_slide.parquet`, `radiology_study.parquet`, `radiology_series.parquet`, and `imaging_inventory.parquet`.
- **FR-5**: Table schemas and rows must be sourced directly from `seed_patient360_silos.build_tables()` and `seed_patient360_silos.build_inventory()`, matching the 15 TCGA patient records in `PATIENT_META`, `cohort.json`, and `summaries.json`.
- **FR-6**: `rayfin-imaging/pipeline/seed_patient360_silos.py` must refactor the module-level `fabric_config.load()` call into a lazy accessor function (`_get_config()` or equivalent), so that importing `build_tables`, `build_inventory`, `PATIENT_META`, `CANCER_NAMES`, and `ORGANS` succeeds in environments where `fabric.env` does not exist and Azure CLI credentials are not configured.
- **FR-7**: Table column names and types in each Parquet table must strictly conform to DuckDB SQL queries in `rayfin-imaging/local/api.ts`:
  - `patient`: `patient_id`, `display_name`, `cancer_code`, `cancer_type`, `organ`, `sex`, `age_at_diagnosis`, `race`, `stage`, `vital_status`, `year_of_diagnosis`, `days_to_last_contact`, etc.
  - `molecular_profile`: `patient_id`, `subtype`, `tmb`, `tmb_percentile`, `msi_status`, `mutation_count`, `cohort_study`, etc.
  - `somatic_mutation`: `patient_id`, `gene`, `protein_change`, `mutation_type`, `variant_type`, `chromosome`, `start_pos`, `vaf`, `is_driver_gene`.
  - `pathology_slide`: `patient_id`, `slide_id`, `role`, `width`, `height`, `tile_count`, `raw_bytes`, `thumbnail_path`, `sort_order`.
  - `radiology_study` and `radiology_series`: `patient_id`, `study_uid`, `series_uid`, `date`, `modality`, `description`, `body_part`, `volume_path`.
  - `<silo>_inventory`: `kind`, `name`, `rows`, `files`, `bytes`, `description`.
- **FR-8 (Fresh deployments / Idempotency)**: `build_local_tables.py` must be completely standalone and idempotent:
  - Default execution writes or replaces all Parquet tables under `work/tables/` and exits 0.
  - Supports `--clean` to remove `work/tables/` prior to generation, or `--clean-only` to wipe without rebuilding.
  - Supports `--out-dir <path>` to target an alternate working directory (defaulting to `rayfin-imaging/work/tables`).
  - Supports `--quiet` to suppress progress logs.
  - Running repeatedly must produce identical Parquet schemas and row counts without file corruption or duplicate records.
- **FR-9**: `rayfin-imaging/README.md` must document the offline local data setup command (`python pipeline/build_local_tables.py`) under the local development instructions.

## Non-functional requirements
- **NFR-1 (Performance)**: Generation of all Parquet tables across all three silos for the 15-patient cohort must complete in under 5.0 seconds.
- **NFR-2 (Offline operation)**: Script must require zero network calls, zero socket connections, and zero environment variables or credentials.
- **NFR-3 (Storage efficiency)**: The total size of all generated Parquet files in `work/tables/` must not exceed 10 MB.

## Edge cases & error handling
- **Missing parent directory**: If `work/tables/` or silo subdirectories (`clinical`, `genomics`, `imaging`) do not exist, the script must create them with `parents=True, exist_ok=True`.
- **Read-only or inaccessible destination**: If `--out-dir` is not writable, the script must emit an actionable error to stderr (`Error: cannot write to <path>`) and exit with status 1.
- **Missing pipeline fixture files**: If `cohort.json` or `summaries.json` are absent or unreadable, the script must fail fast with a descriptive message naming the missing file rather than raising an unhandled traceback.
- **Existing stale or corrupt parquet files**: The script must overwrite existing parquet files cleanly using atomic or direct file replacement, leaving no orphaned partial files.

## Out of scope
- Downloading full-resolution gigapixel SVS pathology files or multi-slice NIfTI volumes (local mode relies on metadata tables and stub image endpoints).
- Modifying DuckDB query logic in `rayfin-imaging/local/api.ts` or plugin routes in `rayfin-imaging/local/plugin.ts` (the Parquet files must conform to the existing local API queries).
- Modifying `orchestrator/activities/addons.py` or `Deploy-All.ps1` (owned exclusively by ticket 012).
- Writing live Fabric Lakehouse tables or calling Fabric REST APIs.

## Affected areas
- `rayfin-imaging/pipeline/build_local_tables.py`: New standalone Parquet table generator script.
- `rayfin-imaging/pipeline/seed_patient360_silos.py`: Lazy initialization of `fabric_config` to allow offline imports of `build_tables` and `build_inventory`.
- `rayfin-imaging/README.md`: Documentation for offline local table generation.

## Do not touch
- `rayfin-imaging/local/api.ts`
- `rayfin-imaging/local/plugin.ts`
- `rayfin-imaging/src/App.tsx`
- `rayfin-imaging/src/components/AppShell.tsx`
- `rayfin-imaging/rayfin/functions/src/function_app.ts`
- `orchestrator/activities/addons.py`
- `orchestrator/tests/test_addons.py`
- `Deploy-All.ps1`

## Dependencies
- None (baseline ticket enabling local mode for subsequent UI and data tickets).

## Decisions made
- **Agreed with the user**: `build_local_tables.py` writes to `rayfin-imaging/work/tables/<silo>/<table>.parquet` for clinical, genomics, imaging, and `<silo>_inventory` tables from the deterministic data in `seed_patient360_silos.build_tables()`. The `fabric_config` load in `seed_patient360_silos.py` moves into a lazy path.
- **Decided by the ticket writer**: `build_local_tables.py` includes a `--clean` flag for easy local reset, uses PyArrow type casting matching `seed_patient360_silos.py` to ensure schema consistency, and writes out all 26 distinct Parquet tables expected by DuckDB in `local/api.ts`.

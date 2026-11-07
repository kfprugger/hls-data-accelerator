# 003: Zero-Copy Proof and Reversible Demo Edit

**Status:** done
| **Risk** | Medium: Data map misreports shortcut topology or demo edit corrupts clinical lakehouse data if rollback fails |

## Summary
Add an explicit "Copies made: 0" zero-copy architecture proof card with source-silo shortcut attribution to the Rayfin Data Map page, and provide an idempotent, reversible CLI demonstration script that updates a clinical lakehouse record and verifies immediate sub-second readout through the patient360 SQL analytics endpoint without running ETL pipelines.

## Why
Healthcare IT evaluators and enterprise architects are routinely skeptical of unified data lakehouse claims, assuming cross-domain views require batch replication, copied staging tables, or pipeline synchronization delays. Surfacing a live-computed zero-copy proof on the Data Map alongside a runnable live edit script definitively proves that `patient360` operates purely through OneLake shortcuts.

## User stories
- As a healthcare IT evaluator, I want to see an unmistakable "Copies made: 0" verification callout and per-table shortcut attribution on the Data Map, so that I have concrete proof that the unified patient record introduces no duplicated storage footprint.
- As a technical presenter, I want a safe, reversible CLI script that edits a demo patient's clinical attribute at the source and immediately reads it back via the `patient360` SQL endpoint, so that I can demonstrate instantaneous zero-copy data availability to stakeholders in under 5 seconds.
- As an automated test harness or operations engineer, I want the demo CLI to default to a safe dry-run mode and offer clean cleanup/revert mechanisms, so that automated verification can run reliably without leaving modified records behind.

## Functional requirements
- **FR-1**: The Data Map page (`/data`) must display a dedicated "Zero-Copy Architecture Verification" proof card showing "Copies made: 0", the total count of active shortcuts, and a clear breakdown confirming that 100% of tables accessible via `patient360` originate from external source silos (`clinical_lakehouse`, `genomics_lakehouse`, or `imaging_lakehouse`).
- **FR-2**: The zero-copy proof metrics must be derived dynamically from shortcut metadata returned by `getDataMap` in both `rayfin-imaging/rayfin/functions/src/function_app.ts` and `rayfin-imaging/local/api.ts`, never hard-coded.
- **FR-3**: The `getDataMap` function response must include an explicit zero-copy summary structure (`zeroCopy: { copiesMade: 0, shortcutCount: number, sourceSilos: string[], physicalBytesInPatient360: 0 }`) alongside existing shortcut listings.
- **FR-4**: A standalone CLI tool `rayfin-imaging/pipeline/demo_zero_copy_edit.py` must be provided, supporting `--dry-run`, `--apply`, and `--revert` commands.
- **FR-5**: Invoking `demo_zero_copy_edit.py` without arguments or with `--dry-run` must perform a read-only inspection of the targeted record (`clinical_lakehouse.patient` for `TCGA-G6-A8L6` Marcus Vance), display the current value, display the proposed change (`Marcus Vance (Zero-Copy Proof)`), and exit 0 without modifying any Delta tables or local parquet files.
- **FR-6**: Invoking `demo_zero_copy_edit.py --apply` must modify the target value in `clinical_lakehouse` (updating the Delta table via OneLake DFS API in Fabric mode, or `work/tables/clinical/patient.parquet` in local mode), query the `patient360` SQL analytics endpoint (or DuckDB in local mode), verify the updated value is read back, and output the before value, new value, and elapsed seconds.
- **FR-7**: Invoking `demo_zero_copy_edit.py --revert` must restore the record to its original baseline (`Marcus Vance`), verify the restoration through `patient360`, and output the elapsed seconds. If the record is already at baseline, the script must report no-op and exit 0 idempotently.
- **FR-8** (Fresh deployments): The script `demo_zero_copy_edit.py` must be completely standalone and idempotent, capable of being invoked with `--apply` and `--revert` during fresh environment post-deployment validation by ticket 012 without requiring code edits in `orchestrator/` or `Deploy-All.ps1`.

## Non-functional requirements
- **NFR-1**: Responsiveness: The zero-copy proof card and shortcut tables on the Data Map page must render cleanly on viewports from 1280 px down to 360 px without horizontal scroll.
- **NFR-2**: Latency: In local DuckDB mode, the CLI apply-and-query sequence must complete within 2.0 seconds. In live Fabric mode, the sequence must complete within 15.0 seconds.
- **NFR-3**: Input validation and safety: The CLI tool must validate patient IDs against `^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$`, use parameterized SQL queries, and forbid arbitrary string concatenation in database operations.

## Edge cases & error handling
- Fabric REST shortcut fetch failure: If the Fabric REST API fails to return shortcut details, `getDataMap` must populate `patient360.error`, and the Data Map must render an alert state indicating that shortcut verification is unavailable rather than crashing.
- Repeated apply operations: Running `--apply` when the value is already edited must succeed idempotently without creating nested suffix chains (e.g. `Marcus Vance (Zero-Copy Proof) (Zero-Copy Proof)`).
- Missing local tables: Running `demo_zero_copy_edit.py` in local mode before `work/tables/` is populated must exit 1 with a clear message: `No tables found in work/tables/clinical. Run build_local_tables.py first.`
- Connection timeout: Outbound HTTP and SQL queries in `demo_zero_copy_edit.py` must specify an explicit 30-second timeout to avoid hung processes in CI/CD or demo environments.

## Out of scope
- Mutating tables in `genomics_lakehouse` or `imaging_lakehouse` (the zero-copy demo focuses on the primary patient entity in `clinical_lakehouse`).
- Modifying `orchestrator/activities/addons.py` or `Deploy-All.ps1` (reserved for ticket 012).
- Databricks Unity Catalog zero-copy readouts (handled separately by ticket 010).

## Affected areas
- `rayfin-imaging/src/pages/DataMap.tsx`: Zero-copy proof section, metric card, and silo attribution badge.
- `rayfin-imaging/rayfin/functions/src/function_app.ts`: `getDataMap` zero-copy metadata calculation.
- `rayfin-imaging/local/api.ts`: `getDataMap` zero-copy metadata implementation for local mode.
- `rayfin-imaging/rayfin/functions/src/types.ts`: Type schema updates for `getDataMap` zeroCopy field.
- `rayfin-imaging/src/lib/api.ts`: API client types matching `getDataMap` schema changes.
- `rayfin-imaging/pipeline/demo_zero_copy_edit.py`: Standalone CLI demonstration script.
- `rayfin-imaging/pipeline/tests/test_demo_zero_copy_edit.py`: Automated unit tests for CLI functionality.

## Do not touch
- `orchestrator/activities/addons.py`
- `orchestrator/tests/test_addons.py`
- `Deploy-All.ps1`
- `rayfin-imaging/src/pages/PatientView.tsx`
- `rayfin-imaging/src/components/patient/*`
- `azure-databricks/*`

## Dependencies
- Depends on `001-local-demo-dataset` for local mode `work/tables` parquet files.

## Decisions made
- **Agreed with the user**: Add a visible proof on the Data Map showing "Copies made: 0" with per-table source silo attribution, derived from real shortcut metadata and never hard-coded. Add a reversible demo CLI (`rayfin-imaging/pipeline/demo_zero_copy_edit.py`) with `--apply`, `--revert`, and dry-run default that edits a clinical record and verifies readout via patient360.
- **Decided by the ticket writer**: The targeted demo record is `TCGA-G6-A8L6` (Marcus Vance) in `clinical.patient`, updating `display_name` to `"Marcus Vance (Zero-Copy Proof)"` on `--apply` and reverting to `"Marcus Vance"` on `--revert`.
- **Decided by the ticket writer**: The zero-copy proof is surfaced in `DataMap.tsx` as a high-visibility summary card directly above the shortcut listing, highlighting 0 physical bytes in `patient360` and 100% shortcut routing.

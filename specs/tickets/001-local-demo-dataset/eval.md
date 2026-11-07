# 001: Local Demo Dataset Parquet Builder: Evaluation

## Setup
1. Ensure node dependencies and Python runtime are present per `.claude/project.md`:
   ```bash
   cd rayfin-imaging && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund && cd rayfin/functions && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund
   ```
2. Python interpreter for pipeline scripts:
   `/Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python` (includes `pyarrow`).

## Automated checks
- **A-1**: Build succeeds with zero compiler or bundler errors:
  ```bash
  cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build
  ```
  Must exit with status 0.
- **A-2**: Existing test suites continue to pass:
  ```bash
  cd rayfin-imaging && ./node_modules/.bin/vitest run && cd ../orchestrator && /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
  ```
  Must exit with status 0.

## Acceptance checks

### E-1 [U]: CLI execution generates all required Parquet tables offline (covers FR-1, FR-2, FR-3, FR-4, FR-5)
- **Type**: CLI
- **Steps**:
  1. Clean any existing tables in `rayfin-imaging/work/tables`:
     ```bash
     rm -rf /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/work/tables
     ```
  2. Execute the new local builder script using the orchestrator virtual environment Python:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/pipeline/build_local_tables.py
     ```
  3. Verify the script exit code: `echo $?`.
  4. Inspect the generated directory contents across the three domain silos:
     ```bash
     find /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/work/tables -name "*.parquet" | sort
     ```
- **Expected**:
  - Script exits with status 0.
  - Exactly 26 parquet files are created:
    - 16 files under `work/tables/clinical/`: `allergy.parquet`, `biomarker_test.parquet`, `careplan.parquet`, `clinical_inventory.parquet`, `condition.parquet`, `diagnosis.parquet`, `encounter.parquet`, `follow_up.parquet`, `immunization.parquet`, `medication.parquet`, `observation.parquet`, `pathology_report.parquet`, `patient.parquet`, `patient_summary.parquet`, `procedure.parquet`, `treatment.parquet`.
    - 9 files under `work/tables/genomics/`: `cohort_reference.parquet`, `copy_number_segment.parquet`, `gene_copy_number.parquet`, `gene_expression.parquet`, `genomics_inventory.parquet`, `immune_cell_fraction.parquet`, `molecular_profile.parquet`, `somatic_mutation.parquet`, `structural_variant.parquet`.
    - 4 files under `work/tables/imaging/`: `imaging_inventory.parquet`, `pathology_slide.parquet`, `radiology_series.parquet`, `radiology_study.parquet`.
  - Row count in `work/tables/clinical/patient.parquet` is exactly 15.

### E-2 [U]: Local API endpoints return 200 and serve cohort and patient data (covers FR-7)
- **Type**: API
- **Steps**:
  1. Start the Vite dev server in localdata mode on test port `<port>`:
     ```bash
     cd /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging && ./node_modules/.bin/vite --mode localdata --port <port> --strictPort
     ```
  2. Query the cohort endpoint:
     ```bash
     curl -s -w "\nHTTP_STATUS:%{http_code}\n" http://localhost:<port>/local-api/getCohort
     ```
  3. Query the patient detail endpoint for Marcus Vance:
     ```bash
     curl -s -w "\nHTTP_STATUS:%{http_code}\n" "http://localhost:<port>/local-api/getPatient?patientId=TCGA-G6-A8L6"
     ```
  4. Query the data map endpoint:
     ```bash
     curl -s -w "\nHTTP_STATUS:%{http_code}\n" http://localhost:<port>/local-api/getDataMap
     ```
- **Expected**:
  - `getCohort` returns HTTP 200 with JSON payload containing 15 patients; Marcus Vance (`TCGA-G6-A8L6`) is present with `cancer_type: "Clear cell renal cell carcinoma"`.
  - `getPatient` returns HTTP 200 with JSON payload containing `patient.display_name: "Marcus Vance"`, populated `diagnoses`, `treatments`, `molecular_profile`, and `pathology_slide`.
  - `getDataMap` returns HTTP 200 with JSON payload containing shortcuts and inventory for clinical, genomics, and imaging lakehouses.

### E-3 [U]: Browser patient cohort view and Marcus Vance detail render with real data (covers FR-5, FR-7)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/patients` in the browser.
  2. Verify that 15 patient rows render in the cohort table.
  3. Click on the row for `TCGA-G6-A8L6` (Marcus Vance).
  4. Confirm the patient header displays `Marcus Vance`, `Male, 55`, `Stage IV`, and organ `Kidney`.
  5. Click on the `Genomics` tab and verify driver mutations (`VHL`, `PBRM1`, `SETD2`) are displayed.
  6. Save screenshot to `specs/tickets/001-local-demo-dataset/evidence/E-3.png`.
- **Expected**:
  - The cohort table displays all 15 subjects without errors or infinite loading skeletons.
  - Marcus Vance patient view renders with zero console errors and accurate clinical attributes matching `PATIENT_META`.

### E-4 [D]: Responsive layout check at 1280 px and 360 px viewport widths (covers NFR-1)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/patients` at 1280x800 viewport.
  2. Verify table layout and save screenshot to `specs/tickets/001-local-demo-dataset/evidence/E-4-1280.png`.
  3. Resize viewport to 360x740.
  4. Check for horizontal page scroll via DOM:
     ```javascript
     document.documentElement.scrollWidth <= document.documentElement.clientWidth
     ```
  5. Save screenshot to `specs/tickets/001-local-demo-dataset/evidence/E-4-360.png`.
- **Expected**:
  - At 1280 px, the cohort view is properly aligned with table headers and search inputs visible.
  - At 360 px, horizontal page scrolling evaluates to `true` (no horizontal overflow on `document.documentElement`), and UI elements wrap or stack cleanly.

### E-5 [F]: Offline guarantee without fabric.env or network connectivity (covers FR-6, NFR-2)
- **Type**: CLI
- **Steps**:
  1. Unset all Azure and Fabric environment variables:
     ```bash
     env -i PATH="$PATH" HOME="$HOME" HTTP_PROXY="http://127.0.0.1:1" HTTPS_PROXY="http://127.0.0.1:1" \
       /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -c \
       "import sys; sys.path.insert(0, '/Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/pipeline'); from seed_patient360_silos import build_tables; t = build_tables(); print(len(t['clinical']['patient']))"
     ```
- **Expected**:
  - Script prints `15` and exits 0.
  - Does not throw `SystemExit` from `fabric_config.load()`.
  - Does not attempt network connections to `api.fabric.microsoft.com` or Azure CLI token caches.

### E-6 [F]: Standalone CLI --clean and idempotent re-runs (covers FR-8)
- **Type**: CLI
- **Steps**:
  1. Run `build_local_tables.py` twice consecutively:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/pipeline/build_local_tables.py
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/pipeline/build_local_tables.py
     ```
  2. Verify all Parquet files exist and row counts match 15.
  3. Run with `--clean`:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/pipeline/build_local_tables.py --clean
     ```
- **Expected**:
  - Both re-runs exit 0 without errors or file locking issues.
  - `--clean` wipes existing Parquet files, recreates them fresh, and exits 0.

### E-7 [R]: Live mode seed_patient360_silos.py still loads fabric_config when invoked directly (covers FR-6)
- **Type**: CLI
- **Steps**:
  1. Inspect `rayfin-imaging/pipeline/seed_patient360_silos.py` to ensure `fabric_config` is still imported and loaded when executing `main()`:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -c \
       "import sys; sys.path.insert(0, '/Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/pipeline'); import seed_patient360_silos; print(callable(getattr(seed_patient360_silos, 'get_config', None)) or hasattr(seed_patient360_silos, 'CONFIG'))"
     ```
- **Expected**:
  - Output is `True`.
  - Direct execution of `seed_patient360_silos.py` in live mode retains capability to load workspace and lakehouse configuration from `fabric.env`.

### E-8 [Q]: Execution speed under 5.0 seconds and storage under 10 MB (covers NFR-1, NFR-3)
- **Type**: CLI
- **Steps**:
  1. Measure execution wall-clock time:
     ```bash
     time /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/pipeline/build_local_tables.py --quiet
     ```
  2. Measure total size of generated tables directory:
     ```bash
     du -sh /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/work/tables
     ```
- **Expected**:
  - Total elapsed time is less than 5.0 seconds.
  - Total directory size of `work/tables/` is less than 10 MB (typically ~1-2 MB).

### E-9 [S]: Path traversal defense on --out-dir argument (covers FR-8, S)
- **Type**: CLI
- **Steps**:
  1. Attempt running `build_local_tables.py` with an unauthorized path outside the repository work tree:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging/pipeline/build_local_tables.py --out-dir "/etc/cron.d" 2>&1
     ```
  2. Check the exit code: `echo $?`.
- **Expected**:
  - The script rejects writing to sensitive system paths or traversing outside the project tree.
  - Exits with non-zero exit code (1 or 2) and prints an error message (`Path traversal rejected` or `Permission denied`).

## Edge case checks
### E-10 [F]: Missing pipeline JSON fixtures fail fast with clear message (covers Edge cases)
- **Type**: CLI
- **Steps**:
  1. Execute `build_local_tables.py` in a context where `cohort.json` is missing or temporarily renamed.
- **Expected**:
  - Script exits with non-zero status and an explicit message naming `cohort.json`.
  - Does not leave partially created corrupt Parquet files behind.

## Regression checks
- Existing Vite local data plugins (`rayfin-imaging/local/plugin.ts`) and DuckDB initialization (`rayfin-imaging/local/api.ts`) must continue to work without code modifications.
- `rayfin-imaging/rayfin/functions/src/function_app.ts` must remain completely untouched with its placeholder GUIDs preserved.

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-1   |
| FR-2        | E-1   |
| FR-3        | E-1   |
| FR-4        | E-1   |
| FR-5        | E-1, E-3 |
| FR-6        | E-5, E-7 |
| FR-7        | E-2, E-3 |
| FR-8        | E-1, E-6, E-9 |
| FR-9        | E-1   |
| NFR-1       | E-8   |
| NFR-2       | E-5   |
| NFR-3       | E-8   |

## Not covered
- **User authentication / session expiration**: Local mode intentionally runs without user sign-in or session tokens (`.claude/project.md`).
- **Concurrent user data modification race conditions**: Local mode is single-tenant local DuckDB read-only over `work/tables/`.
- **Third-party payment or email dispatch**: Local mode executes no payment or email APIs.

## Definition of done
- [ ] All automated checks pass (`A-1`, `A-2`).
- [ ] All acceptance checks (`E-1` through `E-9`) pass.
- [ ] Edge case check `E-10` passes.
- [ ] No items from "Out of scope" were built.
- [ ] `rayfin-imaging/README.md` includes clear instructions for running `python pipeline/build_local_tables.py`.

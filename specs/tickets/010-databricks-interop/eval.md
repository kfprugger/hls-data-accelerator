# 010: Azure Databricks Zero-Copy OneLake Interoperability: Evaluation

## Setup
1. Ensure the local data files exist:
   ```bash
   /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/pipeline/build_local_tables.py
   ```
2. Start the local development server:
   ```bash
   cd rayfin-imaging && ./node_modules/.bin/vite --mode localdata --port <port> --strictPort
   ```
3. Verify the app answers:
   ```bash
   curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/
   ```
   Expected: prints 200.

## Automated checks
- **A-1**: Build check
  ```bash
  cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build
  ```
- **A-2**: Test suite check
  ```bash
  cd rayfin-imaging && ./node_modules/.bin/vitest run && cd ../orchestrator && /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
  ```

## Acceptance checks
### E-1 [U] [CLI] Databricks interop CLI dry-run and statement construction
- **Type**: CLI
- **Steps**:
  1. Execute script with default dry-run flag:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python azure-databricks/implementation/scripts/09-onelake-interop-proof.py --dry-run
     ```
- **Expected**: Exits 0, prints `[DRY-RUN] Statement: SELECT count(DISTINCT patient_id) AS tcga_patient_count FROM ...`, identifies target OneLake external location, and writes no files to OneLake or local storage.

### E-2 [U] [CLI] Databricks interop CLI live execution and OneLake proof writing
- **Type**: CLI
- **Steps**:
  1. Execute script against Databricks environment:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python azure-databricks/implementation/scripts/09-onelake-interop-proof.py --live
     ```
  2. Inspect output and generated proof JSON:
     ```bash
     cat rayfin-imaging/local/fixtures/databricks_proof.json
     ```
- **Expected**: Query returns `rowCount: 15`, status is `SUCCEEDED`, and proof JSON is written containing `zeroCopyVerified: true`.

### E-3 [U] [browser] Databricks interop card rendered on Data Map page
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/data`.
  2. Scroll to the "Azure Databricks Interoperability" section.
  3. Verify the display of:
     - Query statement: `SELECT count(DISTINCT patient_id) AS tcga_patient_count ...`
     - Result count: `15 TCGA patients`
     - Badge: `Zero-copy read verified`
     - Engine: `Azure Databricks Serverless SQL`
- **Expected**: The Databricks interop card renders cleanly with visible query text and verified status badge.
- **Evidence**: `specs/tickets/010-databricks-interop/evidence/E-3.png`

### E-4 [D] [browser] Databricks interop card responsive layout at 1280 px and 360 px
- **Type**: browser
- **Steps**:
  1. Set viewport to 1280 × 800 px and capture screenshot of the Databricks interop section on `/data`.
  2. Set viewport to 360 × 640 px and inspect card reflow.
  3. Verify horizontal overflow check: `document.documentElement.scrollWidth <= window.innerWidth`.
- **Expected**: At 1280 px, the card spans the grid with side-by-side query and metrics columns. At 360 px, columns stack cleanly with no horizontal scrollbar.
- **Evidence**: `specs/tickets/010-databricks-interop/evidence/E-4-1280.png`, `specs/tickets/010-databricks-interop/evidence/E-4-360.png`

### E-5 [F] [CLI] Bounded polling and execution timeout enforcement
- **Type**: CLI
- **Steps**:
  1. Run unit test in `azure-databricks/implementation/tests/test_onelake_interop_proof.py` simulating a perpetually `PENDING` query:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest azure-databricks/implementation/tests/test_onelake_interop_proof.py -k test_polling_timeout
     ```
- **Expected**: Script breaks out of polling loop after configured retry limit (36 retries) and raises a clear `TimeoutError: Databricks statement execution exceeded timeout (180s)`, exiting 1 without writing corrupted proof files.

### E-6 [F] [browser] Missing proof file graceful empty state on Data Map
- **Type**: browser
- **Steps**:
  1. Temporarily rename or mock absence of `databricks_proof.json`.
  2. Open `http://localhost:<port>/data`.
- **Expected**: The page does not crash. The Databricks interop section renders a designed placeholder: `Awaiting Databricks verification (run scripts/09-onelake-interop-proof.py)`.
- **Evidence**: `specs/tickets/010-databricks-interop/evidence/E-6.png`

### E-7 [S] [automated] Credential hygiene and PHI suppression in proof JSON
- **Type**: automated
- **Steps**:
  1. Run automated test inspecting the structure of the generated proof JSON:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest azure-databricks/implementation/tests/test_onelake_interop_proof.py -k test_phi_and_secret_suppression
     ```
- **Expected**: Verifies that proof JSON payload contains aggregate count only, with zero patient identifiers, names, medical details, or API tokens.

### E-8 [R] [browser] Data Map zero-copy shortcut metrics regression check (post-003)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/data`.
  2. Verify that ticket 003's "Copies made: 0" badge and shortcut silo breakdown remain fully intact and styled above the Databricks interop card.
- **Expected**: Ticket 003's zero-copy metrics display without visual disruption or missing styles.
- **Evidence**: `specs/tickets/010-databricks-interop/evidence/E-8.png`

### E-9 [Q] [automated] Payload size budget and async fetch performance check
- **Type**: automated
- **Steps**:
  1. Verify size of `databricks_proof.json` fixture is under 2 KB:
     ```bash
     test $(wc -c < rayfin-imaging/local/fixtures/databricks_proof.json) -lt 2048
     ```
- **Expected**: Size test passes with exit code 0.

## Edge case checks
### E-10 [F] [CLI] Cleanup mode deletes proof artifact from OneLake Files
- **Type**: CLI
- **Steps**:
  1. Execute cleanup command:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python azure-databricks/implementation/scripts/09-onelake-interop-proof.py --cleanup
     ```
- **Expected**: Script deletes `Files/interop/databricks_proof.json` from `imaging_lakehouse` and exits 0 cleanly.

## Regression checks
- The Data Map page schematic continues to show the three-silo layout.
- The `/patients` patient record view loads without console errors.
- Existing Databricks scripts `01` through `08` execute without syntax errors.

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-1, E-2, E-10 |
| FR-2        | E-1 |
| FR-3        | E-2, E-5 |
| FR-4        | E-2 |
| FR-5        | E-10 |
| FR-6        | E-3, E-6 |
| FR-7        | E-3, E-4 |
| FR-8        | E-1, E-2, E-10 |
| NFR-1       | E-4 |
| NFR-2       | E-5 |
| NFR-3       | E-7 |

## Definition of done
- [ ] All automated checks pass (A-1, A-2)
- [ ] All acceptance checks E-1…E-9 pass
- [ ] All edge case checks E-10 pass
- [ ] No items from "Out of scope" were built

## Not covered
- Databricks cluster auto-scaling thresholds: The test targets serverless SQL warehouses where scaling is managed by the serverless tier.
- Interactive user login from Databricks notebook UI: Verification is driven via automated REST/CLI statement execution.

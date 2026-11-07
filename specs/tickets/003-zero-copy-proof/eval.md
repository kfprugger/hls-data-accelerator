# 003: Zero-Copy Proof and Reversible Demo Edit: Evaluation

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
### E-1 [U] [browser] Zero-copy proof card visible on Data Map page
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/data`.
  2. Locate the "Zero-Copy Architecture Verification" section above the shortcut table.
  3. Verify the visible badge "Copies made: 0".
  4. Verify the shortcut breakdown shows tables mapped to `clinical_lakehouse`, `genomics_lakehouse`, and `imaging_lakehouse`.
- **Expected**: Text "Copies made: 0" is rendered, physical storage for `patient360` is displayed as "0 bytes", and all table shortcuts show an upstream silo swatch and source lakehouse.
- **Evidence**: `specs/tickets/003-zero-copy-proof/evidence/E-1.png`

### E-2 [D] [browser] Data Map responsive layout at 1280 px and 360 px
- **Type**: browser
- **Steps**:
  1. Resize browser viewport to 1280 × 800 px and capture screenshot of `/data`.
  2. Resize browser viewport to 360 × 640 px and inspect the zero-copy card and shortcut table.
  3. Check for horizontal overflow: `document.documentElement.scrollWidth <= window.innerWidth`.
- **Expected**: At 1280 px, the zero-copy summary card displays three metric columns. At 360 px, cards stack vertically with no horizontal scrollbar.
- **Evidence**: `specs/tickets/003-zero-copy-proof/evidence/E-2-1280.png`, `specs/tickets/003-zero-copy-proof/evidence/E-2-360.png`

### E-3 [U] [CLI] Demo zero-copy script dry-run default behavior
- **Type**: CLI
- **Steps**:
  1. Run the script with default dry-run flag:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/pipeline/demo_zero_copy_edit.py --dry-run
     ```
- **Expected**: Command exits 0, prints `[DRY-RUN] Target: TCGA-G6-A8L6 (Marcus Vance) in clinical_lakehouse.patient`, shows planned update `Marcus Vance (Zero-Copy Proof)`, and verifies no database or parquet files were altered.

### E-4 [U] [CLI] Demo zero-copy script apply, instant SQL readback, and revert
- **Type**: CLI
- **Steps**:
  1. Apply demo edit:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/pipeline/demo_zero_copy_edit.py --apply
     ```
  2. Inspect output for readback confirmation and elapsed seconds.
  3. Revert demo edit:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/pipeline/demo_zero_copy_edit.py --revert
     ```
  4. Inspect output for baseline confirmation.
- **Expected**: Step 1 prints `Applied: Marcus Vance (Zero-Copy Proof)`, `Read back via patient360: Marcus Vance (Zero-Copy Proof)`, `Elapsed: <2.0s`. Step 3 prints `Reverted: Marcus Vance`, `Read back via patient360: Marcus Vance`, and exits 0.

### E-5 [F] [CLI] Demo script invalid patient ID validation
- **Type**: CLI
- **Steps**:
  1. Execute demo script with an invalid patient ID:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/pipeline/demo_zero_copy_edit.py --apply --patient-id "INVALID_ID_123"
     ```
- **Expected**: Exits with return code 1, prints error `ValueError: Invalid patient ID format: INVALID_ID_123. Must match ^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$`, and performs no data modification.

### E-6 [S] [automated] SQL injection resistance in demo edit parameters
- **Type**: automated
- **Steps**:
  1. Run unit test in `rayfin-imaging/pipeline/tests/test_demo_zero_copy_edit.py` targeting SQL injection vectors:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest rayfin-imaging/pipeline/tests/test_demo_zero_copy_edit.py -k test_sql_injection_defense
     ```
- **Expected**: Test passes; input strings containing `' OR '1'='1` or `; DROP TABLE` are rejected during parameter sanitization before SQL query dispatch.

### E-7 [R] [browser] Data Map existing schematic and inventories regression check
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/data`.
  2. Verify the three-column schematic (Silos → patient360 → Rayfin app/Browser) is intact.
  3. Verify the "What each silo holds" table displays row counts and byte totals for clinical, genomics, and imaging silos.
- **Expected**: All existing schematic cards and table rows render without JavaScript errors or missing styles.
- **Evidence**: `specs/tickets/003-zero-copy-proof/evidence/E-7.png`

### E-8 [Q] [automated] Code quality, lint check, and bundle size audit
- **Type**: automated
- **Steps**:
  1. Verify zero new external npm dependencies were added to `package.json`:
     ```bash
     git diff origin/main -- rayfin-imaging/package.json | grep '^[+] ' || true
     ```
  2. Verify TypeScript type checking succeeds cleanly:
     ```bash
     cd rayfin-imaging && ./node_modules/.bin/tsc -b
     ```
- **Expected**: No new npm dependencies introduced; TypeScript exits 0 with zero diagnostics.

## Edge case checks
### E-9 [F] [browser] Missing shortcut list graceful error handling
- **Type**: browser
- **Steps**:
  1. Mock `getDataMap` returning `patient360.error = "Failed to fetch Fabric shortcuts"`.
  2. Open `http://localhost:<port>/data`.
- **Expected**: Page renders an informative alert banner: `Shortcut list unavailable: Failed to fetch Fabric shortcuts`, while preserving the rest of the silo inventory tables without crashing.
- **Evidence**: `specs/tickets/003-zero-copy-proof/evidence/E-9.png`

### E-10 [F] [CLI] Idempotent revert when already at baseline
- **Type**: CLI
- **Steps**:
  1. Ensure patient record is at baseline `Marcus Vance`.
  2. Run revert command again:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/pipeline/demo_zero_copy_edit.py --revert
     ```
- **Expected**: Exits 0, prints `Record is already at baseline value 'Marcus Vance'. No changes needed.`

## Regression checks
- The `/patients` route loads without console errors.
- The `/wardflow` route displays cardiology patient records without query regression.
- The `getDataMap` API continues to return all existing silo metadata (`workspace`, `patient360`, `silos`, `provenance`).

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-1, E-2 |
| FR-2        | E-1 |
| FR-3        | E-1, E-7 |
| FR-4        | E-3, E-4 |
| FR-5        | E-3 |
| FR-6        | E-4 |
| FR-7        | E-4, E-10 |
| FR-8        | E-3, E-4, E-10 |
| NFR-1       | E-2 |
| NFR-2       | E-4 |
| NFR-3       | E-5, E-6 |

## Definition of done
- [ ] All automated checks pass (A-1, A-2)
- [ ] All acceptance checks E-1…E-8 pass
- [ ] All edge case checks E-9…E-10 pass
- [ ] No items from "Out of scope" were built

## Not covered
- User session authentication expiry: Local development mode operates without an authenticated user session; session lifecycle is handled by the Fabric hosted platform container.
- Payment/billing processing: Rayfin does not handle financial transactions or payment processing.

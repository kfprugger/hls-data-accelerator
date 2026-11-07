# 007: Standards View (FHIR R4 & DICOM to HDS Lineage): Evaluation

## Setup
1. Ensure node dependencies and local tables are installed per `.claude/project.md`:
   ```bash
   cd rayfin-imaging && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund && cd rayfin/functions && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund
   ```
2. Build local DuckDB data (if not already built by ticket 001):
   ```bash
   /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/pipeline/build_local_tables.py
   ```
3. Start the Rayfin app in local mode on assigned port `<port>`:
   ```bash
   cd rayfin-imaging && ./node_modules/.bin/vite --mode localdata --port <port> --strictPort
   ```
4. Verify the dev server responds:
   ```bash
   curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/
   ```
   Must output `200`.

## Automated checks
- `cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build` exits 0.
- `cd rayfin-imaging && ./node_modules/.bin/vitest run && cd ../orchestrator && /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` passes, including new unit tests for `getStandardsMapping`.

## Acceptance checks

### E-1 [U]: Standards page navigation and FHIR R4 lineage display (covers FR-1, FR-2, FR-3)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/`.
  2. Click the navigation link `Standards (FHIR & DICOM)` in the top shell header.
  3. Verify the browser navigates to `http://localhost:<port>/standards`.
  4. Confirm the patient selector displays `TCGA-G6-A8L6 (Marcus Vance)` as selected.
  5. Under the active `FHIR R4 Clinical Standards` tab, locate the left JSON viewer and the right Delta Table viewer.
  6. Save screenshot to `specs/tickets/007-standards-view/evidence/E-1.png`.
- **Expected**:
  - The left pane renders formatted FHIR R4 JSON containing `"resourceType": "Patient"`, `"text": "Marcus Vance"`, and `"resourceType": "Condition"`.
  - The right pane renders Delta table rows from `clinical_lakehouse.dbo.patient` showing column `display_name` with value `Marcus Vance` and `clinical_lakehouse.dbo.diagnoses` showing `primary_diagnosis` with value `Clear cell renal cell carcinoma`.
  - Mapping badges visually highlight the transition from FHIR attribute to Delta column.

### E-2 [U]: DICOM key tags to imaging Delta table lineage display (covers FR-2, FR-4)
- **Type**: browser
- **Steps**:
  1. On `http://localhost:<port>/standards`, click the tab `DICOM Imaging Standards`.
  2. Locate the left DICOM Tag Dataset pane and right Imaging Delta Tables pane.
  3. Save screenshot to `specs/tickets/007-standards-view/evidence/E-2.png`.
- **Expected**:
  - Left pane displays DICOM tag rows including `(0010,0020) PatientID: TCGA-G6-A8L6`, `(0020,000D) StudyInstanceUID`, and `(0008,0060) Modality: CT`.
  - Right pane renders Delta table rows for `imaging_lakehouse.dbo.radiology_study` and `imaging_lakehouse.dbo.radiology_series`.
  - Mapped columns (`study_uid`, `series_uid`, `modality`, `slice_thickness_mm`, `kvp`) match the DICOM header values.

### E-3 [S]: Security validation on patient ID input (covers FR-5, S)
- **Type**: API
- **Steps**:
  1. Issue a request with an invalid patient ID containing special characters:
     ```bash
     curl -s -w "\nHTTP_STATUS:%{http_code}" "http://localhost:<port>/local-api/getStandardsMapping?patientId=TCGA-INVALID'%20OR%201=1--"
     ```
- **Expected**:
  - The server rejects the request with HTTP status `400` or `500` containing JSON `{"error":"Invalid patient id"}`.
  - The server does not execute an unescaped DuckDB query or expose database internal stack traces.

### E-4 [F]: Fallback state for non-existent patient ID (covers FR-2, Edge cases)
- **Type**: browser
- **Steps**:
  1. Navigate directly to `http://localhost:<port>/standards?patientId=TCGA-ZZ-9999`.
  2. Save screenshot to `specs/tickets/007-standards-view/evidence/E-4.png`.
- **Expected**:
  - The page displays a user-friendly notice: `Patient not found in standards catalog`.
  - A fallback button `Reset to Marcus Vance` is displayed; clicking it reloads `TCGA-G6-A8L6` data without crashing the React application.

### E-5 [Q]: Responsive layout and keyboard accessibility check (covers NFR-1, NFR-3, NFR-4)
- **Type**: browser
- **Steps**:
  1. Set viewport to 1280x800.
  2. Measure initial data load completion time for `/standards` using `performance.getEntriesByName`.
  3. Set viewport to 360x740.
  4. Check for horizontal overflow using `document.documentElement.scrollWidth > document.documentElement.clientWidth`.
  5. Press Tab key repeatedly to navigate from the navigation bar into the patient selector and view switcher tabs.
- **Expected**:
  - Data load completes in under 800 ms.
  - At 360 px width, panes stack vertically and horizontal overflow evaluates to `false` (no horizontal scrollbar).
  - Tab navigation displays visible focus indicators (`focus-visible`) on all interactive controls.

### E-6 [D]: Split-pane design fidelity comparison (covers NFR-3, D)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/standards` at 1280x900 viewport.
  2. Save full-page screenshot to `specs/tickets/007-standards-view/evidence/E-6-desktop.png`.
  3. Resize viewport to 360x740.
  4. Save full-page screenshot to `specs/tickets/007-standards-view/evidence/E-6-mobile.png`.
- **Expected**:
  - Desktop screenshot demonstrates a clean 50/50 split pane with dark code block theme for JSON/DICOM tags and clinical table typography matching the Rayfin theme.
  - Mobile screenshot demonstrates stacked cards with zero horizontal clipping.

### E-7 [CLI]: Standalone verification CLI script execution (covers FR-6)
- **Type**: CLI
- **Steps**:
  1. Run the verification script in dry-run mode against the local or target workspace:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/scripts/verify_standards_view.py --patient-id TCGA-G6-A8L6 --dry-run
     ```
- **Expected**:
  - Process exits with code `0`.
  - Output prints JSON with verification results confirming required columns (`patient_id`, `display_name`, `primary_diagnosis`, `study_uid`, `series_uid`) are verified.

## Edge case checks

### E-8 [F]: Patient with missing radiology study (covers FR-4, Edge cases)
- **Type**: browser
- **Steps**:
  1. From the patient selector dropdown, select a patient configured without radiology volumes (or pass `?patientId=TCGA-02-0001` if applicable).
  2. Switch to the `DICOM Imaging Standards` tab.
  3. Save screenshot to `specs/tickets/007-standards-view/evidence/E-8.png`.
- **Expected**:
  - The DICOM panel renders a clear empty state: `No imaging study available for this subject in imaging_lakehouse`.
  - The FHIR R4 clinical panel remains fully functional.

## Regression checks

### R-1 [R]: Core Patient 360 flow integrity
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/patients`.
  2. Select `TCGA-G6-A8L6` (Marcus Vance).
  3. Click the `Genomics` tab.
- **Expected**:
  - Patient header displays Marcus Vance.
  - The Genomics tab lists driver gene `VHL` without regression.

### R-2 [R]: Data Map silo view integrity
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/data`.
- **Expected**:
  - The data map shows `clinical_lakehouse`, `genomics_lakehouse`, `imaging_lakehouse`, and the `patient360` shortcuts.

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-1 |
| FR-2        | E-1, E-2, E-4 |
| FR-3        | E-1 |
| FR-4        | E-2, E-8 |
| FR-5        | E-1, E-3 |
| FR-6        | E-7 |
| NFR-1       | E-5 |
| NFR-2       | E-1 |
| NFR-3       | E-5, E-6 |
| NFR-4       | E-5 |

## Not covered
- **Authentication & session expiry**: Local mode does not run an authentication provider; auth redirects are covered in integration environments by ticket 006.
- **Concurrent write races**: The `/standards` view is strictly read-only; no write endpoints or data mutation concurrency apply.
- **De-identification obfuscation**: Masking researcher views is specifically owned and evaluated by ticket 006 (`006-phi-persona-views`).

## Definition of done
- [ ] All automated checks pass
- [ ] All acceptance checks E-1…E-7 pass
- [ ] Edge case check E-8 passes
- [ ] Regression checks R-1 and R-2 pass
- [ ] No items from "Out of scope" were built

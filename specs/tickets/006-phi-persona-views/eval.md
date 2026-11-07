# 006: OneLake Security PHI vs Researcher Persona Views, Server-Side Masking, and Entra Test Identity: Evaluation

## Setup
1. Ensure the orchestrator virtual environment is available:
   `/Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python --version`
2. Configure live Fabric environment variables (for live CLI checks):
   ```bash
   export AZURE_CONFIG_DIR="$HOME/.azure-isolated/JBATL"
   export HLS_BIND_INTERFACE="en0"
   export FABRIC_WORKSPACE_NAME="med-1103a"
   ```
3. Start the Rayfin development server in local data mode on port `<port>`:
   ```bash
   cd rayfin-imaging && ./node_modules/.bin/vite --mode localdata --port <port> --strictPort
   ```
4. Confirm server readiness:
   `curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/` returns 200.

## Automated checks
- Build check:
  `cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build` exits 0
- Unit and integration tests:
  `cd rayfin-imaging && ./node_modules/.bin/vitest run && cd ../orchestrator && /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` passes, including new tests in `orchestrator/tests/test_phi_persona.py` and `rayfin-imaging/src/components/PersonaBanner.test.tsx`

## Acceptance checks

### E-1 [U] PersonaBanner display and interactive persona toggling in local mode (covers FR-5, FR-6)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/patients` in the browser.
  2. Verify the `PersonaBanner` appears across the top of the application shell.
  3. Verify default state shows `Nurse Persona (Full Clinical PHI)` with a green badge and user label `joey@jbatl.dev`.
  4. Click the "Switch to Researcher Persona" toggle button in the banner.
  5. Verify the banner transitions to `Researcher Persona (De-identified - HIPAA Safe)` with a purple badge and user label `researcher-demo@jbatl.dev`.
  6. Save screenshot to `specs/tickets/006-phi-persona-views/evidence/E-1.png`.
- **Expected**: Banner reflects state change instantly; active persona badge changes color and label.

### E-2 [U] Nurse persona displays full identified patient profile (covers FR-4, FR-5)
- **Type**: browser
- **Steps**:
  1. Ensure Nurse Persona is active on `http://localhost:<port>/patients`.
  2. Select patient `TCGA-G6-A8L6` from the list.
  3. Verify the patient detail header displays `"Marcus Vance"`.
  4. Verify the person description line displays `"55-year-old man at diagnosis · Black or African American · United States"`.
  5. Save screenshot to `specs/tickets/006-phi-persona-views/evidence/E-2.png`.
- **Expected**: Real patient name Marcus Vance is visible in the UI.

### E-3 [S] Active attack check: Researcher identity querying identified table is denied at storage layer (covers FR-2, FR-4)
- **Type**: CLI
- **Steps**:
  1. Execute security attack simulation querying the identified patient table using the researcher identity / role:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest orchestrator/tests/test_phi_persona.py -k test_researcher_denied_on_identified_patient_table
     ```
  2. In the test, authenticate as `researcher-demo@jbatl.dev` (or evaluate the OneLake data access role policy against `Tables/patient`).
  3. Attempt an explicit query: `SELECT TOP 5 * FROM dbo.patient`.
- **Expected**: Query fails with HTTP 403 / SQL error `Cannot find the object "dbo.patient" because it does not exist or you do not have permissions` or OneLake `AccessDeniedOnPath: Tables/patient`. Access is physically denied at the storage/SQL layer.

### E-4 [S] Server-side name masking proof: inspecting network JSON payload confirms Marcus Vance never transmitted (covers FR-1, FR-4, NFR-1)
- **Type**: browser
- **Steps**:
  1. In the browser, toggle to `Researcher Persona`.
  2. Open DevTools Network tab and filter for `/local-api/getCohort` or `/local-api/getPatient`.
  3. Navigate to `http://localhost:<port>/p/TCGA-G6-A8L6`.
  4. Verify the UI renders `TCGA-G6-A8L6` as the patient name instead of `Marcus Vance`.
  5. Inspect the raw HTTP response body of the `getPatient` API call:
     - Search response text for `"Marcus Vance"` or `"Marcus"`.
     - Confirm 0 occurrences of the string `"Marcus Vance"` in the network payload.
     - Confirm `display_name` is `"TCGA-G6-A8L6"`.
  6. Save screenshot of the response payload inspection to `specs/tickets/006-phi-persona-views/evidence/E-4.png`.
- **Expected**: Zero instances of Marcus Vance exist in the serialized network response; masking is performed server-side before transmission.

### E-5 [S] Credential hygiene: password never written to disk, git, or log files (covers FR-3, NFR-2)
- **Type**: CLI
- **Steps**:
  1. Run the researcher provisioning CLI in dry-run mode, capturing all logs:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python scripts/manage_researcher_persona.py --dry-run > /tmp/researcher_stdout.log 2> /tmp/researcher_stderr.log
     ```
  2. Search entire worktree for test user password patterns or accidental leaks:
     ```bash
     grep -rnEi "researcher-demo.*password|password.*=.*[A-Za-z0-9!@#$]{8,}" scripts/ rayfin-imaging/ orchestrator/ .env* || true
     ```
- **Expected**: Command exits 0 and grep produces 0 matches. Password is generated ephemerally, never written to disk or logs.

### E-6 [S] Entra test user lifecycle CLI idempotent create and delete (covers FR-3, FR-7)
- **Type**: CLI
- **Steps**:
  1. Run the CLI tool with `--dry-run` to inspect lifecycle actions:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python scripts/manage_researcher_persona.py --dry-run
     ```
  2. Verify output details planned idempotent actions:
     - Check Entra user `researcher-demo@jbatl.dev`
     - Check OneLake data access role `ClinicalResearcherRole`
     - Plan assignment to `Tables/patient_deidentified`
  3. Verify `--delete` mode exists and validates cleanly in dry-run:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python scripts/manage_researcher_persona.py --delete --dry-run
     ```
- **Expected**: Both commands exit 0 with clean structured validation output.

### E-7 [Q] Persona switch re-render latency under 200 ms without page reload (covers FR-5, FR-6)
- **Type**: browser
- **Steps**:
  1. On `http://localhost:<port>/patients`, measure performance when toggling between Nurse and Researcher personas:
     ```javascript
     const t0 = performance.now();
     document.querySelector('[data-testid="persona-toggle"]').click();
     const elapsed = performance.now() - t0;
     console.log(`Persona toggle took ${elapsed}ms`);
     ```
- **Expected**: Elapsed execution time is $< 200\text{ ms}$; the page updates in-place without triggering a browser window reload.

### E-8 [D] Responsive layout of PersonaBanner at 1280 px and 360 px (covers NFR-3)
- **Type**: browser
- **Steps**:
  1. View `http://localhost:<port>/` at 1280 px $\times$ 800 px.
  2. Verify `PersonaBanner` spans the full viewport width with user email, badge, and toggle aligned.
  3. Save screenshot to `specs/tickets/006-phi-persona-views/evidence/E-8-1280px.png`.
  4. Resize viewport to 360 px $\times$ 740 px.
  5. Verify elements stack gracefully: identity badge wraps cleanly, toggle button remains accessible.
  6. Confirm `document.documentElement.scrollWidth <= window.innerWidth`.
  7. Save screenshot to `specs/tickets/006-phi-persona-views/evidence/E-8-360px.png`.
- **Expected**: Zero horizontal scrollbar at 360 px; text remains legible with no overlapping labels.

## Edge case checks

### E-9 [F] Handling of unauthorized direct navigation or invalid persona role (covers FR-4, Edge cases)
- **Type**: browser
- **Steps**:
  1. In researcher persona, navigate directly to an identified patient route with invalid query parameters: `http://localhost:<port>/p/TCGA-G6-A8L6?view=identified_phi`.
  2. Verify the application ignores the unpermitted view parameter, enforces the de-identified server response, and displays the de-identified patient header.
- **Expected**: Client does not crash, does not display unmasked PHI, and remains bounded by researcher security tier.

## Regression checks

### R-1 [R] Oncology genomics and WardFlow cardiology features remain functional across persona switches
- **Type**: browser
- **Steps**:
  1. In researcher persona, open `http://localhost:<port>/wardflow`.
  2. Confirm cohort table and deterioration scores calculate properly.
  3. Open `http://localhost:<port>/volumes` and confirm 3D/4D imaging volumes load without errors.
- **Expected**: Core clinical calculations and imaging features continue working normally in de-identified mode.

### R-2 [R] Data map shortcuts and volumes catalog remain visible
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/data`.
  2. Verify `patient360` shortcuts and silo links display correctly.
- **Expected**: Data map visual renders completely with no missing nodes.

## Traceability
| Requirement | Evals |
|---|---|
| FR-1 (De-identified Delta table) | E-4 |
| FR-2 (OneLake data access roles) | E-3, E-6 |
| FR-3 (Entra test user CLI) | E-5, E-6 |
| FR-4 (Server-side masking) | E-2, E-3, E-4, E-9 |
| FR-5 (Persona banner component) | E-1, E-2, E-8 |
| FR-6 (Local mode parity) | E-1, E-4, E-7 |
| FR-7 (Fresh deployments) | E-6 |
| NFR-1 (Security / Zero PHI leak) | E-3, E-4 |
| NFR-2 (Credential hygiene) | E-5 |
| NFR-3 (Responsive layout) | E-8 |

## Definition of done
- [ ] All automated checks pass (TypeScript compile, Vite local build, Vitest, Python unittests)
- [ ] All acceptance checks E-1…E-9 pass
- [ ] High-risk checks verified (at least 3 [S] checks: E-3, E-4, E-5, E-6; active attack check: E-3)
- [ ] Screenshots captured in `specs/tickets/006-phi-persona-views/evidence/`
- [ ] No items from "Out of scope" were built

## Not covered
- **Payments / Billing**: Not applicable; clinical demo data only.
- **Biometric / SSO MFA ceremony**: Test account `researcher-demo@jbatl.dev` is configured for demonstration authentication without requiring external hardware tokens.
- **Multi-region geo-replication**: The demo environment is contained within a single Azure region (`westus2`) and tenant.
- **B2B external guest invitations**: Excluded from scope; researcher identity is created directly within the JBATL demonstration tenant.

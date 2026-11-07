# 006: OneLake Security PHI vs Researcher Persona Views, Server-Side Masking, and Entra Test Identity

**Status:** ready

| **Risk** | High: Unmasked PHI data breach to unauthorized researcher persona or OneLake role bypass |

## Summary
Implements OneLake security data access roles on the `patient360` Lakehouse and `clinical_lakehouse`, creating a derived de-identified clinical table (`patient_deidentified`) where names and direct identifiers are masked server-side. Provides an idempotent CLI script to provision/deprovision an Entra test user `researcher-demo@jbatl.dev` without persisting passwords to disk, and mounts an interactive `PersonaBanner` in Rayfin showing the active persona and security tier with a local-mode demonstration toggle.

## Why
Hospital compliance officers and HIPAA security architects require verifiable server-side data boundaries before granting researchers access to clinical data assets. Proving that an unauthorized researcher persona is rejected by OneLake security when attempting to query identified tables—and that de-identified views mask PHI at the storage layer rather than via superficial UI filters—provides incontrovertible proof of Fabric's enterprise governance.

## User stories
- As a clinical nurse, I want full identified access to patient names and clinical records, so that I can provide direct bedside patient care.
- As an oncology researcher, I want to query clinical cohorts and molecular driver data without receiving unmasked patient names or direct identifiers over the wire, so that my research complies with HIPAA de-identification rules.
- As a demonstration presenter, I want to switch between Nurse and Researcher views using a visible persona banner, so that healthcare IT architects immediately see OneLake security enforcement in action.

## Functional requirements
- **FR-1**: Script `rayfin-imaging/pipeline/seed_deidentified_clinical.py` must derive a `patient_deidentified` Delta table in `clinical_lakehouse` and register a OneLake shortcut into `patient360`. In `patient_deidentified`, `display_name` is replaced with `patient_id` (e.g. "TCGA-G6-A8L6" instead of "Marcus Vance"), `race` and `country` are retained, but specific addresses are stripped, birth dates are truncated to year of diagnosis, and direct contact details are removed.
- **FR-2**: OneLake security data access roles must be created and bound via `PUT /v1/workspaces/{wsId}/items/{itemId}/dataAccessRoles`:
  - `ClinicalNurseRole`: Permits Read on all paths (`Tables/*`), assigned to demonstration administrators and nurses (`joey@jbatl.dev`).
  - `ClinicalResearcherRole`: Permits Read on `Tables/patient_deidentified`, `Tables/diagnosis`, `Tables/treatment`, and `Tables/biomarker_test`, but explicitly omits or denies access to `Tables/patient`. Assigned to `researcher-demo@jbatl.dev`.
- **FR-3**: Standalone Python CLI script `scripts/manage_researcher_persona.py` must idempotently manage the test user `researcher-demo@jbatl.dev`:
  - `--create`: Checks if `researcher-demo@jbatl.dev` exists in Entra ID; if not, creates the user, assigns `ClinicalResearcherRole` in OneLake, and displays a temporary high-entropy password once to stdout (with explicit warning that it is never written to disk, config files, or git).
  - `--delete`: Removes the Entra test user and revokes OneLake role assignments cleanly.
  - `--verify`: Queries Graph API and Fabric REST to verify role assignment and account state without disclosing passwords.
  - `--dry-run`: Reports planned Entra and Fabric operations without making live changes.
- **FR-4**: The Rayfin backend UDFs (`getCohort`, `getPatient`) in `function_app.ts` must query the table matching the caller's persona role. For the researcher persona, queries target `dbo.patient_deidentified` or execute under the researcher role; network inspection must verify that `Marcus Vance` and other patient names never appear in the JSON payload sent across the network.
- **FR-5**: Rayfin UI must mount a `PersonaBanner` in `src/components/AppShell.tsx`:
  - Displays active identity: `joey@jbatl.dev` (Nurse Persona) vs `researcher-demo@jbatl.dev` (Researcher Persona).
  - Displays security tier badge: Green `Full Clinical PHI (Identified)` vs Purple `De-identified Research Tier (HIPAA Safe)`.
  - In local mode (`LOCAL_DATA = true`), includes a 1-click toggle button allowing presenters to flip between Nurse and Researcher personas without logging out.
- **FR-6**: In local mode (`LOCAL_DATA = true`), `local/api.ts` must expose a `patient_deidentified` DuckDB view over `work/tables/clinical/patient_deidentified.parquet`. When the researcher persona is active, `getCohort` and `getPatient` return masked `display_name` values and scrubbed identifiers matching live server-side behavior.
- **FR-7 (Fresh deployments)**: Standalone CLI script `scripts/manage_researcher_persona.py` must be completely idempotent, dry-run by default, and support full `--cleanup` / `--delete` mode. Ticket 012 will call this script from `AddonRunner`.

## Non-functional requirements
- **NFR-1 (Security / Zero PHI Leak)**: 0% of unmasked names or raw identifiers may be present in the network response when querying under the researcher persona.
- **NFR-2 (Credential Hygiene)**: Test account passwords must never be stored in files, environment variables, or committed to git.
- **NFR-3 (Responsive layout)**: `PersonaBanner` must render responsively at 1280 px and 360 px viewports without breaking page layout or causing horizontal scroll.

## Edge cases & error handling
- **Researcher queries identified table directly**: Storage/SQL endpoint returns HTTP 403 Forbidden / `PermissionDenied` error; backend converts this to an explicit clinical access denied notice.
- **Entra user already exists**: Running `--create` when `researcher-demo@jbatl.dev` already exists updates role assignments without failing or resetting the password.
- **OneLake role synchronization latency**: If Fabric takes up to 30 seconds to propagate role bindings, the CLI verification retries with exponential backoff before reporting status.
- **Switching personas mid-session in UI**: In local mode, toggling the persona immediately invalidates React Query / cohort cache and re-fetches patient views without full page reload.

## Out of scope
- Modifying `orchestrator/activities/addons.py` or `Deploy-All.ps1` (owned by ticket 012).
- Provisioning multi-tenant B2B guest identities; only the single Entra test user `researcher-demo@jbatl.dev` within `JBATL` tenant is in scope.
- Column-level masking on genomic sequencing BAM/VCF raw files.

## Affected areas
- `scripts/manage_researcher_persona.py`: CLI script for Entra user creation, deletion, OneLake role binding, and verification.
- `rayfin-imaging/pipeline/seed_deidentified_clinical.py`: Script to generate `patient_deidentified` Delta table and OneLake shortcuts.
- `rayfin-imaging/rayfin/functions/src/function_app.ts`: Update UDFs (`getCohort`, `getPatient`) to route queries by caller persona.
- `rayfin-imaging/rayfin/functions/src/types.ts`: Update schema with persona metadata and de-identified flags.
- `rayfin-imaging/local/api.ts`: Add `patient_deidentified` DuckDB view and persona toggle state.
- `rayfin-imaging/local/plugin.ts`: Add `/local-api/persona` state handler.
- `rayfin-imaging/src/components/PersonaBanner.tsx`: New React persona indicator and toggle banner.
- `rayfin-imaging/src/components/AppShell.tsx`: Mount `PersonaBanner` above main navigation.
- `rayfin-imaging/src/hooks/usePersona.tsx`: Context hook managing active persona.
- `rayfin-imaging/src/lib/api.ts`: Add persona context parameter/header to UDF requests.
- `orchestrator/tests/test_phi_persona.py`: Unit tests for Entra user CLI, OneLake role JSON serialization, and masking rules.
- `rayfin-imaging/src/components/PersonaBanner.test.tsx`: Vitest tests for the persona banner and toggle.

## Do not touch
- `orchestrator/activities/addons.py`: Owned by ticket 012.
- `orchestrator/tests/test_addons.py`: Owned by ticket 012.
- `Deploy-All.ps1`: Owned by ticket 012.

## Dependencies
- `001-local-demo-dataset`: Provides local table infrastructure in `work/tables/`.
- `002-tcga-synthetic-ingest`: Ingests the 15 TCGA patient records into `clinical_lakehouse`.
- Fabric workspace `med-1103a` with Azure CLI authenticated as admin.

## Decisions made
- **Agreed with the user**: OneLake security data access roles on `patient360` (identified vs de-identified tables), de-identified table derived in clinical silo, idempotent Entra CLI for `researcher-demo@jbatl.dev` with delete mode and no stored passwords, and an app persona banner.
- **Decided by the ticket writer**: The de-identified table is named `patient_deidentified` in `clinical_lakehouse` and exposed via shortcut in `patient360`.
- **Decided by the ticket writer**: In local mode, `PersonaBanner` features an interactive toggle switch ("Nurse (Identified)" / "Researcher (De-identified)"), persisting selection to session state so presenters can demonstrate both views instantly without signing in and out.
- **Decided by the ticket writer**: In live mode, persona is determined by Entra claims / token identity (`researcher-demo@jbatl.dev` vs default workspace admin).
- **Decided by the ticket writer**: For Marcus Vance, the de-identified record replaces `display_name: "Marcus Vance"` with `display_name: "TCGA-G6-A8L6"`, removes address fields, and coarsens exact birth date to diagnosis year `1956`.

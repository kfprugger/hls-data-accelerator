# 007: Standards View (FHIR R4 & DICOM to HDS Lineage)

**Status:** done

| **Risk** | Medium: Standards mapping fails to query or parse FHIR/DICOM tables, rendering an unhandled exception or blank screen on /standards during an executive demo. |

## Summary
Adds a dedicated `/standards` route and navigation tab to the Rayfin Fabric web application that renders healthcare data interoperability lineage side-by-side for semi-technical healthcare IT leaders. For a selected cohort subject (default Marcus Vance, `TCGA-G6-A8L6`), the page displays raw clinical standards inputs—a FHIR R4 resource bundle (`Patient` and `Condition` JSON) and key DICOM radiology tags—directly adjacent to the conformed Microsoft Fabric Healthcare Data Solutions (HDS) and imaging Delta table rows they became.

## Why
Healthcare CIOs, CMIOs, and enterprise data architects frequently question how semi-structured HL7/FHIR resources and complex binary DICOM headers are transformed into analytics-ready Delta Lake tables. By presenting the raw standard payload side-by-side with the flattened Delta table records in OneLake, this view proves schema transparency, zero loss of clinical fidelity, and illustrates the automated HDS ingestion pipeline without requiring viewers to inspect raw SQL scripts or pipeline JSON.

## User stories
- As a Healthcare Enterprise Architect, I want to inspect a FHIR R4 Patient and Condition JSON resource side-by-side with the resulting `patient` and `diagnoses` Delta table rows, so that I can verify field-level mapping and semantic transformation accuracy.
- As a PACS Administrator / Imaging Informaticist, I want to view standard DICOM tag attributes (PatientID, StudyInstanceUID, Modality, SliceThickness) next to `radiology_study` and `radiology_series` Delta table rows, so that I can confirm imaging metadata integrity.
- As an IT Leader, I want to switch between cohort patients (such as Marcus Vance `TCGA-G6-A8L6`) to confirm that standard mapping lineage is consistent across multiple oncological disease profiles.

## Functional requirements
- **FR-1**: Route and Navigation. The app must register a new route `/standards` in `rayfin-imaging/src/App.tsx` and an accessible navigation entry in `rayfin-imaging/src/components/AppShell.tsx` labeled `Standards (FHIR & DICOM)`.
- **FR-2**: Standards Page Layout & Patient Selection. The `/standards` page (`rayfin-imaging/src/pages/Standards.tsx`) must provide:
  - A patient selector dropdown populated with the 15 TCGA cohort subjects, defaulting to Marcus Vance (`TCGA-G6-A8L6`).
  - View switcher tabs to toggle between `FHIR R4 Clinical Standards` and `DICOM Imaging Standards`.
  - A synchronized split-pane comparison view with responsive syntax highlighting, copy-to-clipboard buttons, and field-level visual mapping badges.
- **FR-3**: FHIR R4 to Delta Table Lineage View.
  - The left pane must display formatted, collapsible JSON for FHIR R4 `Patient` (e.g. identifier, name, gender, birthDate, address) and `Condition` (e.g. clinicalStatus, verificationStatus, code SNOMED/ICD-10, subject reference, recordedDate).
  - The right pane must display the corresponding conformed Delta table records from `clinical_lakehouse.dbo.patient` and `clinical_lakehouse.dbo.diagnoses`.
  - Visual badge indicators must explicitly connect FHIR paths to Delta table columns (e.g., `Patient.gender` -> `clinical.patient.sex`, `Patient.name[0].text` -> `clinical.patient.display_name`, `Condition.code.coding[0].display` -> `clinical.diagnoses.primary_diagnosis`, `Condition.code.coding[0].code` -> `clinical.diagnoses.icd10`).
- **FR-4**: DICOM to Imaging Delta Table Lineage View.
  - The left pane must display formatted key DICOM dataset tags with standard hex codes and names: `(0010,0020) PatientID`, `(0020,000D) StudyInstanceUID`, `(0020,000E) SeriesInstanceUID`, `(0008,0060) Modality`, `(0008,0020) StudyDate`, `(0008,0070) Manufacturer`, `(0008,1090) ManufacturerModelName`, `(0018,0050) SliceThickness`, `(0018,0060) KVP`, `(0018,0010) ContrastBolusAgent`, `(0018,0015) BodyPartExamined`, and `(0008,103E) SeriesDescription`.
  - The right pane must display the corresponding records from `imaging_lakehouse.dbo.radiology_study` and `imaging_lakehouse.dbo.radiology_series`, highlighting mapped columns (`study_uid`, `series_uid`, `modality`, `manufacturer`, `model`, `slice_thickness_mm`, `kvp`, `contrast`, `body_part`, `description`, `images`, `dims`, `spacing_mm`, `volume_path`).
- **FR-5**: Backend Data Function and Local API.
  - In Fabric mode, the backend must expose `getStandardsMapping(patientId: string)` in `rayfin-imaging/rayfin/functions/src/function_app.ts` querying Gold SQL / Lakehouse endpoints with `PATIENT_ID` regex validation.
  - In local mode, `rayfin-imaging/local/api.ts` and `local/plugin.ts` must implement `/local-api/getStandardsMapping` querying DuckDB parquet files in `work/tables/clinical/*.parquet` and `work/tables/imaging/*.parquet` combined with the deterministic Synthea FHIR schema generator.
  - Types must be declared in `rayfin-imaging/rayfin/functions/src/types.ts` and client helper `fetchStandardsMapping(patientId: string)` in `rayfin-imaging/src/lib/api.ts`.
- **FR-6**: Fresh Deployments CLI Script. The builder must create a standalone, idempotent Python CLI script `rayfin-imaging/scripts/verify_standards_view.py`.
  - Accepts CLI arguments: `--workspace` (Fabric workspace name or ID), `--patient-id` (default `TCGA-G6-A8L6`), `--dry-run` (default true), and `--cleanup`.
  - Uses `AZURE_CONFIG_DIR` and `HLS_BIND_INTERFACE=en0` for isolation.
  - Queries the target Fabric Lakehouse or local DuckDB tables to verify that the required FHIR and DICOM columns exist and contain valid mapping data for the cohort.
  - In `--cleanup` mode, removes any transient verification artifacts without deleting underlying clinical or imaging tables.
  - Exits 0 on successful validation. Ticket 012 will wire this script into `AddonRunner`.

## Non-functional requirements
- **NFR-1**: Standards mapping data payload must load and render in under 800 ms in local mode and under 2000 ms over Fabric SQL endpoints.
- **NFR-2**: Syntax highlighted JSON viewer must support collapsing, expanding, and copying clean JSON to clipboard.
- **NFR-3**: Fluid responsive layout: side-by-side split panels on desktop (1280 px) and vertically stacked panels with no horizontal overflow at mobile (360 px).
- **NFR-4**: Full keyboard navigation across patient selector, view tabs, and collapsible JSON trees with WCAG 2.1 AA accessible contrast ratios and ARIA landmark regions.

## Edge cases & error handling
- Non-existent or invalid patient ID in route: Displays an inline warning banner ("Patient not found in standards catalog") with a button to reset to Marcus Vance (`TCGA-G6-A8L6`).
- Patient with no radiology study: Left DICOM pane displays "No imaging study available for subject" empty state while retaining FHIR clinical tabs.
- Lakehouse query failure or network timeout: Client displays an error state with an explicit retry button; requests enforce an explicit 90-second timeout.
- Malformed patient ID parameter: API returns 400 Bad Request and enforces regex `^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$`, preventing SQL injection or path traversal.

## Out of scope
- Editing, modifying, or creating FHIR resources or DICOM tags in the browser.
- Direct binary PACS WADO-RS downloading of raw DICOM `.dcm` files from `/standards`.
- Editing `orchestrator/activities/addons.py`, `orchestrator/tests/test_addons.py`, or `Deploy-All.ps1` (strictly owned by Ticket 012).

## Affected areas
- `rayfin-imaging/src/pages/Standards.tsx`: new standards lineage page.
- `rayfin-imaging/src/components/standards/FhirMappingCard.tsx`: new FHIR R4 JSON vs table viewer component.
- `rayfin-imaging/src/components/standards/DicomMappingCard.tsx`: new DICOM dataset tags vs table viewer component.
- `rayfin-imaging/src/App.tsx`: add `/standards` route.
- `rayfin-imaging/src/components/AppShell.tsx`: add `Standards (FHIR & DICOM)` navigation tab.
- `rayfin-imaging/src/lib/api.ts`: add `fetchStandardsMapping` client function.
- `rayfin-imaging/rayfin/functions/src/types.ts`: add `getStandardsMapping` schema.
- `rayfin-imaging/rayfin/functions/src/function_app.ts`: add `getStandardsMapping` UDF.
- `rayfin-imaging/local/api.ts`: add `getStandardsMapping` DuckDB implementation.
- `rayfin-imaging/local/plugin.ts`: register `/local-api/getStandardsMapping` endpoint.
- `rayfin-imaging/scripts/verify_standards_view.py`: new standalone verification CLI script.

## Do not touch
- `orchestrator/activities/addons.py`
- `orchestrator/tests/test_addons.py`
- `Deploy-All.ps1`
- `rayfin-imaging/src/components/patient/*`
- `rayfin-imaging/src/pages/WardFlow.tsx`

## Dependencies
- Waits for `001-local-demo-dataset` (provides the local DuckDB parquet tables in `work/tables/clinical` and `work/tables/imaging`).
- Runs alongside `003-zero-copy-proof`, `005-data-agent-qa`, `006-phi-persona-views`, `008-imaging-hero`, `010-databricks-interop`.

## Decisions made
- **Agreed with the user**: Page lives at `/standards`, shows FHIR R4 Patient/Condition JSON next to HDS rows, and DICOM study key tags next to imaging rows.
- **Decided by the ticket writer**:
  - Unified into a single backend Rayfin function `getStandardsMapping(patientId)` to avoid multi-round client queries.
  - Marcus Vance (`TCGA-G6-A8L6`) is set as the default patient to align with the core demo storyline.
  - Interactive hover state connects the JSON field path to the corresponding table column for instant visual comprehension.
  - Standalone script `rayfin-imaging/scripts/verify_standards_view.py` defaults to read-only `--dry-run` verification to avoid unintended state changes.

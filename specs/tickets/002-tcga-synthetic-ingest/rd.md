# 002: TCGA Cohort Synthetic FHIR, Device, and Claim Ingestion

**Status:** ready

| **Risk** | High: Accidental overwrite of clinical FHIR records, credential exposure, or data leakage of synthetic identifiers into non-demo pipelines |

## Summary
Implements a standalone CLI tool `synthea/seed_tcga_cohort.py` (`plan` default dry-run, `apply`, `delete`) that ingests the 15 TCGA demo patients through the HLS synthetic healthcare pipeline. Builds FHIR R4 resources (`Patient`, `Condition`, `MedicationRequest`, `Observation`, `Coverage`, `Device`, and `Basic` device associations) using deterministic UUIDv5 `resource_id` identifiers and the `synthetic-demo-enrichment` provenance tag. Strictly refuses to overwrite any resource lacking the synthetic tag, removes only tagged resources on deletion, pairs Marcus Vance (`TCGA-G6-A8L6`) to Masimo pulse oximeter `MASIMO-RADIUS7-0001`, and coordinates propagation into `healthcare1_reporting_gold`, Eventhouse telemetry, and claims.

## Why
In Microsoft Fabric healthcare demonstrations for semi-technical healthcare IT leaders (CIOs, CMIOs, enterprise architects), evaluators expect to see longitudinal patient records connected end-to-end: from clinical EHR (FHIR R4), to real-time bedside IoT monitors (Masimo pulse oximeters), to claims economics and analytical lakehouses, all indexed under identical patient barcodes (e.g. `TCGA-G6-A8L6` Marcus Vance). Currently, Synthea generates generic synthetic subjects, while Rayfin's multi-silo Delta tables contain the 15 TCGA cancer patients. Ingesting the 15 TCGA subjects directly into the Azure Health Data Services (AHDS) FHIR service, pairing Marcus Vance to a Masimo device, and propagating the cohort through HDS Bronze-Silver-Gold pipelines, Eventhouse telemetry, and claims unifies the platform under coherent, verified healthcare identities.

## User stories
- As a healthcare solutions architect, I want the 15 TCGA patients ingested into FHIR R4 with standard identifiers (`TCGA-G6-A8L6`), cancer diagnoses, treatment lines, baseline vitals, and paired Masimo devices, so that live FHIR searches, Fabric Healthcare Data Solutions (HDS) pipelines, and Rayfin UI views query identical clinical records.
- As a healthcare IT security officer, I want synthetic ingestion to strictly refuse overwriting any existing resource that lacks the `synthetic-demo-enrichment` tag, and require `delete` to remove only tagged resources, so that live clinical or non-demo records are never corrupted or removed.
- As a clinical demo presenter, I want Marcus Vance paired deterministically to Masimo device `MASIMO-RADIUS7-0001`, so that live SpO2 alerts and Eventhouse telemetry correspond directly to Marcus Vance in the Rayfin UI.
- As an automated test harness or operations engineer, I want `seed_tcga_cohort.py` to default to a read-only `plan` dry-run, support idempotent re-runs, and never leak Azure CLI tokens or credentials in logs or stdout.

## Functional requirements
- **FR-1**: Standalone CLI script `synthea/seed_tcga_cohort.py` must support three subcommands:
  - `plan` (default): Inspects the target FHIR service, generates the planned FHIR resource bundle in memory, reports exact counts of resources to create or update, and exits 0 without writing data.
  - `apply`: Uploads the generated FHIR transaction bundles to the FHIR service, verifies HTTP 200/201 response status for every entry, and reports success metrics.
  - `delete`: Identifies and removes all resources on the FHIR service that carry the `synthetic-demo-enrichment` tag.
- **FR-2 (FHIR R4 Patient)**: For each of the 15 TCGA patients in `PATIENT_META` (`rayfin-imaging/pipeline/seed_patient360_silos.py`), the script must generate a FHIR R4 `Patient` resource:
  - `identifier`: System `https://gdc.cancer.gov/tcga/barcode`, value: TCGA barcode (e.g. `TCGA-G6-A8L6`).
  - `name`: Family and given names from `PATIENT_META["name"]` (e.g., family `"Vance"`, given `["Marcus"]`).
  - `gender`: `"male"` if sex is `"Male"` else `"female"`.
  - `birthDate`: ISO date string derived from diagnosis year and age (`m["year"] - m["age"]`).
  - `address`: Country `"United States"`.
- **FR-3 (FHIR R4 Condition)**: For each patient, generates primary oncological `Condition` resources:
  - Code: SNOMED CT and ICD-10 (e.g. `m["icd10"]`, display from `CANCER_NAMES[code]`).
  - Clinical status: `active`, verification status: `confirmed`.
  - Subject: `{"reference": f"Patient/{patient_resource_id}"}`.
  - Stage: Staging from `m["stage"]` (e.g. `Stage IV`).
- **FR-4 (FHIR R4 MedicationRequest)**: For each treatment line in `m["treatments"]`:
  - Medication display from treatment agent (e.g. Sunitinib, Axitinib, Bevacizumab for Marcus Vance).
  - Status: `active` if treatment is current, `completed` if prior.
  - Intent: `order`, subject: `{"reference": f"Patient/{patient_resource_id}"}`.
- **FR-5 (FHIR R4 Observation)**: Generates baseline vital signs:
  - Systolic Blood Pressure, Diastolic Blood Pressure, Heart Rate, Body Mass Index (BMI), and baseline SpO2 (96-98%).
  - Category: `vital-signs`, subject: `{"reference": f"Patient/{patient_resource_id}"}`.
- **FR-6 (FHIR R4 Coverage)**: Generates synthetic health insurance `Coverage` resources:
  - Payer: Synthetic Medicare (for age >= 65) or Synthetic Commercial (for age < 65).
  - Beneficiary: `{"reference": f"Patient/{patient_resource_id}"}`.
- **FR-7 (FHIR R4 Device & Basic DeviceAssociation)**:
  - Generates a `Device` resource representing a Masimo Radius-7 pulse oximeter:
    - Identifier: `http://masimo.com/devices`, value: `MASIMO-RADIUS7-0001` for Marcus Vance (`TCGA-G6-A8L6`), and sequential IDs for other cohort patients.
    - Type: Pulse oximeter (SNOMED `706767009`), model: `Radius-7`.
  - Generates a `Basic` resource linking the device to the patient:
    - Code: `device-assoc` (system `http://terminology.hl7.org/CodeSystem/basic-resource-type`).
    - Subject: `{"reference": f"Patient/{patient_resource_id}", "display": "Marcus Vance"}`.
    - Extension: `http://example.org/StructureDefinition/associated-device` referencing `Device/{device_resource_id}`.
    - Conforms to `create-device-association-table.ipynb` and `DevicePayerOntology` expectations.
- **FR-8 (Deterministic IDs & Provenance Tag)**:
  - All resource IDs must be generated via UUIDv5 under namespace `73590e85-86db-46ab-8a17-549b208963cc` (`synthea/enrich_demo_cohort.py` `resource_id`).
  - Every generated resource must include `meta.tag`:
    ```json
    "tag": [{
      "system": "https://brakekat.com/hls/demo-provenance",
      "code": "synthetic-demo-enrichment",
      "display": "Synthetic demo source; not an observed clinical event"
    }]
    ```
- **FR-9 (Safe Overwrite Protection)**:
  - Before applying any upsert (PUT), the script queries the FHIR service for existing resources with the same ID. If a resource exists and lacks the `synthetic-demo-enrichment` tag, the script must abort immediately with error `Refusing to overwrite existing non-synthetic resource: <resourceType>/<id>` and exit with code 3 without modifying any records.
- **FR-10 (Strict Tagged Deletion)**:
  - The `delete` subcommand must verify the `synthetic-demo-enrichment` tag on every candidate resource before issuing a DELETE request. Resources without the tag must be skipped and reported in the cleanup summary.
- **FR-11 (Platform Lineage Settlement)**:
  - FHIR to Gold: FHIR resources reach `healthcare1_reporting_gold` through the HDS pipeline (Azure Health Data Services -> FHIR export to Bronze -> HDS Silver Delta tables -> Phase 5 / `materialize_claims_quality.py` into Gold star-schema tables).
  - Telemetry: Masimo emulator (`emulator.py`) emits readings for `MASIMO-RADIUS7-0001` to Event Hub, ingested by Eventstream into Eventhouse table `TelemetryRaw`, linked to Marcus Vance via `Basic` device-association and the `DeviceAssociation` table.
  - Claims: Claim emulator (`phase-7/claim-emulator/claim_emulator.py`) simulates claim events into `claims_events` in Eventhouse and `fact_claim` in `healthcare1_reporting_gold`.
- **FR-12 (Fresh deployments / Idempotency)**:
  - `synthea/seed_tcga_cohort.py` must be completely standalone and idempotent:
    - Default invocation runs `plan` (read-only count summary).
    - Accepts `--fhir-url` (or `--resource-group` to discover AHDS), `--subscription`, and optional `--as-of`.
    - Ticket 012 will call this script from `AddonRunner`.

## Non-functional requirements
- **NFR-1 (Plan performance)**: `plan` dry-run must compute all resource manifests in under 3.0 seconds.
- **NFR-2 (Batch sizing)**: Ingestion uses standard FHIR transaction bundles with batch sizes between 50 and 200 entries to prevent payload rejection.
- **NFR-3 (Zero credential leakage)**: Bearer tokens, authorization headers, and Azure subscription secrets must never be printed to stdout, stderr, or log files.
- **NFR-4 (Origin validation)**: The HTTP client must validate that requests stay strictly on the configured FHIR origin, refusing cross-domain redirects or credential leaks.

## Edge cases & error handling
- **Untagged existing resource collision**: Aborts immediately with exit code 3, logs the offending resource ID and type, and executes zero updates.
- **FHIR server throttling (429 / 503)**: Automatically retries with exponential backoff (up to 3 retries, maximum 30 seconds backoff) before surfacing an error.
- **SSRF / invalid FHIR URL**: Rejects URLs not matching HTTPS scheme or having non-standard healthcare API domain structures before acquiring credentials.
- **Network timeout**: Every outbound HTTP request to the FHIR service must specify an explicit 60-second timeout.
- **Empty cohort configuration**: If `cohort.json` contains no patients, the script exits with code 1 and an explicit error.

## Out of scope
- Modifying HDS C# or Python binaries in `vendor/microsoft-hds/`.
- Modifying `orchestrator/activities/addons.py` or `Deploy-All.ps1` (owned by ticket 012).
- Synthesizing large binary DICOM files (DICOM series metadata is populated via existing imaging lakehouse tables).
- Sending live telemetry (handled by the existing Masimo emulator and ticket 004).

## Affected areas
- `synthea/seed_tcga_cohort.py`: New standalone CLI tool for cohort planning, ingestion, and deletion.
- `synthea/tests/test_seed_tcga_cohort.py`: Unit tests for resource generation, tag validation, overwrite defense, and CLI options.

## Do not touch
- `synthea/enrich_demo_cohort.py`
- `synthea/apply_demo_enrichment.py`
- `orchestrator/activities/addons.py`
- `orchestrator/tests/test_addons.py`
- `Deploy-All.ps1`
- `vendor/*`

## Dependencies
- Depends on `PATIENT_META` in `rayfin-imaging/pipeline/seed_patient360_silos.py` and `enrich_demo_cohort.py` helper functions.
- Prerequisites in live Fabric mode: Azure Health Data Services FHIR service provisioned.

## Decisions made
- **Agreed with the user**: `synthea/seed_tcga_cohort.py` CLI supports `plan` (default dry-run), `apply`, and `delete`. Generates FHIR R4 Patient (identifier = TCGA barcode, fictional names from `PATIENT_META`), Condition, MedicationRequest, Observation, Coverage, Device (Masimo, paired to Patient) with deterministic `resource_id` IDs and `synthetic-demo-enrichment` tag. Refuses overwrite of untagged resources; delete removes only tagged resources.
- **Decided by the ticket writer**: Device pairing links Marcus Vance (`TCGA-G6-A8L6`) to `MASIMO-RADIUS7-0001` and generates a FHIR `Basic` resource with code `device-assoc` conforming to `create-device-association-table.ipynb`, ensuring that the `DeviceAssociation` table in Gold and `DevicePayerOntology` automatically recognize the patient-device relationship.

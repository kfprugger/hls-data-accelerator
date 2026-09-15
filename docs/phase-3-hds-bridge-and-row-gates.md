# Phase 3 — HDS Bridge + Row Gates

Phase 3 deploys the vendored Microsoft Healthcare Data Solutions source, connects Azure source paths to OneLake, and runs the ordered pipelines that produce validated Silver and Gold data.

[← Phase 2](phase-2-active-patient-telemetry.md) · [Main README](../README.md) · [Interactive diagram](diagrams/phase-3-hds-bridge-and-row-gates.html) · [Diagram source](diagrams/phase-3-hds-bridge-and-row-gates.dataflow.json) · [Next: Phase 4 →](phase-4-semantic-intelligence-and-ux.md)

<a href="diagrams/phase-3-hds-bridge-and-row-gates.html">
  <img src="diagrams/phase-3-hds-bridge-and-row-gates.visual-check.1440x900.light.png#gh-light-mode-only" alt="Phase 3 flow from HDS source, FHIR export, and DICOM source paths through Bronze shortcuts and ordered clinical, imaging, POA, CMA, and OMOP pipelines into validated Silver and Gold state">
  <img src="diagrams/phase-3-hds-bridge-and-row-gates.visual-check.1440x900.dark.png#gh-dark-mode-only" alt="Phase 3 flow from HDS source, FHIR export, and DICOM source paths through Bronze shortcuts and ordered clinical, imaging, POA, CMA, and OMOP pipelines into validated Silver and Gold state">
</a>

## Exit contract

Phase 3 is complete only when:

- The HDS/DTT v1.4.0 source payload is built, staged, deployed, and validated.
- `healthcare1_environment` is published with the required libraries.
- `FHIR-HDS` and `DICOM-HDS` OneLake shortcuts point at the correct ADLS Gen2 source paths.
- Required Clinical and Patient Outreach Analytics pipelines complete.
- Imaging completes when selected and produces non-empty `ImagingStudy` and `ImagingMetastore` tables.
- OMOP starts only after the selected core pipelines complete and produces Gold CDM state.
- Required Bronze/Silver row gates and FHIR reference-integrity checks pass.

Optional sidecars and CMA cannot convert a failed required gate into success.

## Prerequisites

- [Phase 1](phase-1-data-fabric-foundation.md) produced a complete FHIR export and the selected DICOM files.
- The Fabric workspace identity has storage access and compatible ADLS ACLs.
- The workspace is attached to an active paid Fabric capacity.
- The deploying identity can create and run Fabric notebooks, environments, lakehouses, and pipelines.

## HDS source deployment

The repository vendors Microsoft HDS 1.4.0 under [`vendor/microsoft-hds/1.4.0`](../vendor/microsoft-hds/1.4.0/). That directory is immutable input. Build-time corrections and generated packages belong under `.hds-build/1.4.0`.

[`orchestrator/activities/deploy_hds_source.py`](../orchestrator/activities/deploy_hds_source.py) performs the source deployment contract:

1. Validate the vendored HDS/DTT source.
2. Build or reuse compatible wheels and repair package metadata when required.
3. Stage the payload in the deployment lakehouse.
4. Import the deployment and validation notebooks.
5. Publish `healthcare1_environment` with the required OpenTelemetry, SciPy, and HDS dependencies.
6. Run the HDS master deployment.
7. Validate the expected lakehouses, notebooks, pipelines, semantic models, and reports.

Validate the local payload without submitting a cloud deployment:

```bash
cd orchestrator
.venv/bin/python -m activities.deploy_hds_source \
  --workspace "<fabric-workspace>" \
  --validate-only
```

## OneLake bridge

[`phase-2/storage-access-trusted-workspace.ps1`](../phase-2/storage-access-trusted-workspace.ps1) resolves the Fabric workspace identity, grants the selected storage access, applies required ADLS ACLs, and creates:

| Shortcut | Source | Bronze location |
|---|---|---|
| `FHIR-HDS` | FHIR `$export` NDJSON | Clinical FHIR ingest path |
| `DICOM-HDS` | Re-tagged `.dcm` files | `Files/Ingest/Imaging/DICOM/DICOM-HDS` |

The shortcut itself is the terminal source folder. Adding an extra nested `DICOM-HDS` directory breaks the HDS namespace contract.

## Pipeline ordering

| Order | Pipeline/group | Gate behavior |
|---:|---|---|
| 1 | Claims/CCLF sidecars | Serialized when they can contend for Delta writers; optional |
| 2 | Other discovered sidecars | Best-effort and non-blocking when inputs are absent |
| 3 | Clinical foundation | Blocking; establishes Silver clinical readiness and reference integrity |
| 4 | Patient Outreach Analytics | Required; runs after clinical so its model is not left blank |
| 5 | Care Management Analytics | Optional non-blocking Silver consumer |
| 6 | Imaging with clinical foundation | Blocking when imaging is selected; starts only after clinical readiness |
| 7 | OMOP analytics | Runs alone after every selected core prerequisite completes |

## Row and reference gates

The script can require source rows explicitly:

- `-RequireClinicalFhirData` requires non-empty Bronze `ClinicalFhir` state.
- `-RequireImagingDicomData` requires non-empty Bronze `ImagingDicom` state.

It also checks:

- Silver FHIR reference projections remain intact after clinical processing.
- Silver `ImagingStudy` and `ImagingMetastore` contain data after imaging.
- Required pipeline job status reaches `Completed` within the bounded polling window.
- OMOP is skipped rather than started against incomplete selected prerequisites.

## Run it

A full deployment automatically starts HDS source work as early as dependencies permit and waits at the correct barrier.

For a post-source continuation that refreshes RTI enrichment and runs this bridge:

```powershell
./Deploy-All.ps1 `
  -Phase2 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -RequireBronzeClinicalFhir `
  -RequireBronzeImagingDicom
```

To run only the bridge after HDS source artifacts already exist:

```powershell
./phase-2/storage-access-trusted-workspace.ps1 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -RequireClinicalFhirData `
  -RequireImagingDicomData
```

Use `-SkipImagingPipeline` only when imaging is intentionally excluded from the selected deployment.

## Verify before Phase 4

- Required HDS items exist in the target workspace and are bound to that workspace—not IDs copied from another deployment.
- `FHIR-HDS` and `DICOM-HDS` resolve through OneLake without duplicating source data.
- Latest required pipeline jobs are `Completed`.
- Silver clinical tables contain the expected cohort and intact patient references.
- Silver imaging tables contain the selected studies.
- Gold OMOP tables contain queryable data for cohorting.
- POA facts are populated; a deployed but wholly blank semantic model fails this phase.

## Common failures

| Symptom | Check |
|---|---|
| HDS deploy works only on one machine | Inspect cached wheels and mutable package downloads; validate from a clean source payload |
| Shortcut exists but ingestion sees no files | Verify exact shortcut path, workspace identity RBAC, and ADLS access/default ACLs |
| Clinical completed but Silver references are broken | Stop downstream work and inspect the projection/reference contract |
| Imaging never starts | Clinical readiness is a hard prerequisite; inspect its job and row gates first |
| OMOP is skipped | One or more selected Clinical/Imaging gates did not complete |
| POA report is blank | Confirm `healthcare1_msft_poa_ingestion` has a completed job and populated facts |
| Capacity resumes but streams remain paused | Resume Eventstream nodes separately before relying on real-time downstream checks |

## Source map

- [`orchestrator/activities/deploy_hds_source.py`](../orchestrator/activities/deploy_hds_source.py) — HDS source staging and deployment
- [`vendor/microsoft-hds/1.4.0/`](../vendor/microsoft-hds/1.4.0/) — immutable Microsoft source input
- [`phase-2/storage-access-trusted-workspace.ps1`](../phase-2/storage-access-trusted-workspace.ps1) — shortcuts, ACLs, pipeline ordering, and row gates
- [`fabric-rti/HDS-SETUP-GUIDE.md`](../fabric-rti/HDS-SETUP-GUIDE.md) — deeper HDS deployment notes
- [`orchestrator/shared/deployment_validation.py`](../orchestrator/shared/deployment_validation.py) — deployed-resource validation

[← Phase 2 — Active Patient Telemetry](phase-2-active-patient-telemetry.md) · [Next: Phase 4 — Semantic Intelligence + UX →](phase-4-semantic-intelligence-and-ux.md)

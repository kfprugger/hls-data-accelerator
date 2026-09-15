# Phase 1 — Data Fabric Foundation

Phase 1 creates the Azure and Fabric control boundary, loads the synthetic clinical and imaging foundation, and leaves durable source paths for the real-time and HDS phases.

[← Main README](../README.md) · [Interactive diagram](diagrams/phase-1-data-fabric-foundation.html) · [Diagram source](diagrams/phase-1-data-fabric-foundation.dataflow.json) · [Next: Phase 2 →](phase-2-active-patient-telemetry.md)

<a href="diagrams/phase-1-data-fabric-foundation.html">
  <img src="diagrams/phase-1-data-fabric-foundation.visual-check.1440x900.light.png#gh-light-mode-only" alt="Phase 1 data flow from Synthea, TCIA, and workload containers into Azure FHIR, ADLS, Event Hubs, and the Fabric workspace">
  <img src="diagrams/phase-1-data-fabric-foundation.visual-check.1440x900.dark.png#gh-dark-mode-only" alt="Phase 1 data flow from Synthea, TCIA, and workload containers into Azure FHIR, ADLS, Event Hubs, and the Fabric workspace">
</a>

## Exit contract

Phase 1 is complete only when all of these are true:

- The target Fabric workspace exists, is assigned to an active paid capacity, and has a provisioned workspace identity.
- The Azure resource group contains the Event Hubs namespace, `telemetry-stream`, ACR, Key Vault, storage, and the selected container workloads.
- Synthetic FHIR R4 data is queryable in Azure Health Data Services.
- Device resources and `device-assoc` records link the demo cohort to the simulated Masimo devices.
- Re-tagged DICOM studies exist in `dicom-output`, with matching FHIR `ImagingStudy` resources.
- A completed FHIR `$export` is available in ADLS Gen2 for HDS ingestion.

## Prerequisites

Complete the root [Quickstart](../README.md#quickstart) and pass `Preflight-Check.ps1` first. The deploying identity needs:

- Azure resource creation and role-assignment permissions.
- Fabric workspace creation and capacity assignment permissions.
- Access to an active paid F-SKU capacity.
- An existing Entra security group for deployment administrators.
- Aligned Azure CLI and Az PowerShell tenant/subscription contexts.

## What gets deployed

| Area | Asset | Purpose |
|---|---|---|
| Fabric | Workspace + identity | Owns Fabric items and trusted workspace access |
| Azure messaging | Event Hubs namespace + `telemetry-stream` | Receives simulated device vitals |
| Build | Azure Container Registry | Stores emulator, Synthea, FHIR loader, and DICOM loader images |
| Secrets/control | Key Vault | Holds deployment-managed configuration that cannot use identity alone |
| Clinical | Azure Health Data Services workspace + FHIR R4 service | Stores the synthetic clinical record |
| Source landing | ADLS Gen2 | Holds Synthea output, FHIR `$export`, and re-tagged DICOM |
| Compute | Azure Container Instances/jobs | Runs Synthea, loaders, and the telemetry emulator |

Service-to-service traffic uses managed identities and RBAC. Application code does not embed Event Hub, FHIR, or storage credentials.

## Execution sequence

### 1. Fabric workspace and identity

`Deploy-All.ps1` creates or reuses the workspace, assigns the selected Fabric capacity, and provisions the workspace identity early. That identity is required by later OneLake and trusted-workspace operations.

### 2. Base Azure infrastructure

[`phase-1/deploy.ps1`](../phase-1/deploy.ps1) deploys the resource group foundation from [`bicep/infra.bicep`](../bicep/infra.bicep), builds the emulator image in ACR, deploys the container group, and grants `Azure Event Hubs Data Sender` to its managed identity.

### 3. FHIR service and synthetic cohort

[`phase-1/deploy-fhir.ps1`](../phase-1/deploy-fhir.ps1) and the supporting loaders:

1. Provision the AHDS workspace, FHIR service, storage, and user-assigned identity.
2. Run Synthea for the requested patient count; the repository default is 100.
3. Stage FHIR R4 bundles in blob storage.
4. Load bundles through [`fhir-loader/load_fhir.py`](../fhir-loader/load_fhir.py), including reference normalization, bundle splitting, and bounded retry handling.
5. Create deterministic Masimo device resources and `device-assoc` links with [`create-device-associations.py`](../create-device-associations.py).
6. Start the FHIR bulk `$export` used by Phase 3.

### 4. DICOM acquisition and linkage

The DICOM path uses [`dicom-loader/load_dicom.py`](../dicom-loader/load_dicom.py) to:

1. Download public studies from The Cancer Imaging Archive.
2. Replace patient identifiers and UIDs with synthetic cohort values while preserving pixel data.
3. Upload `.dcm` files to `dicom-output`.
4. Create matching FHIR `ImagingStudy` resources.

## Run it

A full deployment is the safest way to preserve ordering:

```powershell
$account = az account show --output json | ConvertFrom-Json

./Deploy-All.ps1 `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -FabricWorkspaceName "<fabric-workspace>" `
  -AdminSecurityGroup "<entra-security-group>" `
  -ExpectedTenantId $account.tenantId `
  -ExpectedSubscriptionId $account.id `
  -PatientCount 100
```

For focused development, the lower-level entry points are:

```powershell
./phase-1/deploy.ps1 `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -AdminSecurityGroup "<entra-security-group>"

./phase-1/deploy-fhir.ps1 `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -AdminSecurityGroup "<entra-security-group>" `
  -PatientCount 100
```

Do not treat the standalone scripts as a substitute for `Deploy-All.ps1` when you need the complete workspace, export, DICOM, and downstream handoff contract.

## Data strategy switches

| Switch | Behavior |
|---|---|
| `-UseCachedSynthea` | Loads the canonical cached 100-patient fixture |
| `-ReusePatients` | Keeps the current FHIR cohort and performs the downstream catch-up work |
| `-ReseedData` | Permanently replaces the current FHIR data before loading the requested cohort |
| `-ScaffoldingOnly` | Creates definitions and infrastructure without starting data producers or ingestion |
| `-SkipSynthea` | Skips new synthetic bundle generation |
| `-SkipDeviceAssoc` | Skips device/patient association creation |
| `-SkipDicom` | Skips TCIA download, re-tagging, and ImagingStudy creation |
| `-RebuildContainers` | Forces cloud container image rebuilds |

`-ReusePatients` and `-ReseedData` are mutually exclusive.

## Verify before Phase 2

- Query the FHIR service for `Patient`, `Device`, and `ImagingStudy` resources.
- Confirm the FHIR export container has completed NDJSON output rather than only a successful export request.
- Confirm `dicom-output` contains `.dcm` files for the synthetic study links.
- Confirm the emulator container is running and its managed identity has Event Hubs sender access.
- Confirm the Fabric workspace identity is provisioned and the selected capacity remains active.

The end-to-end harness performs broader checks after all selected phases. See [`eval/README.md`](../eval/README.md).

## Common failures

| Symptom | Check |
|---|---|
| Azure CLI and PowerShell disagree about the target | Align `az account set` and `Set-AzContext` before deployment |
| Container build succeeds but the workload cannot pull | Verify ACR image publication and `AcrPull` on the workload identity |
| FHIR `$export` returns success but no files appear | Poll the export job and inspect ADLS output before continuing |
| DICOM studies exist but do not join to the cohort | Compare re-tagged patient IDs with the created `ImagingStudy` and FHIR patient IDs |
| Workspace access fails later | Verify capacity assignment, workspace identity provisioning, and Fabric role membership |

## Source map

- [`Deploy-All.ps1`](../Deploy-All.ps1) — phase orchestration and workspace provisioning
- [`phase-1/deploy.ps1`](../phase-1/deploy.ps1) — Azure foundation
- [`phase-1/deploy-fhir.ps1`](../phase-1/deploy-fhir.ps1) — FHIR, Synthea, export, and DICOM orchestration
- [`fhir-loader/`](../fhir-loader/) — FHIR loading
- [`dicom-loader/`](../dicom-loader/) — DICOM acquisition and re-tagging
- [`synthea/`](../synthea/) — synthetic cohort generation and fixtures
- [`bicep/`](../bicep/) — Azure resource definitions

[← Main README](../README.md) · [Next: Phase 2 — Active Patient Telemetry →](phase-2-active-patient-telemetry.md)

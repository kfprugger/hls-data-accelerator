<div align="center">

# HLS Data Accelerator

**Deploy a connected healthcare data estate across Azure and Microsoft Fabric—from FHIR, DICOM, device telemetry, and claims to real-time analytics, lakehouse intelligence, AI agents, and operational action.**

<p>
  <a href="https://azure.microsoft.com/"><img alt="Azure" src="https://img.shields.io/badge/Azure-0078D4?style=flat-square&amp;logo=microsoftazure&amp;logoColor=white"></a>
  <a href="https://www.microsoft.com/microsoft-fabric"><img alt="Microsoft Fabric" src="https://img.shields.io/badge/Microsoft%20Fabric-742774?style=flat-square&amp;logo=powerbi&amp;logoColor=white"></a>
  <a href="https://hl7.org/fhir/R4/"><img alt="FHIR R4" src="https://img.shields.io/badge/FHIR-R4-E34F26?style=flat-square"></a>
  <a href="https://www.dicomstandard.org/"><img alt="DICOM" src="https://img.shields.io/badge/DICOM-enabled-005EB8?style=flat-square"></a>
  <a href="https://learn.microsoft.com/powershell/"><img alt="PowerShell 7+" src="https://img.shields.io/badge/PowerShell-7%2B-5391FE?style=flat-square&amp;logo=powershell&amp;logoColor=white"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-2EA44F?style=flat-square"></a>
</p>

[Quickstart](#quickstart) · [How it works](#how-it-works) · [Deployment phases](#deployment-phases) · [Documentation](#documentation) · [Teardown](#teardown)

</div>

> [!IMPORTANT]
> This repository is a reference accelerator for synthetic demonstration data and re-tagged public imaging data. It is not a medical device, clinical decision-support product, or production PHI landing zone. A full deployment creates billable Azure and Fabric resources.

<a href="docs/diagrams/system-overview.html">
  <img src="docs/diagrams/system-overview.visual-check.1440x900.light.png#gh-light-mode-only" alt="HLS Data Accelerator system overview showing healthcare sources flowing through Azure into Microsoft Fabric and developer-facing analytics and action surfaces">
  <img src="docs/diagrams/system-overview.visual-check.1440x900.dark.png#gh-dark-mode-only" alt="HLS Data Accelerator system overview showing healthcare sources flowing through Azure into Microsoft Fabric and developer-facing analytics and action surfaces">
</a>

<p align="center"><sub><a href="docs/diagrams/system-overview.html">Open the interactive system overview</a> · search, trace relationships, switch themes, and export the diagram</sub></p>

## Why this exists

Healthcare prototypes often stop at one workload: a FHIR server, a streaming dashboard, an imaging viewer, or a Power BI report. HLS Data Accelerator connects the full path so developers can deploy and evaluate the seams between those workloads:

- **Four healthcare data domains:** synthetic FHIR R4, re-tagged TCIA DICOM, simulated Masimo device telemetry, and synthetic payer events.
- **Batch and real time together:** Healthcare Data Solutions lakehouses and OneLake shortcuts sit beside Eventstreams, Eventhouse, and KQL.
- **Usable experiences, not empty scaffolding:** Power BI reports, real-time dashboards, OHIF imaging, Fabric Data Agents, ontologies, and Activator rules consume the deployed data estate.
- **One control plane:** the local React/FastAPI orchestrator and `Deploy-All.ps1` expose preflight, deployment presets, progress, recovery, validation, and teardown.
- **Fail-closed gates:** required pipelines, row counts, Eventstream topology, report facts, and published agent definitions are validated instead of treating resource creation as success.

## Quickstart

The browser orchestrator is the recommended path for a first deployment. The CLI uses the same deployment engine and is useful for automation and recovery.

### 1. Confirm cloud prerequisites

| Requirement | Minimum |
|---|---|
| Azure access | Permission to create resources and role assignments: **Owner**, or **Contributor + User Access Administrator** |
| Microsoft Fabric | An active paid **F-SKU (F2 or higher)** capacity; trial capacities are not supported by Healthcare Data Solutions |
| Fabric permissions | Ability to create a workspace and Fabric items, publish Data Agents, and use enabled tenant workloads |
| Entra ID | An existing security group used as the deployment administrator group |
| Tenant features | Healthcare Data Solutions, Real-Time Intelligence, Data Agents, Fabric IQ/Ontology, Data Activator, and Power BI enabled for the deploying identity |
| Local tools | Git, PowerShell 7+, Azure CLI 2.50+, Az PowerShell, Bicep, Node.js, and Python 3.10+ |

### 2. Clone and bootstrap

```bash
git clone https://github.com/kfprugger/hls-data-accelerator.git
cd hls-data-accelerator
```

macOS or Linux:

```bash
bash ./setup-prereqs.sh
```

Windows PowerShell:

```powershell
pwsh -NoProfile -File .\setup-prereqs.ps1
```

The bootstrap installs or verifies the local toolchain and creates the orchestrator Python environment. Re-run it with `-CheckOnly` after signing in to verify the complete local and cloud context.

### 3. Sign in to one tenant and subscription

Use the same tenant and subscription in Azure CLI and Az PowerShell:

```powershell
$tenantId = "<tenant-id>"
$subscriptionId = "<subscription-id>"

az login --tenant $tenantId
az account set --subscription $subscriptionId
Connect-AzAccount -Tenant $tenantId -Subscription $subscriptionId
Set-AzContext -Subscription $subscriptionId
```

Then verify the toolchain and account alignment:

```powershell
./setup-prereqs.ps1 -CheckOnly
```

### 4. Run preflight before cloud mutation

```powershell
./Preflight-Check.ps1 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -Location "eastus" `
  -AdminSecurityGroup "<entra-security-group>"
```

Preflight checks host architecture, PowerShell, Azure CLI, Bicep, both Azure login contexts, resource providers, the Entra group, Fabric API access, paid capacity readiness, and the companion imaging toolkit.

### 5. Start the deployment UI

```powershell
./Start-WebUI.ps1
```

Open [http://localhost:5173](http://localhost:5173), choose **Full platform**, review the generated plan, run preflight, and submit the deployment. Other presets support **Demo / fastest**, **Scaffolding / no data**, **Infra only**, **Resume / repair**, and **Data pipeline only**.

Stop the local UI when finished:

```powershell
./Start-WebUI.ps1 -Stop
```

### CLI alternative

This example deliberately passes the current Azure account IDs instead of relying on repository-specific defaults:

```powershell
$account = az account show --output json | ConvertFrom-Json

./Deploy-All.ps1 `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -FabricWorkspaceName "<fabric-workspace>" `
  -AdminSecurityGroup "<entra-security-group>" `
  -ExpectedTenantId $account.tenantId `
  -ExpectedSubscriptionId $account.id `
  -PatientCount 100 `
  -RunEval
```

`-RunEval` runs the end-to-end evaluation harness after deployment. Omit it only when you intentionally plan to validate later.

## How it works

1. **Preflight and orchestration.** The React UI calls a local FastAPI backend, which builds a deployment plan and invokes the PowerShell/Python activities with structured progress and recovery state.
2. **Clinical and imaging foundation.** Synthea creates synthetic FHIR R4 bundles; the loaders populate Azure Health Data Services, re-tag public TCIA DICOM studies, create `ImagingStudy` links, and stage FHIR exports and DICOM files in ADLS Gen2.
3. **Live telemetry.** A managed-identity emulator sends device events to Azure Event Hubs. Fabric Eventstream routes them into Eventhouse tables and KQL functions that power live dashboards and alerts.
4. **Healthcare Data Solutions.** The vendored Microsoft HDS/DTT v1.4.0 source is staged and deployed. OneLake shortcuts expose source files without an unnecessary copy; ordered pipelines produce Bronze, Silver, and Gold data products.
5. **Semantic and visual experiences.** Reporting materialization, Power BI, OHIF, Fabric ontologies, and Data Agents turn the governed data into imaging, cohorting, Patient 360, and triage experiences.
6. **Population and payer intelligence.** Claims and clinical facts feed quality measures, Star Ratings, HCC risk, readmission prediction, utilization, streaming payer scores, operations agents, and Activator rules.
7. **Validation and operations.** API-first checks prove item definitions, pipeline outcomes, fresh real-time flow, populated report facts, agent publication, and teardown coverage.

## Deployment phases

The conceptual phase model below matches the orchestrator monitor. A full deployment overlaps some work—for example, HDS source staging can run while Azure ingestion completes—but every phase has an explicit exit contract.

| Phase | Purpose | Primary implementation | Details | Interactive diagram |
|---:|---|---|---|---|
| 1 | Data Fabric Foundation | `phase-1/deploy.ps1`, `phase-1/deploy-fhir.ps1`, workspace provisioning in `Deploy-All.ps1` | [Phase 1 guide](docs/phase-1-data-fabric-foundation.md) | [Open](docs/diagrams/phase-1-data-fabric-foundation.html) |
| 2 | Active Patient Telemetry | `deploy-fabric-rti.ps1` core deployment and `-Phase2` enrichment | [Phase 2 guide](docs/phase-2-active-patient-telemetry.md) | [Open](docs/diagrams/phase-2-active-patient-telemetry.html) |
| 3 | HDS Bridge + Row Gates | `orchestrator/activities/deploy_hds_source.py`, `phase-2/storage-access-trusted-workspace.ps1` | [Phase 3 guide](docs/phase-3-hds-bridge-and-row-gates.md) | [Open](docs/diagrams/phase-3-hds-bridge-and-row-gates.html) |
| 4 | Semantic Intelligence + UX | `FabricDicomCohortingToolkit`, `phase-4/deploy-ontology.ps1`, `phase-2/deploy-data-agents.ps1` | [Phase 4 guide](docs/phase-4-semantic-intelligence-and-ux.md) | [Open](docs/diagrams/phase-4-semantic-intelligence-and-ux.html) |
| 5 | Bedside Alerting + Action | `ClinicalAlertActivator` deployment inside `Deploy-All.ps1` | [Phase 5 guide](docs/phase-5-bedside-alerting-and-action.md) | [Open](docs/diagrams/phase-5-bedside-alerting-and-action.html) |
| 6 | Population Health + Quality | `phase-5/materialize_claims_quality.py` and the canonical Power BI project | [Phase 6 guide](docs/phase-6-population-health-and-quality.md) | [Open](docs/diagrams/phase-6-population-health-and-quality.html) |
| 7 | Payer RTI + Operations | `phase-7/deploy-payer-rti.ps1` and the claim emulator | [Phase 7 guide](docs/phase-7-payer-rti-and-ops.md) | [Open](docs/diagrams/phase-7-payer-rti-and-ops.html) |

### Targeted switches are continuation modes

Historical CLI switch names do not map one-to-one to the conceptual phase numbers. Prefer a full deployment or the UI-generated resume plan. When operating directly:

| Switch | Actual targeted behavior |
|---|---|
| `-Phase2` | Refreshes post-HDS RTI enrichment and runs the HDS shortcut/pipeline bridge; ontology-aware agents remain deferred unless ontology is explicitly skipped |
| `-Phase3` | Runs the imaging/cohorting toolkit only |
| `-Phase4` | Runs ontology, ontology-aware agents, and bedside Activator work |
| `-Phase5` | Runs Population Health & Quality only (conceptual Phase 6) |
| `-Phase7` | Runs payer RTI and operations only |

## Architecture at a glance

### Data domains

| Domain | Producer | Landing path | Fabric use |
|---|---|---|---|
| Clinical | Synthea + FHIR Loader | Azure FHIR Service → `$export` → ADLS Gen2 | HDS Bronze/Silver, OMOP Gold, quality models, agents |
| Imaging | TCIA + DICOM Loader | Re-tagged `.dcm` in ADLS Gen2 + FHIR `ImagingStudy` | HDS imaging tables, reporting Gold, Power BI, OHIF |
| Device telemetry | Masimo emulator | `telemetry-stream` Event Hub | `MasimoTelemetryStream` → Eventhouse → KQL dashboards/alerts |
| Payer operations | Claim emulator | `claim-stream` Event Hub | `ClaimsRTIStream` → payer scoring, worklists, agents, Activator |

### Identity and data movement

- Service-to-service access uses managed identities and Azure/Fabric RBAC; secrets are not embedded in application code.
- OneLake shortcuts expose FHIR exports and DICOM source files to HDS without copying the source estate again.
- Telemetry and claims use separate Eventstreams because each topology owns one `DefaultStream` and the schemas route to different Eventhouse tables.
- Required pipelines and row gates are ordered. OMOP does not start until selected clinical and imaging prerequisites complete.

For the deeper component map, orchestration design, recovery model, and repository tree, read the [Project Architecture Blueprint](Project_Architecture_Blueprint.md).

## Deployment modes

| Mode | Use it when | Data behavior |
|---|---|---|
| Demo / fastest | You need a smaller first pass | Uses a smaller cohort and skips the heaviest optional surfaces |
| Full platform | You want the complete reference architecture | Deploys all selected phases and data paths |
| Scaffolding / no data | You need definitions and infrastructure without producers | Does not launch Synthea, DICOM, telemetry, claim producers, exports, or materialization runs |
| Infra only | You need the Azure/Fabric foundation | Skips downstream data and experience workloads |
| Resume / repair | A prior deployment partially completed | Reuses successful state and reruns only the selected recovery path |
| Data pipeline only | Infrastructure already exists | Runs the selected data processing path without recreating foundation resources |

## Project layout

```text
hls-data-accelerator/
├── Deploy-All.ps1                  # End-to-end deployment engine
├── Preflight-Check.ps1             # Non-deploying readiness checks
├── Start-WebUI.ps1                 # Local React + FastAPI orchestrator
├── Teardown-All.ps1                # Full Azure/Fabric cleanup
├── phase-1/                        # Azure, FHIR, Synthea, and DICOM foundation
├── phase-2/                        # HDS bridge, row gates, and clinical Data Agents
├── phase-4/                        # Fabric ontology deployment
├── phase-5/                        # Population Health & Quality materialization/report
├── phase-7/                        # Payer RTI, scoring, agents, and Activator
├── fabric-rti/                     # KQL, Eventstream, and RTI dashboard assets
├── orchestrator/                   # FastAPI backend and deployment activities
├── orchestrator-ui/                # React + Fluent UI frontend
├── eval/                           # API-first deployment evaluation harness
├── vendor/microsoft-hds/1.4.0/     # Immutable vendored Microsoft HDS source
└── docs/                           # Phase guides and interactive Archify diagrams
```

## Validation

A created resource is not automatically a working surface. The deployment and evaluation paths distinguish these gates:

- Azure resources exist and managed-identity RBAC is present.
- HDS deployment artifacts, environment publication, and required pipelines complete.
- Bronze/Silver/Gold row gates contain the required data.
- Eventstream source and destination nodes are `Running`, with fresh destination events.
- Semantic models are queryable and required facts are populated—not merely empty schemas.
- Reports expose the expected multi-visual layouts.
- Data Agent definitions are published with their intended datasources.
- OHIF resolves and renders indexed studies through the DICOMweb proxy.

See the [evaluation harness guide](eval/README.md) and the [interactive end-to-end verification map](docs/hls-end-to-end-verification.html).

## Teardown

> [!CAUTION]
> Teardown deletes the selected Fabric workspace and Azure resource groups. Review the resolved names before using `-Force`.

```powershell
./Teardown-All.ps1 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Force `
  -Wait
```

Use `-SkipAzure` for Fabric-only cleanup or `-SkipFabric` for Azure-only cleanup.

## Documentation

### Phase guides

- [Phase 1 — Data Fabric Foundation](docs/phase-1-data-fabric-foundation.md)
- [Phase 2 — Active Patient Telemetry](docs/phase-2-active-patient-telemetry.md)
- [Phase 3 — HDS Bridge + Row Gates](docs/phase-3-hds-bridge-and-row-gates.md)
- [Phase 4 — Semantic Intelligence + UX](docs/phase-4-semantic-intelligence-and-ux.md)
- [Phase 5 — Bedside Alerting + Action](docs/phase-5-bedside-alerting-and-action.md)
- [Phase 6 — Population Health + Quality](docs/phase-6-population-health-and-quality.md)
- [Phase 7 — Payer RTI + Operations](docs/phase-7-payer-rti-and-ops.md)

### Deep dives and operations

- [Project Architecture Blueprint](Project_Architecture_Blueprint.md)
- [Microsoft HDS v1.4.0 source deployment](fabric-rti/HDS-SETUP-GUIDE.md)
- [Ontology setup guide](docs/ONTOLOGY-SETUP-GUIDE.md)
- [Evaluation harness](eval/README.md)
- [End-to-end verification diagram](docs/hls-end-to-end-verification.html)
- [Changelog](CHANGELOG.md)

## Safety and scope

- **Synthetic/demo data only.** Do not point this accelerator at production PHI without a separate security, privacy, networking, retention, and compliance design.
- **Public imaging is re-identified only with synthetic IDs.** The DICOM loader preserves pixel data while replacing patient identifiers for the demo cohort.
- **Preview workloads can change.** Fabric IQ/Ontology, Data Agents, Operations Agents, and Activator behavior depends on tenant availability and current APIs.
- **Cloud cost is real.** Paid Fabric capacity, Azure Health Data Services, Event Hubs, storage, container builds, and container compute can accrue charges until paused or removed.
- **Alerting is opt-in.** Clinical and payer email rules require explicit recipient parameters; verify destinations before generating demo events.

## License

[MIT](LICENSE) © 2026 Joey Brakefield.

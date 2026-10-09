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

[Quickstart](#quickstart) · [How it works](#how-it-works) · [Deployment phases](#deployment-phases) · [Operations references](#operations-references) · [Teardown](#teardown)

</div>

> [!IMPORTANT]
> This repository is a reference accelerator for synthetic demonstration data and re-tagged public imaging data. It is not a medical device, clinical decision-support product, or production PHI landing zone. A full deployment creates billable Azure and Fabric resources.


## Why this exists

Healthcare prototypes often stop at one workload: a FHIR server, a streaming dashboard, an imaging viewer, or a Power BI report. HLS Data Accelerator connects the full path so developers can deploy and evaluate the seams between those workloads:

- **Four healthcare data domains:** synthetic FHIR R4, re-tagged TCIA DICOM, simulated Masimo device telemetry, and synthetic payer events.
- **Batch and real time together:** Healthcare Data Solutions lakehouses and OneLake shortcuts sit beside Eventstreams, Eventhouse, and KQL.
- **Usable experiences, not empty scaffolding:** Power BI reports, real-time dashboards, OHIF imaging, Fabric Data Agents, ontologies, and Activator rules consume the deployed data estate.
- **One control plane:** the local or [hosted React/FastAPI orchestrator](hosted/README.md) and `Deploy-All.ps1` expose preflight, deployment presets, progress, recovery, validation, and teardown.
- **Fail-closed gates:** required pipelines, row counts, Eventstream topology, report facts, and published agent definitions are validated instead of treating resource creation as success.

## Quickstart

The browser orchestrator is the recommended path for a first deployment. The CLI uses the same deployment engine and is useful for automation and recovery.

For hosted access, use the Entra-authenticated portal at **https://hls.jbatl.dev** and sign into the deployment tenant through the in-UI device-code flow. Operators provisioning the shared host should follow the [hosted bootstrap and release guide](hosted/README.md). The steps below run the same orchestrator locally.

### 1. Confirm cloud prerequisites

| Requirement | Minimum |
|---|---|
| Azure access | Permission to create resources and role assignments: **Owner**, or **Contributor + User Access Administrator** |
| Microsoft Fabric | An active paid **F-SKU (F2 or higher)** capacity; trial capacities are not supported by Healthcare Data Solutions |
| Fabric permissions | Ability to create a workspace and Fabric items, publish Data Agents, and use enabled tenant workloads |
| Entra ID | An existing security group used as the deployment administrator group |
| Tenant features | Healthcare Data Solutions, Real-Time Intelligence, Data Agents, Fabric IQ/Ontology, Data Activator, and Power BI enabled for the deploying identity |
| Local tools | Git, PowerShell 7+, Azure CLI 2.50+, Az PowerShell, Bicep, Node.js, and Python 3.13 x64 on Windows or Python 3.13–3.14 on macOS/Linux |

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

On Windows 11 ARM64, bootstrap selects **Python 3.13 x64 under x64 emulation**. PowerShell can remain native ARM64. Native Windows ARM64 Python is rejected because the pinned `cryptography` release has no Windows ARM64 wheel. Bootstrap recreates an incompatible orchestrator `.venv`; `-CheckOnly` never installs Python or changes the environment.

The repository contains source, configuration, and empty HDS table schemas, not bundled Synthea or Microsoft sample datasets. `-UseCachedSynthea` generates and validates the deterministic 100-patient cohort locally under ignored `synthea/.generated/` before upload. Microsoft sample-driven tools require separately supplied local data; see the [HDS setup guide](fabric-rti/HDS-SETUP-GUIDE.md).

Bootstrap installs the development-only Parquet inspector and enables `.githooks/pre-push` when no custom hook directory is configured. The hook checks every outgoing commit before Git sends it, including intermediate commits later deleting a dataset. Existing custom hooks are preserved with an integration warning. CI also checks the committed source tree. Run `orchestrator/.venv/bin/python utilities/check_repository_data.py` before committing, or `& .\orchestrator\.venv\Scripts\python.exe .\utilities\check_repository_data.py` on Windows. The check reads Git's index, so cleaning only an unstaged working file cannot hide staged data.

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

### Optional add-ons

The deploy form's **Add-ons** section selects Databricks, both Rayfin Fabric apps,
and/or the Caldova cardiology stack. They run after the base deployment passes its
live checks and appear as phases with logs and substeps. On a completed deployment,
the monitor's **Add-ons** panel can add or retry them without rerunning Deploy-All.

- **Databricks:** preflight checks the provider, region and CLI tools. A full run
  passes `-SnapshotFhirExportForDatabricks`; after the last FHIR export and before
  HDS ingestion, AzCopy copies `fhir-export` server-side to
  `fhir-export-databricks` and verifies matching blob counts. The deploying user
  needs Storage Blob Data Contributor (Phase 1 grants it to the admin group).
  Adding it later uses the existing FHIR export helper with the dedicated container.
  Scripts 01–07 run in a per-deployment copy with `DATABRICKS_AUTH_TYPE=azure-cli`
  and `HLS_NONINTERACTIVE=1`; the chosen admin group must be available in Unity
  Catalog. Metastore assignment is attempted automatically. If account-admin
  action is needed, the panel explains the account-console assignment and offers
  **Continue**, which rechecks assignment; the pause expires after 24 hours.
- **Rayfin:** each app gets its own deployment working copy and rewritten Fabric
  item IDs. Node/npm install, build and `rayfin up` run without login prompts.
  Management commands receive a Fabric-audience token; semantic-model/DB probes
  receive a Power BI-audience token, and SQL provisioning receives a SQL token.
  The new hosting origin is registered, not the checked-in demo origin. The command
  center installs its publication procedures, configures the app database secrets,
  and enrolls the deploying user as a writer; its first signed-in Gold sync publishes
  the snapshot. The triage app remains a workflow surface, not an automatic alert writer.
- **Cardiology:** supply operator/reviewer UPNs (reviewers must also be operators),
  location, optional resource prefix, and optional paired model name/version.
  Empty model fields use the built-in candidate list; preflight requires an offered
  DataZoneStandard version with at least 50K TPM free and app-registration permission.
  `WARDFLOW_ROOT` must point to the private `jb-dev` checkout/image snapshot. The
  runner seeds dry-run then apply, deploys the Masimo aggregator into the main RG,
  deploys Gold projection, waits for HDS ingestion to finish, refreshes Gold from
  the pre-seed UTC watermark, then deploys the app into `rg-<workspace>-cardio`.

The APIs are `POST /api/deploy/{id}/addons` with an `addons` list (`databricks`,
`rayfin`, `cardiology`) plus the form's option fields, and
`POST /api/deploy/{id}/addons/databricks/continue`. An active or paused add-on keeps
the sandbox active. Add-on failures on an already-completed deployment preserve
that base deployment and are shown separately. Work copies and JSONL logs live
under `HLS_DATA_DIR`; no access tokens are written to their configuration.

Full teardown already removes the Rayfin AppBackends and companion items, bound
Databricks Unity Catalog objects before the workspace, and the ownership-tagged
cardiology RG/app registration. The dedicated export container lives in the main
RG's storage account and is removed with that RG. Shared metastores and Fabric
capacity are not deleted.

## How it works

1. **Preflight and orchestration.** The React UI calls a local FastAPI backend, which builds a deployment plan and invokes the PowerShell/Python activities with structured progress and recovery state.
2. **Clinical and imaging foundation.** Synthea creates synthetic FHIR R4 bundles; the loaders populate Azure Health Data Services, re-tag public TCIA DICOM studies, and create `ImagingStudy` links. After patients and devices exist, `synthea/apply_demo_enrichment.py fhir` upserts deterministic, provenance-tagged payer Organizations, Coverage, Appointments, Conditions, and MedicationRequests before FHIR exports reach ADLS Gen2. Reuse and continuation runs enrich existing patients too; scaffolding and resource groups without FHIR skip enrichment.
3. **Live telemetry.** A managed-identity emulator sends device events to Azure Event Hubs. Fabric Eventstream routes them into Eventhouse tables and KQL functions that power live dashboards and alerts.
4. **Healthcare Data Solutions.** The vendored Microsoft HDS/DTT v1.4.0 source is staged and deployed. OneLake shortcuts expose source files without an unnecessary copy; ordered pipelines produce Bronze, Silver, and Gold data products. Immediately before POA ingestion, `synthea/apply_demo_enrichment.py outreach` runs `Seed_Outreach_Demo_Sources` against the Bronze lakehouse to seed seven Dynamics-style outreach tables from the same FHIR patients. It refuses to overwrite populated non-demo tables lacking `scenario_source`; the notebook must complete and verify every row count before POA starts. After the optional CMA pipeline completes successfully, the runner's `sdoh` mode executes the existing `phase-2/seed_cma_sdoh.py` in `Seed_CMA_SDOH_Demo`, attached to `healthcare1_msft_gold_cma`, before CMA semantic-model finalization. This seeds six synthetic SDOH tables, including 168 indicators and 28 ZIP/FIPS mappings; skipped or unsuccessful CMA pipelines do not seed them.
5. **Semantic and visual experiences.** Reporting materialization, Power BI, OHIF, Fabric ontologies, and Data Agents turn the governed data into imaging, cohorting, Patient 360, and triage experiences.
6. **Population and payer intelligence.** Claims and clinical facts feed quality measures, Star Ratings, HCC risk, readmission prediction, utilization, streaming payer scores, operations agents, and Activator rules.
7. **Validation and operations.** API-first checks prove item definitions, pipeline outcomes, fresh real-time flow, populated report facts, agent publication, and teardown coverage.

## Deployment phases

The conceptual phase model below matches the orchestrator monitor. A full deployment overlaps some work—for example, HDS source staging can run while Azure ingestion completes—but every phase has an explicit exit contract.

| Phase | Purpose | Primary implementation |
|---:|---|---|
| 1 | Data Fabric Foundation | `phase-1/deploy.ps1`, `phase-1/deploy-fhir.ps1`, workspace provisioning in `Deploy-All.ps1` |
| 2 | Active Patient Telemetry | `deploy-fabric-rti.ps1` core deployment and `-Phase2` enrichment |
| 3 | HDS Bridge + Row Gates | `orchestrator/activities/deploy_hds_source.py`, `phase-2/storage-access-trusted-workspace.ps1` |
| 4 | Semantic Intelligence + UX | `FabricDicomCohortingToolkit`, `phase-4/deploy-ontology.ps1`, `phase-2/deploy-data-agents.ps1` |
| 5 | Bedside Alerting + Action | `ClinicalAlertActivator` deployment inside `Deploy-All.ps1` |
| 6 | Population Health + Quality | `phase-5/materialize_claims_quality.py` and the canonical Power BI project |
| 7 | Payer RTI + Operations | `phase-7/deploy-payer-rti.ps1` and the claim emulator |

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
| Clinical | Synthea + FHIR Loader + deterministic demo enrichment | Azure FHIR Service → `$export` → ADLS Gen2 | HDS Bronze/Silver, OMOP Gold, quality models, agents |
| Imaging | TCIA + DICOM Loader | Re-tagged `.dcm` in ADLS Gen2 + FHIR `ImagingStudy` | HDS imaging tables, reporting Gold, Power BI, OHIF |
| Patient outreach | Generated outreach events linked to FHIR patients | `Seed_Outreach_Demo_Sources` → seven Bronze Delta tables | Required HDS POA ingestion and outreach reports |
| Device telemetry | Masimo emulator | `telemetry-stream` Event Hub | `MasimoTelemetryStream` → Eventhouse → KQL dashboards/alerts |
| Payer operations | Claim emulator | `claim-stream` Event Hub | `ClaimsRTIStream` → payer scoring, worklists, agents, Activator |

### Identity and data movement

- Service-to-service access uses managed identities and Azure/Fabric RBAC; secrets are not embedded in application code.
- OneLake shortcuts expose FHIR exports and DICOM source files to HDS without copying the source estate again.
- Telemetry and claims use separate Eventstreams because each topology owns one `DefaultStream` and the schemas route to different Eventhouse tables.
- Required pipelines and row gates are ordered. OMOP does not start until selected clinical and imaging prerequisites complete.


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
├── vendor/microsoft-hds/1.4.0/     # Microsoft HDS source and empty schemas; no bundled datasets
├── azure-databricks/               # Databricks deployment and validation assets
└── docs/                           # Data Agent schema refresh runbook
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

See the [evaluation harness guide](eval/README.md).

If an existing Data Agent shows stale or inaccessible schema selections, use the [Data Agent schema refresh runbook](docs/DATA-AGENT-SCHEMA-REFRESH.md). The utility is read-only by default; apply requires backups and verifies both draft and published selections.

## Teardown

> [!CAUTION]
> Teardown deletes the selected Fabric workspace, main Azure resource group and owned front ends. Preview with `-Plan` and review every delete/skip decision before executing.

```powershell
./Teardown-All.ps1 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -SubscriptionId "<deployment-subscription-id>" `
  -ExpectedTenantId "<tenant-id>" `
  -Plan
```

Remove `-Plan` to execute after typing `yes`; add `-Force` to skip that prompt. Every execution prints a read-only plan first, waits for Azure deletion, and reports deleted items, skipped front ends with reasons, and failures. Local deployment state is removed only after a successful non-plan run.

The shared teardown includes Rayfin apps, deployment-bound Fabric connections and Databricks Unity Catalog objects, and owned cardiology and DICOM viewer front ends. It does not target the shared hosted deployer. Discovery checks deployment ties and skips shared or unrelated groups. Supply `-FrontEndResourceGroup @("<front-end-rg>")` for explicit groups (ownership checks still apply); `-DicomViewerResourceGroup` is an optional explicit group with no default. `-NoFrontEndDiscovery` disables automatic front-end group discovery.

If preflight warns that lakehouse or Eventhouse endpoints could not be read (for example, while capacity is paused), SQL/Eventhouse-only front ends may not be discovered. Do not treat that as an empty inventory: investigate the warning and supply known front-end resource groups explicitly for ownership validation.

`-SubscriptionId` is required unless `HLS_SUBSCRIPTION_ID` or the deployment state supplies it; the Azure CLI default subscription is never used. `-ExpectedTenantId` refuses a tenant mismatch before deletion. Workspace and main resource group names may default from deployment state; there is no fallback resource group name. `-SkipAzure` omits main resource group deletion and `-SkipFabric` omits workspace deletion; always inspect the remaining connection and front-end actions in the plan.

`Deploy-All.ps1 -Teardown` uses the same implementation with `-Force`, pinned to `-ExpectedSubscriptionId`; it refuses to run if that parameter is empty, so the current Az PowerShell or CLI context is never the target. Use `Teardown-All.ps1 -Plan` when you only want a preview.

## Operations references

- [Azure Databricks destination](azure-databricks/README.md)
- [Microsoft HDS v1.4.0 source deployment](fabric-rti/HDS-SETUP-GUIDE.md)
- [Evaluation harness](eval/README.md)
- [Changelog](CHANGELOG.md)

## Safety and scope

- **Synthetic/demo data only.** Do not point this accelerator at production PHI without a separate security, privacy, networking, retention, and compliance design.
- **Public imaging is re-identified only with synthetic IDs.** The DICOM loader preserves pixel data while replacing patient identifiers for the demo cohort.
- **Preview workloads can change.** Fabric IQ/Ontology, Data Agents, Operations Agents, and Activator behavior depends on tenant availability and current APIs.
- **Cloud cost is real.** Paid Fabric capacity, Azure Health Data Services, Event Hubs, storage, container builds, and container compute can accrue charges until paused or removed.
- **Alerting is opt-in.** Clinical and payer email rules require explicit recipient parameters; verify destinations before generating demo events.

## License

[MIT](LICENSE) © 2026 Joey Brakefield.

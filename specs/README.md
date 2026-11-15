# HLS Data Accelerator Component Specification

Status: Needs decision · Date: 2026-11-13
Repo roots: `.` (this repository)

Hosted access policy: `https://hls.jbatl.dev` admits `microsoft.com` accounts plus operator accounts set in `HLS_ALLOWED_USERS`; self-hosters approve their own domains via `-AllowedDomains` (see [Component 12](#component-12-hosted-orchestrator--gateway-architecture-hostedgateway-hostedsandbox-hostedinfra-hosteddeploy-hostedorchestratorps1)).

## This revision

Contracts changed since round 2:
- **Component 1**: Documents linear backoff schedule per call site (capped at 60 s or 90 s) and exponential backoff (capped at 120 s); clarifies phase switch mappings and conditional execution of Data Agents under `-Phase2` with `-SkipOntology`.
- **Component 3**: Reconciles device associations (100 base devices plus 15 TCGA cohort devices, yielding 115 total) and emulator sizing with `-DeviceCount` and `-SeedTcgaCohort`.
- **Component 7**: Aligns `dim_patient` build rules: only an absent optional source is skipped and listed; a missing required source, schema drift, or any read or count error fails the run before the dimension is written. Every recomputed Gold table is written with `overwrite` + `overwriteSchema`, so an empty placeholder never blocks later real rows. A Gold step is skipped only when a source table is missing and all of its outputs are optional (`ALLOW_EMPTY_TABLES`); the skipped step and its unrefreshed tables are named. A missing source for a step with a required output, and any read, transform or write failure, fails the run and names the step and tables. The summary step creates empty placeholders only for genuinely absent optional tables, without overwriting, halts on missing required tables, and reports whether a read, count, required-table check or placeholder create failed. Distinguishes platform reporting Gold lakehouse `healthcare1_reporting_gold` from vendor CMA Gold lakehouse `healthcare1_msft_gold_cma`.
- **Component 9**: Separates the predicted dedupe outcome (`EXPECTED_DISPATCH`, `SUPPRESSED_DEDUPE`, `UNCERTAIN_BOUNDARY`, from `delta`) from the observed result (`DISPATCHED` only when the alert email is seen); correlates each drop to its own Eventhouse row, alert row and email through `metadata.alert_probe_id`; dry runs report planned beats with no timings; defines Databricks SQL alert per-device, per-tier cooldown in a 15-minute tumbling window. The SQL resource always deploys paused; setting `ALERT_EMAIL` alone does not activate it.
- **Component 10**: Maps `/data-share` readers directly to recorded owner requirements; replaces numeric internal constants with behavioral contracts.
- **Component 12**: Defines admission claims compared during MSAL `/organizations` sign-in; specifies B2B guest evaluation; defines idle reaper behavior where unreachable sandboxes are evicted after the idle limit.
- **Component 14**: Specifies deployment tag keys and front-end resource group discovery criteria; confirms teardown operates capacity-neutral.
- **Component 15**: Replaces redundant roadmap details with a concise milestone status table linking `specs/tickets/BOARD.md`.

### Decisions requested
1. **[AlertEngine](#alertengine)**: Keep both platform-specific alert definitions: Fabric Activator for the core path, and the Databricks SQL alert inside the opt-in add-on, with its SQL schedule left paused until an operator activates it for a registered workspace user? Recommended: yes.
2. **[DataShare](#datashare)**: Accept the shared `/data-share` mount for the reference deployment (every sandbox can read the share; isolation is application code plus sealed credentials) while access stays limited to `microsoft.com` accounts? Recommended: yes, and revisit before admitting other tenants.
3. **[ESC-4](#esc-4)**: Keep teardown capacity-neutral (D5) and add no `-PauseCapacity` switch? Recommended: yes.

## Problem

Deploying connected healthcare data platforms across Azure and Microsoft Fabric is fragmented and prone to integration drift. Developers and clinical engineering teams typically assemble disparate prototypes: a standalone FHIR server, an isolated DICOM PACS viewer, an independent streaming telemetry dashboard, or disconnected Power BI reports. The seams between these systems—data normalization, real-time ingestion, multimodal linkage, governed semantic modeling, and agentic workflows—are fragile and frequently fail in production.

Existing reference architectures suffer from several critical shortcomings:
1. **Scattered Control Planes:** Azure infrastructure, Fabric items, and Databricks workspaces require separate command-line invocations without unified preflight validation, structured progress streaming, or reliable continuation mechanisms.
2. **Fragile Data Seams:** Ingestion pipelines fail silently on schema mismatches, duplicate dimensions, missing location participants, and concurrent lakehouse writes.
3. **Weak Operational Verification:** Deployments routinely report success when cloud resources are provisioned, even though underlying Direct Lake semantic models, Data Agents, or Eventstreams remain empty, unconfigured, or unqueryable.
4. **Coarse-Grained Teardown:** Cleanup scripts frequently leave behind orphaned companion items or risk deleting shared Fabric capacities and hosting infrastructure.

This specification defines the complete, verified component architecture of the HLS Data Accelerator as unified by the November 2026 review.

Measurable verification criteria:
1. **Scattered Control Planes:** `Preflight-Check.ps1` returns structured JSON `{passed, checks, failures, warnings}` and exits with code 0 on pass or code 1 on failure before resource mutations; orchestrator supervises child processes in isolated process groups and streams structured events via SSE.
2. **Fragile Data Seams:** Medallion ingestion and materialization steps exit non-zero on any unhandled read, parse, or schema error; `dim_patient` fails closed if empty while fact tables contain rows.
3. **Weak Operational Verification:** `eval/deployment_eval_harness.py` validates non-empty query responses across all deployed Direct Lake models, Data Agents, and Eventstreams.
4. **Coarse-Grained Teardown:** `Teardown-All.ps1` removes all deployment-tagged resources and orphaned companions while preserving Fabric capacities and untied compute.

| Shortcoming / Failure Mode | Addressing Components | Verification Reference |
|---|---|---|
| **1. Scattered Control Planes** | Component 1 (`Deploy-All.ps1`), Component 2 (`Preflight-Check.ps1`), Component 10 (`orchestrator/local_server.py`), Component 11 (`orchestrator-ui/`), Component 12 (`hosted/`) | See [Verification §1, §3, §4, §6](#verification) |
| **2. Fragile Data Seams** | Component 3 (`fhir-loader`, `synthea`), Component 4 (`dicom-loader`, `hds-source`), Component 5 (Fabric IQ Ontology v2 TMDL), Component 7 (CMS Quality Measures), Component 8 (Payer RTI) | See [Verification §4, §5](#verification) |
| **3. Weak Operational Verification** | Component 6 (`eval/deployment_eval_harness.py`), Component 9 (`scripts/trigger_spo2_alert.py`) | See [Verification §4, §5](#verification) |
| **4. Coarse-Grained Teardown** | Component 14 (`Teardown-All.ps1`, `orchestrator/shared/full_teardown.py`) | See [Verification §1, §4](#verification) |

---

## Glossary

- **AppBackend**: Microsoft Fabric workload item hosting Project Rayfin application data and functions.
- **Caldova**: Cardiology clinical decision-support application integrated as an optional add-on.
- **Direct Lake**: Microsoft Power BI storage mode reading Delta Parquet files directly from OneLake storage without import or DirectQuery latency.
- **EGM**: Engineering Governance Model reviewing specifications and architectural implementations.
- **Eventhouse**: Microsoft Fabric real-time analytics database engine powered by KQL.
- **HCC**: Hierarchical Condition Category risk-adjustment model used by CMS.
- **HDS**: Healthcare Data Solutions in Microsoft Fabric, providing medallion pipelines and healthcare schemas.
- **PHI**: Protected Health Information.
- **PHQ**: Population Health & Quality semantic model and reporting layer.
- **Rayfin**: Suite of clinical imaging web applications (imaging viewer, clinical triage, command center) deployed on Azure Container Apps and Fabric.
- **Reflex**: Fabric Data Activator rule evaluating streaming telemetry or events to trigger notifications.
- **SDOH**: Social Determinants of Health data reflecting socioeconomic and environmental health measures.
- **WardFlow**: Private repository for a synthetic hospital-operations simulator and decision-support test bench. It is not a clinical system. A WardFlow branch also carries `caldova-cardio/`, a separate, self-contained snapshot of the Caldova cardiology app that is not part of WardFlow. The hosted WardFlow bundle and the cardiology add-on use that snapshot and the `rayfin-wardflow-persona-app/` navigator from the WardFlow checkout.

---

## Goals / Non-goals

### Goals
- **Unified Healthcare Control Plane:** Provide a single local and hosted control plane (`Deploy-All.ps1`, FastAPI `orchestrator/local_server.py`, and React UI `orchestrator-ui/`) managing end-to-end deployment across clinical FHIR, DICOM imaging, streaming vitals, CMS quality measures, and payer operations.
- **Fail-Closed Verification:** Enforce deterministic preflight checks (`Preflight-Check.ps1`), pipeline row-count gates (`-RequireBronzeClinicalFhir`, `-RequireBronzeImagingDicom`), and post-deployment evaluation (`eval/deployment_eval_harness.py` when `-RunEval` is passed) validating that Direct Lake models, Data Agents, and Eventstreams serve live data.
- **Governed Semantic Intelligence:** Replace retired legacy schemas with Fabric IQ Ontology v2 TMDL (`phase-4/build_ontology_v2.py`, `phase-4/deploy-ontology.ps1`) backed by Direct Lake tables.
- **Resilient Continuation & Phase Recovery:** Support targeted phase continuation (`-Phase2`, `-Phase3`, `-Phase4`, `-Phase5`, `-Phase7`) with strict isolation, skipping succeeded steps only when live prerequisites are verified. CLI switch `-Phase5` executes Phase 6 CMS quality measures.
- **Secure Multi-Tenant Hosting:** Provide an Azure Container Apps gateway (`hosted/gateway/`) and per-user isolated sandboxes (`hosted/sandbox/`) with tenant-level OpenID discovery, single device-code sign-in, AES-256-GCM auth seals, and cross-sandbox history synchronization.
- **Modular Add-on Ecosystem:** Enable clean post-deployment addition of Azure Databricks AI/BI Lakeview dashboards (`azure-databricks/`), Project Rayfin clinical imaging applications (`rayfin-imaging/`), and Caldova cardiology clinical decision support without invalidating core platform status.
- **Safe, Pinned Teardown:** Deliver subscription-pinned, ownership-aware teardown (`Teardown-All.ps1`, `orchestrator/shared/full_teardown.py`) that purges deployment-bound front ends, Databricks UC objects, and Fabric items without disrupting shared capacities.

### Non-goals
- **Production PHI Hosting:** This accelerator is strictly designed for synthetic Synthea data and re-tagged public TCIA imaging. It is not a HIPAA-certified production PHI landing zone.
- **Medical Device Certification:** The platform and associated triage tools are demonstration accelerators, not software as a medical device (SaMD) or clinical decision-support products.
- **Direct Workspace Private Link (WSPL) Automation:** Automated provisioning of Fabric Workspace Private Link endpoints under default-deny VNet policies remains an opt-in infrastructure phase requiring customer network coordination.
- **Universal Multi-Replica State Synchronization:** Caldova cardiology platform state operates as an in-process singleton, requiring single-replica container deployment.

---

## Journeys

### Journey 1: Full Automated Healthcare Estate Deployment
- **Given** an authorized operator with Contributor and User Access Administrator roles on an Azure subscription, an active Microsoft Fabric F-SKU capacity (F2 or higher), an Entra ID admin security group, sibling checkouts `../FabricDicomCohortingToolkit` (present, or cloned by preflight), `../wardflow` (when cardiology is deployed), and network access to GitHub.
- **When** the operator runs `pwsh -NoProfile -File ./Deploy-All.ps1 -FabricWorkspaceName 'med-prod' -Location 'westus2' -AdminSecurityGroup 'HlsAdmins' -RunEval`.
- **Then** `Deploy-All.ps1` `Test-Prerequisites` validates local tools, Azure sign-in, the admin security group, Fabric API access, and Azure Health Data Services region availability (the orchestrator web UI runs `Preflight-Check.ps1` separately through `POST /api/deploy/preflight`); Phase 1 provisions Azure Health Data Services and starts HDS source compilation in parallel; Synthea bundles and re-tagged The Cancer Imaging Archive (TCIA) DICOM studies are ingested; Phase 2 provisions Azure Event Hubs, Masimo device telemetry emulators, Fabric Eventstreams, and KQL tables; Phase 3 deploys DICOM shortcuts and HDS medallion pipelines; Phase 4 publishes Fabric IQ Ontology v2 TMDL items and binds Data Agents; Phase 5 deploys bedside Activator alert reflexes; Phase 6 materializes 23 Centers for Medicare & Medicaid Services (CMS) quality measure tables; Phase 7 launches payer claim streams and scoring; and optional `eval/deployment_eval_harness.py` validates operational surfaces.

### Journey 2: Continuation and Phase Recovery
- **Given** a previous deployment where Phase 1 and Phase 2 completed successfully, but downstream steps were halted due to an external network interruption.
- **When** the operator restarts deployment using a targeted phase switch (`-Phase3`, `-Phase4`, `-Phase5`, `-Phase7`) or selects "Resume run" via `/api/deploy/{instance_id}/continue-failed` in the web UI.
- **Then** the deployment engine inspects runtime deployment state JSON files and verifies live cloud prerequisites. In the CLI, `-Phase2` re-executes Phase 2 (Fabric Real-Time Intelligence enrichment) and Phase 3 HDS pipelines, exiting before downstream steps. Under `-Phase2`, Data Agents deploy only when `-SkipOntology` is passed; they bind to lakehouse tables without ontology. Otherwise they defer to `-Phase4` because `ClinicalDeviceOntology` deploys in Phase 4. Resuming downstream phases requires targeted phase switches (`-Phase3` for imaging toolkit, `-Phase4` for ontology and bedside Activator, `-Phase5` for CMS quality measures, `-Phase7` for payer RTI) or the web UI continuation endpoints.

### Journey 3: Hosted Sandbox Lifecycle and Authentication
- **Given** an approved user navigating to `https://hls.jbatl.dev`.
- **When** the user authenticates via Microsoft Entra ID OIDC through `hls-gateway` with authority `https://login.microsoftonline.com/organizations`.
- **Then** the gateway evaluates the boolean admission rule: admitted iff `(tid, oid)` or `(tid, email)` is in `HLS_ALLOWED_USERS`, or home `tid` is in `HLS_ALLOWED_TENANTS`. Because authority is `/organizations`, `tid` is the authenticating home tenant. Reference deployment access admits accounts whose home tenant is the Microsoft corporate tenant `72f988bf-86f1-41af-91ab-2d7cd011db47` (`microsoft.com` accounts), plus operator accounts set in `HLS_ALLOWED_USERS`. B2B guest accounts are not admitted through a tenant entry. Self-hosters approve domains with `-AllowedDomains` (domain resolves to a tenant via OpenID discovery at deploy time; approving a domain admits that whole tenant; consumer Microsoft-account tenants are refused). An unreachable sandbox records `unreachable_since`; it is evicted only after `unreachable_since` exceeds `HLS_IDLE_MINUTES` (`policy.py:154-156`). Known limit: a deployment run inside a sandbox that remains unreachable for that duration is lost. See [Component 12](#component-12-hosted-orchestrator--gateway-architecture-hostedgateway-hostedsandbox-hostedinfra-hosteddeploy-hostedorchestratorps1) for canonical admission rules.

---

## Design

### Architecture Overview

```text
[ Data Producers ]
  ├── Synthea Generator ─────────> Azure Health Data Services (FHIR R4) ───> $export ──> ADLS Gen2
  ├── TCIA Cancer Imaging ───────> DICOM Loader (re-tagged .dcm) ───────────> DICOMweb ──> ADLS Gen2
  ├── Masimo Pulse Oximeter ─────> Azure Event Hubs (telemetry-stream) ────> Eventstream ──> Eventhouse (KQL)
  └── CMS Claim Emulator ────────> Azure Event Hubs (claim-stream) ────────> Eventstream ──> Eventhouse (KQL)
                                                                                               │
[ Microsoft Fabric Medallion Architecture ]                                                    │
  ├── OneLake Shortcuts ─────────> Bronze Lakehouse (Raw FHIR, DICOM, Dynamics Outreach)       │
  ├── HDS 1.4.0 DataPipelines ───> Silver Lakehouse (Normalized Clinical FHIR & Imaging)       │
  ├── Spark & Direct Lake ───────> Gold Lakehouses (OMOP, CMA, SDOH, CMS Quality Measures)     │
  ├── Fabric IQ Ontology v2 ─────> TMDL Entity Bindings (ClinicalDeviceOntology, DevicePayer)   │
  └── Semantic Layer & UX ───────> Power BI Direct Lake Reports, OHIF Viewer, Rayfin Apps      │
                                                                                               │
[ Intelligence & Operational Action ]                                                          │
  ├── Fabric Data Agents ────────> Patient 360, Clinical Triage, Graph Agent (Fabric MCP) <────┘
  ├── Data Activator ────────────> Bedside SpO2 Reflexes & Payer Worklists (fn_ClinicalAlerts)
  └── Orchestrator Control ──────> FastAPI Backend (:7071) + React M3 UI + ACA Gateway (:443)
```

---

### Component 1: Base Deployment Orchestration (`Deploy-All.ps1`)
- **Purpose**: Provides unified, modular automation for provisioning and configuring all Azure and Fabric resources across clinical, telemetry, imaging, ontology, and quality measure tiers.
- **Entry Points**:
  - `Deploy-All.ps1`: Primary end-to-end automation script.
  - `deploy-fabric-rti.ps1`: Fabric Eventhouse, Eventstream, and KQL deployment engine.
  - `phase-1/deploy.ps1`: Base Azure foundation and storage deployment.
  - `phase-1/deploy-fhir.ps1`: FHIR service and Synthea ingestion pipeline.
  - `phase-2/deploy-data-agents.ps1`: Clinical Data Agent publication.
  - `phase-4/deploy-ontology.ps1`: Fabric IQ Ontology deployment.
  - `phase-5/materialize_claims_quality.py`: Spark quality measure computation.
  - `phase-7/deploy-payer-rti.ps1`: Payer streaming infrastructure.
- **Phase Execution & Switch Mapping**:
  CLI switch numbers predate the phase labels: `-Phase5` runs Phase 6 CMS Quality & Claims; `-Phase4` runs Phase 4 (Ontology) and Phase 5 (Bedside Activator); `-Phase2` runs Phase 2 RTI and Phase 3 HDS pipelines; `-Phase3` runs the Phase 3 DICOM imaging toolkit.

  | Phase | Script Label | Contents | CLI Switch | Entry Script |
  |---|---|---|---|---|
  | 1 | Data Fabric Foundation | Azure foundation, Health Data Services, FHIR ingestion, Bronze Lakehouse, HDS Source Deploy | *(default)* | `phase-1/deploy.ps1`, `phase-1/deploy-fhir.ps1` |
  | 2 | Active Patient Telemetry | Event Hubs, Masimo pulse oximeter emulator, Eventhouse, Eventstream, KQL tables | `-Phase2` *(partial)* | `deploy-fabric-rti.ps1` |
  | 3 | HDS Bridge + Row Gates | OneLake DICOM shortcut, HDS pipelines (FHIR & DICOM silver/gold tables), Cohorting Agent, DICOM Viewer | `-Phase2` *(pipelines)*, `-Phase3` *(toolkit)* | `Deploy-All.ps1`, `FabricDicomCohortingToolkit/Deploy-DataAgent.ps1` |
  | 4 | Semantic Intelligence & UX | Fabric IQ Ontology v2 TMDL (`ClinicalDeviceOntology`), Data Agent ontology binding | `-Phase4` | `phase-4/deploy-ontology.ps1` |
  | 5 | Bedside Alerting & Action | Fabric Data Activator Bedside SpO2 reflex (`fn_ClinicalAlerts`) | `-Phase4` *(terminal step)* | `scripts/deploy_clinical_activator.py` |
  | 6 | Population Health & Quality | 23 CMS quality measure tables, Power BI Direct Lake report | `-Phase5` | `phase-5/materialize_claims_quality.py` |
  | 7 | Payer RTI & Ops | Claim Event Hub, claim emulator, ClaimsRTIStream, Eventhouse `claims_events`, agent backfills | `-Phase7` | `phase-7/deploy-payer-rti.ps1` |
- **Inputs and Configuration**:
  - Required PowerShell parameters: `-FabricWorkspaceName`, `-Location`, `-ExpectedTenantId`, `-ExpectedSubscriptionId`. `-AdminSecurityGroup` defaults to `sg-msft-hds-dicom-project`.
  - Mode switches: `-ScaffoldingOnly`, `-Teardown`, `-RunEval`.
  - Continuation switches: `-Phase2`, `-Phase3`, `-Phase4`, `-Phase5`, `-Phase7`.
  - Resource and capacity selection: `-ResourceGroupName` (default `rg-medtech-rti-fhir`), `-CapacitySubscriptionId`, `-CapacityResourceGroup`, `-CapacityName`, `-SourceResourceGroup`, `-SilverLakehouseId`, `-SilverLakehouseName`.
  - Reuse and data replacement: `-ReuseFabricRti`, `-ReusePatients`, `-ReseedData`, `-UseCachedSynthea`, `-RebuildContainers`. `-ReusePatients` and `-ReseedData` are mutually exclusive. `-UseCachedSynthea` fixes `PatientCount` at 100. `-ReseedData` replaces the FHIR patient set.
  - Demonstration parameters: `-SeedTcgaCohort <bool>` (default `$false`), `-DeviceCount <int>`, `-PatientCount <int>`.
  - Alert and claim parameters: `-AlertEmail <string>`, `-AlertCooldownMinutes <int>` (1–1440; default 10), `-AlertTierThreshold <string>` (`WARNING`, `URGENT`, `CRITICAL`; default `URGENT`), `-PayerOpsEmail <string>` (falls back to `AlertEmail` when empty), `-ClaimEventRatePerMinute <int>` (default 60).
  - Row-count gates: `-RequireBronzeClinicalFhir`, `-RequireBronzeImagingDicom`.
  - Imaging and ontology selection: `-DicomToolkitPath`, `-DicomViewerResourceGroup` (default `rg-hds-dicom-viewer`), `-ReplaceOntology` (delete and recreate the ontology).
  - Export controls: `-SkipFhirExport`, `-SnapshotFhirExportForDatabricks` (preserve the export before HDS moves its source blobs).
  - Service principal credentials: `-SpnClientId`, `-SpnClientSecret`, `-SpnTenantId`. Keep credential values outside tracked profiles.
  - Logging and resource metadata: `-JsonLogs`, `-Tags`. The entry point always sets `SecurityControl=Ignore` in the resource tags.
  - Granular skips: `-SkipBaseInfra`, `-SkipFhir`, `-SkipDicom`, `-SkipFabric`, `-SkipSynthea`, `-SkipImaging`, `-SkipOntology`, `-SkipActivator`, `-SkipQualityMeasures`, `-SkipPhase7`, `-SkipPayerRti`, `-SkipPayerActivator`, `-SkipOpsAgent`, `-SkipGraphAgent`, `-SkipDeviceAssoc`, `-SkipRtiPhase2`, `-SkipHdsPipelines`, `-SkipHdsSource`, `-SkipDataAgents`.
- **Behavior Contract**:
  1. Validates prerequisites before it changes any resource. It uses its own function `Test-Prerequisites`: PowerShell 7, Az module, Azure CLI, Bicep, Azure sign-in, the setup-managed Python, Git, the admin security group, a Fabric API token, the imaging toolkit (`Ensure-DicomToolkitRepo`, when Phase 3 imaging is required), and Azure Health Data Services region availability. On failure it calls `exit 1`. `-Teardown` skips `Test-Prerequisites`. `Deploy-All.ps1` does not run `Preflight-Check.ps1`.
  2. Emits structured phase boundary events `@@PHASE|<id>|<label>|<stepCount>@@` consumed by UI and streaming logs.
  3. Launches HDS source deployment (`orchestrator/activities/deploy_hds_source.py`) in parallel with base Azure infrastructure to minimize deployment duration.
  4. **Retry Schedules**: `Deploy-All.ps1` implements two retry schedules:
     - Linear backoff: 15s per attempt (`15 * $attempt`). Fabric REST calls use up to 8 attempts capped at 90s (Phase 3 line 2546, Phase 4 lines 3027 and 3111, Phase 5 lines 3438 and 3470). Generic Phase 4 REST calls (`Invoke-P4Rest` line 2855) use up to 6 attempts capped at 60s. Power BI REST calls (lines 3567 and 3594) use up to 5 attempts capped at 60s. Transient HTTP status codes (403 with `RequestDeniedByInboundPolicy` or `Forbidden`, 429, 500, 502, 503, 504) and connection timeouts are classified via `Test-P5FabricTransientError` (lines 3399-3415).
     - Exponential backoff: `Invoke-FabricGetWithRetry` (line 1359) uses `[Math]::Min(120, 10 * [Math]::Pow(2, $attempt - 1))`, with up to 8 attempts capped at 120s.
  5. **Phase Switch Isolation**:
     - Bedside Activator runs during full platform deployments or as the terminal step of standalone `-Phase4`. It does not run under `-Phase2`, `-Phase3`, `-Phase5`, or `-Phase7`.
     - `-Phase3` sets `$SkipPhase7 = $true`, preventing Phase 7 execution during imaging-only runs.
     - CLI switch `-Phase2` executes Phase 2 RTI enrichment and Phase 3 HDS pipelines, then exits before downstream steps. Under `-Phase2`, Data Agents are created only when `-SkipOntology` is also passed. In that case they bind to Eventhouse KQL tables (`TelemetryRaw`, `AlertHistory`) and Silver lakehouse tables without the ontology. Otherwise they are skipped under `-Phase2` and deferred to `-Phase4` because `ClinicalDeviceOntology` deploys in Phase 4.
     - CLI switch `-Phase5` executes Phase 6 CMS Quality & Claims, skipping Phases 1–5 and 7.
  6. **Evaluation Alignment**: Opt-in switch `-RunEval` executes `eval/deployment_eval_harness.py`. Evaluation passes `--expected-device-associations` (`$expectedDeviceAssociations` in `Deploy-All.ps1:154`, which evaluates to 115 when `-SeedTcgaCohort` is `$true` and 100 when `$false`), `--resource-group`, and `--subscription`. Evaluation failure emits a warning and does not block deployment completion.
  7. **Teardown Delegation**: `-Teardown` delegates directly to `Teardown-All.ps1` with `-FabricWorkspaceName`, `-ResourceGroupName`, `-SubscriptionId $ExpectedSubscriptionId`, and `-ExpectedTenantId $ExpectedTenantId -Force`.
- **Verification Commands**: See [Verification §1](#1-powershell-syntax-parallel-execution--retry-classification).
- **Known Limits**: Requires an active Fabric capacity (F2 or higher); capacity pausing blocks pipeline execution.
- **Status**: Implemented. Verified by [Verification §1](#1-powershell-syntax-parallel-execution--retry-classification). Open: none.

---

### Component 2: Environment Preflight & Toolchain Bootstrapping (`Preflight-Check.ps1`, `setup-prereqs.ps1`)
- **Purpose**: Validates local and cloud prerequisites non-destructively and provisions reproducible runtime environments for local development and hosted sandboxes.
- **Entry Points**:
  - `Preflight-Check.ps1`: Standalone preflight validation script.
  - `setup-prereqs.ps1`: Windows and macOS/Linux PowerShell toolchain bootstrapper.
  - `setup-prereqs.sh`: Bash bootstrapping wrapper.
  - `utilities/check_repository_data.py`: Pre-push git hook validating that no datasets or PHI are committed.
- **Inputs and Configuration**:
  - `Preflight-Check.ps1`: `-FabricWorkspaceName`, `-Location`, `-AdminSecurityGroup`, `-SkipImaging`, phase switches (`-Phase2`, `-Phase3`, `-Phase4`, `-Phase5`, `-Phase7`), `-CapacityName`, `-DicomToolkitPath`.
  - `setup-prereqs.ps1`: `-CheckOnly`.
  - Toolchain lockfiles: `orchestrator/requirements.lock`, `utilities/repository-data-requirements.lock`.
- **Behavior Contract**:
  1. Validates Azure CLI login, active tenant/subscription context, RBAC permissions, Entra group existence, Fabric capacity assignment, and required Fabric tenant switches.
  2. Emits a deterministic JSON result `{passed, checks, failures, warnings}` to stdout; exits with code 0 on pass, code 1 on failure. This JSON payload and exit code form the machine-readable contract consumed by the UI and local server. The orchestrator runs `Preflight-Check.ps1` for `POST /api/deploy/preflight` (called by `orchestrator-ui/src/components/GuidedDeployment.tsx`) through `orchestrator/activities/invoke_powershell.py` `run_preflight`, then appends the add-on checks from `orchestrator/activities/addons.py` `preflight`. `Deploy-All.ps1` does not run `Preflight-Check.ps1`; its own `Test-Prerequisites` calls `exit 1` directly without emitting machine-readable JSON.
  3. **FabricDicomCohortingToolkit Auto-Clone Rule**: When Phase 3 imaging is required (`-not $SkipImaging -and ($Phase2 -or $Phase3 -or (-not $Phase4 -and -not $Phase5 -and -not $Phase7))`), `Preflight-Check.ps1` checks for `Deploy-DataAgent.ps1` at `../FabricDicomCohortingToolkit`. If absent, it clones repository `https://github.com/kfprugger/FabricDicomCohortingToolkit.git` (default branch, unpinned, as required by repository instruction). If the target directory already exists with content but lacks `Deploy-DataAgent.ps1`, preflight refuses to clone and records a failure. Any git clone failure records a failure, causing preflight to exit 1. If imaging is skipped, the toolkit repo is neither checked nor cloned.
  4. Pre-push hook: `setup-prereqs.ps1` (without `-CheckOnly`) sets `core.hooksPath` to `.githooks` when no hooks path is set; it keeps an existing hooks path and prints a warning. `.githooks/pre-push` runs `utilities/check_repository_data.py --pre-push` with the managed Python in `orchestrator/.venv`; without that Python the push fails. With `--pre-push`, the script inspects the Git tree of every outgoing commit (`push_revisions`: `<remote>..<local>`, or every commit on no remote for a new branch). Without `--pre-push`, it inspects the index, or one commit with `--revision`. It exits with code 1 and blocks the push when a tracked file:
     - has a record or archive suffix: `RECORD_FORMATS` (`.csv`, `.tsv`, `.ndjson`, `.jsonl`, `.dcm`, `.avro`, `.orc`, `.feather`, `.arrow`) or `ARCHIVE_FORMATS` (`.zip`, `.tar`, `.gz`, `.tgz`, `.7z`, `.whl`, `.jar`, `.pbix`);
     - is on a blocked path (`_blocked_path`): `synthea/output`, `synthea/prepackaged`, top-level `output`, any `prepackaged`, `.generated`, or `.hds-build` folder, any `PatientOutreachAnalytics` folder, vendored HDS `SampleData` or `ReferenceData`, or a file named `canonical-fixture-manifest.json`;
     - is a Parquet file with rows, a non-empty `.db`, `.sqlite`, or `.sqlite3` file, or a notebook with cell outputs;
     - is a `_delta_log` commit file with an `add` action whose statistics carry `numRecords`, `minValues`, or `maxValues`;
     - is a `JSON_FORMATS` file (`.json`, `.avsc`, `.bim`, `.pbir`, `.pbism`) that holds a clinical FHIR resource (a `resourceType` other than `Bundle` and the conformance types in `FHIR_REFERENCE_TYPES`);
     - is a symlink with an inspected suffix, or an inspected file that the script cannot parse.
     If the check cannot complete (for example, an unmerged index or a nested Git repository), the script exits with code 2 and the push also fails.
  5. Native macOS SQL access requires Microsoft ODBC Driver 18 and Homebrew `openssl@3` in addition to the Python toolchain; bootstrap does not install the ODBC driver. `Start-WebUI.ps1` passes `DYLD_LIBRARY_PATH` to the backend after `nohup`, which strips that variable on macOS. An explicit caller value stays authoritative; otherwise the launcher checks the interpreter's standard Apple Silicon (`/opt/homebrew`) or Intel (`/usr/local`) prefix and selects `opt/openssl@3/lib` only when both `libssl.3.dylib` and `libcrypto.3.dylib` exist. The caller's `DYLD_LIBRARY_PATH`, global library links and SQL encryption/certificate options remain unchanged. Direct Python startup must supply the compatible library directory as shown in the root [README](../README.md#2-clone-and-bootstrap).
- **Verification Commands**: See [Verification §1](#1-powershell-syntax-parallel-execution--retry-classification).
- **Known Limits**: Windows on ARM64 requires Python 3.13 x64 under emulation due to pre-compiled `cryptography` wheel constraints. Native macOS SQL access needs the separately installed ODBC driver and compatible OpenSSL major; an explicit incompatible library override can still fail.
- **Status**: Implemented. Verified by [Verification §1](#1-powershell-syntax-parallel-execution--retry-classification). Open: none.

---

### Component 3: FHIR Foundation, Loader & Device Associations (`phase-1/`, `fhir-loader/`, `./create-device-associations.py`)
- **Purpose**: Provisions Azure Health Data Services, generates synthetic longitudinal patient cohorts, loads FHIR R4 resource bundles with resilient HTTP retries, applies demo clinical enrichment, and associates patients with telemetry hardware.
- **Entry Points**:
  - `phase-1/deploy-fhir.ps1`: Azure FHIR service provisioning and export trigger.
  - `fhir-loader/load_fhir.py`: Multi-threaded FHIR bundle loader.
  - `synthea/apply_demo_enrichment.py`: Deterministic demo enrichment engine.
  - `./create-device-associations.py`: FHIR `Device` resource generator and patient association linker at repository root.
- **Inputs and Configuration**:
  - `FHIR_SERVICE_URL`, `RESOURCE_GROUP`, `-PatientCount <int>`, `-SeedTcgaCohort <bool>`, `--as-of`, `--no-capacity-resume`.
  - `-PatientCount` defaults depend on the entry point: 100 in `Deploy-All.ps1` (and the orchestrator `patient_count`), which passes it to `phase-1/deploy-fhir.ps1`; 10 when `phase-1/deploy-fhir.ps1` runs standalone. `-UseCachedSynthea` fixes it at 100 in both scripts. The Synthea job receives the value as `PATIENT_COUNT`.
- **Behavior Contract**:
  1. FHIR Provisioning: Creates Azure Health Data Services workspace and FHIR R4 service configured with managed identity RBAC.
  2. **Resilient HTTP Loader**: `fhir-loader/load_fhir.py` loads Synthea transaction bundles using `requests.Session` configured with `urllib3.util.retry.Retry`, retrying HTTP status codes `[429, 500, 502, 503, 504]` and transient connection errors with exponential backoff.
  3. **Enriched Synthetic Appointments**: `synthea/apply_demo_enrichment.py` seeds deterministic payer coverage, appointments, care encounters, conditions, and medication requests. All synthetic appointments carry a valid `Location` participant/reference to guarantee non-null `LocationKey` in downstream Healthcare Data Solutions (HDS) Provider Organization Analytics (POA) models.
  4. **Device Associations**: `./create-device-associations.py` (at repository root) associates all 100 base devices (`DEVICE_COUNT = 100`) with Masimo Radius-7 pulse-oximeters (`MASIMO-RADIUS7-0001` through `MASIMO-RADIUS7-0100`), cycling existing patients if needed so that no telemetry device is orphaned. When `-SeedTcgaCohort $true` is supplied, 15 additional devices (`MASIMO-RADIUS7-0101` through `MASIMO-RADIUS7-0115`) are provisioned and linked via `synthea/seed_tcga_cohort.py` (`generate_cohort_resources` and `build_device_association`), pairing Marcus Vance (`TCGA-G6-A8L6`) with `MASIMO-RADIUS7-0101` and subsequent patients with `0102`..`0115`, yielding 115 total device associations. In `Deploy-All.ps1`, `$expectedDeviceAssociations` evaluates to 115 when `-SeedTcgaCohort` is `$true` (100 otherwise), and `$effectiveDeviceCount` uses `$DeviceCount` when greater than 0, else 115 when `-SeedTcgaCohort` is `$true`, else 100.
- **Verification Commands**: See [Verification §4, §5](#4-orchestrator-backend-add-on--quality-model-tests).
- **Known Limits**: Server-side `$export` from FHIR service requires ADLS Gen2 storage with Storage Blob Data Contributor RBAC.
- **Status**: Implemented. Verified by [Verification §4, §5](#4-orchestrator-backend-add-on--quality-model-tests). Open: none.

---

### Component 4: DICOM Imaging & Healthcare Data Solutions (HDS 1.4.0) (`dicom-loader/`, `hds-source/`, `vendor/microsoft-hds/1.4.0/`)
- **Purpose**: Re-tags and ingests public The Cancer Imaging Archive (TCIA) cancer imaging studies, links them to FHIR patients via `ImagingStudy`, and deploys Microsoft Healthcare Data Solutions (HDS 1.4.0) medallion lakehouses (Bronze, Silver, Gold Observational Medical Outcomes Partnership [OMOP], Provider Organization Analytics [POA], Care Management Analytics [CMA]).
- **Entry Points**:
  - `dicom-loader/load_dicom.py`: TCIA study download, re-tagging, ADLS upload, and FHIR `ImagingStudy` creator.
  - `hds-source/Deploy-HdsSource.ps1`: Standalone HDS source build and deployment automation.
  - `orchestrator/activities/deploy_hds_source.py`: Orchestrator HDS background deployment activity.
  - `vendor/microsoft-hds/1.4.0/`: Vendored Microsoft Healthcare Data Solutions source assets and schemas.
  - `phase-2/seed_cma_sdoh.py`: SDOH demographic data seeder.
  - `phase-2/cma-report/`: Tokenized Care Management Analytics (CMA) TMDL model and PBIR report.
- **Inputs and Configuration**:
  - `-FabricWorkspaceName`, `-ValidateOnly`, `-ContractOnly`.
  - Spark Runtime: Fabric Runtime 1.3 (Spark 3.5).
  - Storage: OneLake shortcuts mapped to ADLS Gen2 `dcm` and `export` containers.
- **Behavior Contract**:
  1. **Strict Vendor Preservation**: Vendored Microsoft HDS 1.4.0 source code remains strictly unmodified under `vendor/microsoft-hds/1.4.0/`. Patched wheels and notebooks compile cleanly into temporary `.hds-build/1.4.0/`.
  2. **Direct Lake CMA Deployment**: `orchestrator/activities/deploy_hds_source.py` `_ensure_cma_items` creates or updates the CMA semantic model and report from tokenized TMDL/PBIR (`phase-2/cma-report/`). It substitutes `__SQL_ENDPOINT__` and `__DATABASE_NAME__` with connection properties of `healthcare1_msft_gold_cma`, the dedicated Microsoft HDS CMA Gold lakehouse (distinct from the platform reporting lakehouse `healthcare1_reporting_gold`). `_run_deployment_stage` calls it at the start of the `powerbi_deployer` stage. The vendor `powerbi_deployer` notebook then runs; `_patch_powerbi_deployer` makes that notebook fail on any semantic model or report deploy error.
  3. **Relational SDOH Seeding**: Seeds SDOH demographic tables into Gold lakehouse with one row per county/measure and subcategory key in `category_id`.
  4. Direct Lake shortcuts expose raw DICOM `.dcm` files and FHIR NDJSON files directly into Bronze Lakehouse without copying.
- **Verification Commands**: See [Verification §4, §5](#4-orchestrator-backend-add-on--quality-model-tests).
- **Known Limits**: Fabric workspace must use Fabric Spark Runtime 1.3; Runtime 2.0 requires explicit downgrade.
- **Status**: Implemented. Verified by [Verification §4, §5](#4-orchestrator-backend-add-on--quality-model-tests). Open: none.

---

### Component 5: Fabric IQ Ontology v2 TMDL (`phase-4/build_ontology_v2.py`, `phase-4/deploy-ontology.ps1`)
- **Purpose**: Generates and deploys Fabric IQ Ontology v2 items using Tabular Model Definition Language (TMDL), replacing the deprecated v1 JSON schema and establishing Direct Lake entity bindings over Gold Lakehouse tables.
- **Entry Points**:
  - `phase-4/build_ontology_v2.py`: TMDL generation compiler.
  - `phase-4/deploy-ontology.ps1`: Fabric REST API ontology publication script.
- **Inputs and Configuration**:
  - `-FabricWorkspaceName`, `-OntologyName` (`ClinicalDeviceOntology` or `DevicePayerOntology`), `-IncludeFhir`, `-IncludeDicom`, `-IncludeTelemetry`, `-IncludeGold`, `-ReplaceExisting`.
- **Behavior Contract**:
  1. `phase-4/build_ontology_v2.py` generates TMDL items: `database.tmdl` along with table, entity, and relationship TMDL files.
  2. Partitions use `mode: directLake` with `expressionSource: DatabaseQuery` binding to `dbo` lakehouse tables.
  3. Entities specify `backingTable`, `keyProperty`, and typed properties with deterministic UUIDv5 lineage tags.
  4. `ClinicalDeviceOntology` defines clinical core entities (Patient, Device, Encounter, Condition, MedicationRequest, Observation, ImagingStudy, DeviceAssociation). `DevicePayerOntology` adds Gold claims and payer entities (Claim, Payer, Diagnosis, PatientDiagnosis, MedAdherence, CareGap, PatientRisk, HighCostClaimant).
  5. `phase-4/deploy-ontology.ps1` creates the ontology with `POST /v1/workspaces/{id}/ontologies` and base64-encoded TMDL parts. It updates an existing v2 ontology with `POST /v1/workspaces/{id}/ontologies/{ontologyId}/updateDefinition?updateMetadata=true`. This replaces the deprecated Fabric IQ v1 JSON ontology schema with declarative TMDL items and Direct Lake partition bindings.
  6. **Existing Ontology Handling**: `phase-4/deploy-ontology.ps1` reads an existing ontology of the same name with `getDefinition`. A definition with a `.tmdl` part is v2. A failed `getDefinition` call stops the script.
     - Legacy v1 JSON ontology: the script sets `$ReplaceExisting = $true`, deletes the v1 ontology, and deletes every GraphModel named `<OntologyName>_graph_*`. Then it creates a new v2 item. A failed v1 delete stops the script. GraphModel delete errors do not stop the script.
     - Existing v2 ontology without `-ReplaceExisting`: the script keeps the item unchanged.
     - Existing v2 ontology with `-ReplaceExisting`: the script updates the definition in place. It does not delete GraphModels.
- **Verification Commands**: See [Verification §1, §4](#1-powershell-syntax-parallel-execution--retry-classification).
- **Known Limits**: Graph visualization in Fabric portal preview depends on tenant-level preview enablement.
- **Status**: Implemented. Verified by [Verification §4](#4-orchestrator-backend-add-on--quality-model-tests). Open: none.

---

### Component 6: Fabric Data Agents & API-First Evaluation Harness (`phase-2/deploy-data-agents.ps1`, `eval/`)
- **Purpose**: Configures natural-language Fabric Data Agents grounded on lakehouses and ontologies, and provides an automated post-deployment evaluation harness proving that user-facing surfaces serve real data.
- **Entry Points**:
  - `phase-2/deploy-data-agents.ps1`: Patient 360 and Clinical Triage Data Agent creation and schema binding.
  - `eval/deployment_eval_harness.py`: Automated surface verification harness.
  - `eval/surface_checks.py`: Direct Lake DAX and KQL query probes.
  - `eval/graph_agent_check.py`: Ontology graph agent verification.
  - `eval/operations_agent_check.py`: Healthcare operations agent verification.
- **Inputs and Configuration**:
  - Harness flags: `--workspace`, `--json-out`, `--skip` (`reports`, `agents`, `rti`, `deployment`, `browser`), `--no-capacity-resume`, `--expected-device-associations`, `--resource-group`, `--subscription`, `--capacity-id`.
  - Agent parameters (`phase-2/deploy-data-agents.ps1`): `-IncludeDicomImaging`, `-Patient360Only`, `-TriageOnly`.
- **Behavior Contract**:
  1. `phase-2/deploy-data-agents.ps1` deploys the Patient 360 and Clinical Triage Data Agents with structured system instructions, schema bindings, and few-shot examples. `Deploy-All.ps1` runs it after `ClinicalDeviceOntology` exists (Phase 4 step 8d); a `-Phase2` run defers it to Phase 4 unless `-SkipOntology` is set, and `-SkipDataAgents` skips it. Phase 7 deploys the Healthcare Graph Agent (see [Component 8](#component-8-payer-real-time-intelligence-rti-phase-7-phase-7deploy-payer-rtips1-phase-7claim-emulator)).
  2. Protocol Compliance: Data Agent evaluation queries agents via standard Fabric Model Context Protocol (MCP) JSON-RPC (`tools/list` and `tools/call`), avoiding deprecated OpenAI Assistants endpoints.
  3. Dynamic Capacity Resolution: Derives the assigned capacity ARM ID via Azure Resource Graph and resumes an inactive capacity before evaluation unless `--no-capacity-resume` is supplied. The check reads capacity state; it does not validate the SKU or prove that the selected SKU supports every probed feature.
  4. Surface Probes: Probes DAX expressions against Direct Lake models, checks Eventstream node status and event freshness in `TelemetryRaw` and `claims_events`, and verifies device association counts.
  5. Runtime preparation is mutating: the harness can start stopped producer containers, resume paused Eventstreams with `startType: Now`, and pause stale streams before resuming them from Now. That resume skips queued history. `--no-capacity-resume` disables capacity resumption only; it does not disable producer or Eventstream changes. Run these checks only on an estate authorized for those changes.
  6. Eventstream lifecycle convergence: HTTP 409 with `errorCode: ArtifactOperationConflict` means a resume or reset pause was not accepted. The harness re-reads runtime topology and tries again only if the operation is still needed, within the original deadline. It does not repeat an accepted lifecycle call. Failed nodes can settle while another node changes state, while a paused stream has not yet been resumed by this check, and for 180 seconds after its accepted resume. Other stable failures and deadline exhaustion fail the gate. Running nodes alone do not pass it; both destination tables must contain current events.
- **Verification Commands**: See [Verification §4](#4-orchestrator-backend-add-on--quality-model-tests).
- **Known Limits**: Capacity readiness is a state check, not a SKU compatibility check. The deployment harness is not a read-only health check; its Eventstream reset policy skips queued history.
- **Status**: Implemented. Verified by [Verification §4](#4-orchestrator-backend-add-on--quality-model-tests). Open: none.

---

### Component 7: Population Health & CMS Quality Measures (`phase-5/materialize_claims_quality.py`, `phase-5/cms-quality-report/`)
- **Purpose**: Computes 23 CMS quality measure tables, HCC risk adjustments, star ratings, and medication adherence facts via PySpark, and exposes a Direct Lake Power BI report.
- **Entry Points**:
  - `phase-5/materialize_claims_quality.py`: PySpark quality calculation script.
  - `phase-5/cms-quality-report/`: TMDL semantic model and PBIR report definitions.
- **Inputs and Configuration**:
  - Executed on Fabric Spark pool against platform reporting Gold lakehouse `healthcare1_reporting_gold` (created in Phase 3). Note that `healthcare1_msft_gold_cma` is a separate HDS Gold lakehouse dedicated to CMA.
  - Model: `Population Health & Quality Dashboard.SemanticModel`.
  - Report: `Population Health & Quality Dashboard.Report`.
- **Behavior Contract**:
  1. Materializes 24 Gold Delta tables (`TABLES`, including `dim_patient`) plus `FactDiagnosisOntology` into `healthcare1_reporting_gold`.
  2. Card Visual Safety: All 13 KPI cards across report pages project scalar DAX measures from `_Measures` table, preventing `Invalid Date` visual rendering crashes.
  3. **Relational Model Integrity**:
     - Semantic model relationships use a unique `dim_patient` dimension table as the one-side in 1-to-many relationships (preventing fan-out multiplication errors from non-unique `agg_quality_measures.patient_id`).
     - `dim_patient` is materialized by `phase-5/materialize_claims_quality.py` as the distinct union of non-empty patient IDs across seven patient-level tables (`agg_quality_measures`, `care_gaps`, `agg_medication_adherence`, `agg_risk_scores`, `readmission_risk_scores`, `agg_high_cost_claimants`, and `fact_claim`). Only an absent optional source in `ALLOW_EMPTY_TABLES` is skipped and named. A missing required source, a source without `patient_id` or `patient_ref`, or any other read or count failure stops the run before the dimension is written. The run also fails before the write when no patient source is available or no source yields a patient ID, so the existing `dim_patient` table stays unchanged. The summary step creates a declared empty schema only for a genuinely absent optional table, using non-overwriting writes. Read/count failures and missing required tables never trigger empty-table replacement.
     - Gold steps: every recomputed Gold table (and `FactDiagnosisOntology`) is written by `overwrite_gold_table` with `mode("overwrite")` and `overwriteSchema`, so the produced schema replaces a declared placeholder schema and real rows land over an empty placeholder from an earlier run. Step sources are read through `read_step_source`; a missing table raises `MissingSourceTableError`. `handle_gold_step_error` skips a step only when its source is missing and every output is in `ALLOW_EMPTY_TABLES`, and it names the step and the tables left unrefreshed. A missing source for a step with a required output, and any other read, transform or write failure, fails the run with the step and table names. Every Silver source also feeds a step with a required output, so a missing Silver table ultimately fails the run.
     - `dim_hcc` contains exactly one unique row per `hcc_code` (19 codes) built via `build_dim_hcc_rows(HCC_MAPPINGS, HCC_CANONICAL_NAMES)` with canonical names, coefficients, and hierarchy groups.
- **Verification Commands**: See [Verification §4](#4-orchestrator-backend-add-on--quality-model-tests).
- **Known Limits**: Requires clinical Synthea and claim emulator tables populated prior to running materialization.
- **Status**: Implemented. Verified by [Verification §4](#4-orchestrator-backend-add-on--quality-model-tests). Open: none.

---

### Component 8: Payer Real-Time Intelligence (RTI) Phase 7 (`phase-7/deploy-payer-rti.ps1`, `phase-7/claim-emulator/`)
- **Purpose**: Ingests streaming synthetic medical claims, evaluates real-time fraud and utilization scores, populates KQL tables, and powers Healthcare Operations Agents.
- **Entry Points**:
  - `phase-7/deploy-payer-rti.ps1`: Payer RTI deployment script.
  - `phase-7/claim-emulator/claim_emulator.py`: Claims generator application.
  - `phase-7/agent-grounding-backfills.ps1`: Claim summary and agent grounding seeder.
- **Inputs and Configuration**:
  - Event Hub: `claim-stream`.
  - Claim emulator: Container instance `claim-emulator-grp` emitting `-ClaimEventRatePerMinute` claims/min (default 60; configurable via `CLAIM_EVENT_RATE_PER_MINUTE`).
  - Claim emulator environment (`phase-7/claim-emulator/claim_emulator.py`): `PATIENT_COUNT` (default 100), `FRAUD_VELOCITY_PROVIDER_ID` (default `TEST-PROVIDER`), `FRAUD_AMOUNT_MULTIPLIER` (default 6). Values below 1 for `PATIENT_COUNT` and `FRAUD_AMOUNT_MULTIPLIER` become 1.
  - Eventstream: `ClaimsRTIStream` routing to Eventhouse table `claims_events`.
  - Definition-only controls: `-SkipClaimEmulator`, `-SkipSnapshotMaterialization`. With payer RTI enabled, `-SkipClaimEmulator` stops an existing `claim-emulator-grp` instead of deploying a producer. `-SkipSnapshotMaterialization` defers Gold Lakehouse bindings and snapshot materialization while preserving schemas, functions and grounding definitions.
  - Agent controls: `-SkipOpsAgent` (HealthcareOpsAgent and Payer Ops Triage), `-SkipGraphAgent` (Healthcare Graph Agent). `Deploy-All.ps1` sets both with `-SkipPhase7`, with `-SkipFabric`, and on `-Phase3`, `-Phase4` or `-Phase5` continuations.
- **Behavior Contract**:
  1. Provisions dedicated Azure Event Hub `claim-stream` and claim emulator ACI.
  2. Deploys Fabric Eventstream `ClaimsRTIStream` isolated from device telemetry stream (each topology owns its own `DefaultStream`).
  3. Ingests claims into Eventhouse KQL database, computing rolling utilization, readmission likelihood, and fraud flags.
  4. Backfills claim grounding summaries for Healthcare Operations Agent via `phase-7/agent-grounding-backfills.ps1`.
  5. **Healthcare Graph Agent**: Unless `-SkipGraphAgent` is set, `phase-7/deploy-payer-rti.ps1` creates or updates the `Healthcare Graph Agent` Data Agent for `DevicePayerOntology` traversal. Its sources are the Eventhouse KQL database plus, when `-SkipSnapshotMaterialization` is not set, the Reporting Gold lakehouse and `DevicePayerOntology` if each is found. With `-SkipSnapshotMaterialization` the agent gets definition-only instructions. The script writes the manual graph-attach steps to `.graph-agent-manual-steps-<workspace>.txt` in the state-tracking directory.
- **Verification Commands**: See [Verification §1, §5](#1-powershell-syntax-parallel-execution--retry-classification).
- **Known Limits**: Continuous claim streaming accrues Event Hub and Eventhouse capacity consumption; stop emulator when demo concludes.
- **Status**: Implemented. Verified by [Verification §1, §5](#1-powershell-syntax-parallel-execution--retry-classification). Open: none.

---

### Component 9: Real-Time Alerts & Data Activator Reflexes (`scripts/deploy_clinical_activator.py`, `scripts/trigger_spo2_alert.py`)
- **Purpose**: Configures Fabric Data Activator Reflex items monitoring live KQL telemetry for SpO2 drops and vital anomalies, and provides automated alert trigger and stopwatch timing.
- **Entry Points**:
  - `scripts/deploy_clinical_activator.py`: Reflex definition compiler and deployer (authoritative in repository).
  - `scripts/trigger_spo2_alert.py`: SpO2 vital drop injector and stopwatch timer.
- **Inputs and Configuration**:
  - `--workspace`, `--email`, `HLS_ALERT_EMAIL`, `--cooldown-minutes` (valid range 1..1440, default 10; passed from `Deploy-All.ps1` via `-AlertCooldownMinutes`, default 10; hosted runs use the default cooldown of 10 minutes), `--settle-seconds` (delay in seconds before baseline and drop, default 0; orchestrator passes 70 after fresh Reflex deploy), `--min-tier` (`WARNING`, `URGENT`, `CRITICAL`; default `URGENT`; passed from `Deploy-All.ps1` via `-AlertTierThreshold`, default `URGENT`), `EVENTHUB_NAMESPACE` (or `EVENT_HUB_NAMESPACE`), `EVENTHUB_NAME` (or `EVENT_HUB_NAME`; default `telemetry-stream`), `RESOURCE_GROUP`, `EVENTHOUSE_QUERY_URI`.
  - Patient and live device lookup: `--patient-id` (default `TCGA-G6-A8L6`), `--live`, `FHIR_SERVICE_URL` (or `FHIR_URL`; otherwise the single FHIR service in `--resource-group`), and optional `HLS_FHIR_TOKEN` (otherwise `az account get-access-token`).
  - Reflex polling interval: 60 seconds (`executionIntervalInSeconds = 60`).
  - Alert functions: `deploy-fabric-rti.ps1` section 6e creates `fn_SpO2Alerts`, `fn_PulseRateAlerts` and a basic `fn_ClinicalAlerts` from inline KQL (same text in `utilities/run-kql-scripts.ps1`); Phase 2b replaces `fn_ClinicalAlerts` with the version that joins HDS Silver patient, condition and device-association data. SpO2 counts only non-null readings with `0 < spo2 < 100` and compares the unrounded minimum; pulse rate uses `toint(pr)` with no positivity filter. `fabric-rti/kql/03-clinical-alert-functions.kql` is a readable copy of the same thresholds and is not run by any deploy script.
- **Behavior Contract**:
  1. **Stateful Reflex Design**: `scripts/deploy_clinical_activator.py` builds a stateful Reflex rule using Microsoft Learn Method 2 (`Device` object grouping and `alert_active` transition `BecomesGreaterThan 0`). The KQL source queries `fn_ClinicalAlerts(cooldown_minutes)` filtered to tiers at or above `--min-tier`, joined with a `TelemetryRaw` roster lookback (`max(60, cooldown_minutes + 10)m`) to project one row per device with `alert_active` (`iff(isnotempty(alert_tier), 1, 0)`), `alert_tier` (coalesced to `'NORMAL'`), `spo2`, and `pr`. The Reflex entity graph defines a `Device` object view keyed by `device_id` (`IdentityPartAttribute`), a `SplitEvent` event view mapping events to `Device`, and an `AttributeTrigger` evaluating `alert_active` rising transitions. Actions send email alerts through tenant notification connectors to validated recipients with a per-device cooldown window (`cooldown_minutes`, default 10 minutes).
  2. **Eventhouse Alert Classification & Baseline Telemetry**: Deduplication is predicted from Eventhouse alert history rather than local state, and delivery is reported only when it is observed. `scripts/trigger_spo2_alert.py` queries `TelemetryRaw` for the newest reading on the device whose tier is at or above `--min-tier`, over the last `cooldown_minutes` plus 70 s. The tier uses the deployed SpO2 and pulse-rate predicates (see Inputs), then the enriched `fn_ClinicalAlerts` escalation: WARNING becomes URGENT and URGENT becomes CRITICAL when a patient linked to the device through `SilverBasic` has a high-risk condition code in `SilverCondition`. It calculates `delta = drop_epoch - previous_alert_epoch` (drop time minus that reading's timestamp, or `None` when no qualifying reading exists; a one-row null aggregate counts as no history). Parameters: $W = \text{cooldown\_minutes} \times 60$ (default 10 min = 600s), $P = \text{poll\_interval\_seconds}$ (60s), and $L = \text{latency\_allowance\_seconds}$ (10s).
     If the history query fails, returns a Kusto in-band error, has no `PrimaryResult`, does not return exactly one aggregate row, returns a malformed timestamp, or does not return a boolean high-risk flag, the script logs the error, predicts `UNCERTAIN_BOUNDARY`, and does not poll the Graph mailbox.
     The prediction (`expected_outcome`) has three classes:
     - `SUPPRESSED_DEDUPE`: `delta < W - L` (delta < 590s). `email_expected` is false. The script does not poll the Graph mailbox; stopwatch beat 4 (`activator_dispatched`) is `suppressed`.
     - `EXPECTED_DISPATCH`: no qualifying history, or `delta > W + P + L` (delta > 670s). `email_expected` is true, and the script polls the Graph mailbox for T3.
     - `UNCERTAIN_BOUNDARY`: `W - L <= delta <= W + P + L` (590s <= delta <= 670s). Email delivery is unknown; T3 is neither polled nor asserted; beat 4 is `uncertain`, and the result carries `boundary_notice`.
     The result `status` reports what was observed: `PLANNED` (dry run), `DISPATCHED` (only when the matching email was observed), `DISPATCH_NOT_OBSERVED` (an email was expected but not seen before the deadline), `SUPPRESSED_DEDUPE`, or `UNCERTAIN_BOUNDARY`. `dispatch_observed` is true only for `DISPATCHED`.
     **Per-drop correlation and timing**: every event the script sends carries a fresh `metadata.alert_probe_id`. T0 is the drop timestamp. T1 is the `ingestion_time()` of the `TelemetryRaw` row with this probe id. T2 is the Eventhouse `now()` at the first poll that returns a `fn_ClinicalAlerts(cooldown_minutes)` row for this device and tier with `alert_time >= T0` while this probe's row is inside the cooldown window. The Reflex query projects the newest probe id per device (within the cooldown window) as attribute `alert_probe_id`, and the alert email subject ends with `[probe <id>]`. T3 is the Graph `receivedDateTime` of a message whose subject contains this marker and the device id, received at or after T0 (up to 4 pages of 25 messages, 180 s deadline). A beat whose timestamp is missing, has no UTC offset, is malformed, or is earlier than T0 stays `not_observed`; every poll has a time and attempt limit. Each poll checks its absolute deadline immediately before each attempt and calculates a fresh remaining budget, so time spent paused also reduces the next request's timeout. Graph pages share one deadline and use at most 15 s per page. A result that arrives after the deadline is not counted. The baseline, T1 and T2 polls each have a 30 s deadline; the single recent-telemetry and history queries use a 30 s HTTP timeout. A timed-out query keeps its error: a history timeout predicts `UNCERTAIN_BOUNDARY`, and a T1 or T2 timeout is the poll's last query error. If two drops reach one device inside one 60 s evaluation, the email carries the later probe id and the earlier run's T3 stays `not_observed`. A dry run makes no network calls: every beat is `planned` with null timestamps, and `t_ingest`, `t_detect`, `t_action` and `t_total` are null.
     The drop is always transmitted to Eventstream regardless of deduplication state so downstream tables receive continuous telemetry. Before injecting a drop, the script checks `TelemetryRaw` for recent telemetry on the device within 55 minutes (`ago(55m)`). If absent, it seeds a normal baseline reading (`spo2` 97.0%, `pr` 80, with its own probe id) via Event Hub (15s timeout; exits 1 on failure), polls KQL up to a 30s deadline for that probe's row, and pauses 70 seconds ($P + L$) before the SpO2 drop. In live mode, the script exits 0 if T1 and T2 were observed, or 1 if either was not. The result field `poll_errors` keeps the last Eventhouse error of the baseline, T1 and T2 polls, and the exit-1 message shows the T1 and T2 errors; a T3 that was not seen is reported as `DISPATCH_NOT_OBSERVED` and does not change the exit code. The Rayfin add-on runs the Reflex deploy and the live trigger (passing `--min-tier` from the run config and `--cooldown-minutes` from the single add-on constant `ALERT_COOLDOWN_MINUTES`, 10) without catching their errors, so a failed lookup or a non-zero exit fails the add-on (ticket 012 FR-4).
     **Live patient-device resolution**: In live mode (`--live` without `--dry-run`), `resolve_patient_device` reads FHIR before any telemetry is sent. `--patient-id` must be FHIR-id shaped (`[A-Za-z0-9-.]`, 1–64 characters). It resolves to a Patient only by exact resource id (an `_id` search whose returned `id` equals the request) or by an exact `Patient.identifier` value in the `https://gdc.cancer.gov/tcga/barcode` system. No match fails, and more than one matching Patient fails. The script then searches `Basic` for code `device-assoc` (`http://terminology.hl7.org/CodeSystem/basic-resource-type`) and subject `Patient/<resolved id>` (`_count=100`). It considers only returned resources that carry that code and whose `subject.reference` is exactly `Patient/<resolved id>` or that reference under the configured FHIR base URL; other returned resources are ignored. Display names, id prefixes and other patients' associations never select a device, and live mode has no local-cohort or invented-device fallback. Each considered association must have a list of extension objects, exactly one recognized association-status extension with a non-empty `valueCode`, and exactly one recognized associated-device extension whose reference is `Device/<FHIR id>`; a missing, duplicate or malformed status or device field fails the lookup. A well-formed association whose status is not `active` is skipped, not accepted. If no active association remains, the lookup fails. If several valid active associations name different devices, the lowest device ID is used. Each search must return one complete `searchset` Bundle: a `next` link, a `total` that differs from the entry count, malformed links or entries, an entry whose search mode is not `match` (such as `include`), or a resource of another type fails the lookup, and no returned link is followed. FHIR HTTP failures report only the status code and its standard phrase, and transport failures only the exception type; FHIR response bodies, server-supplied reasons and tokens are not printed. An az CLI failure (FHIR discovery or token) includes up to 300 characters of az stderr; az stdout is never printed. Every lookup failure exits nonzero (1; 2 when neither a FHIR URL nor a resource group is set) before Event Hub or Eventhouse is contacted. Dry runs keep the deterministic local cohort mapping without network access.
     Observation deadlines and each request's remaining budget use `time.monotonic()`, so a backward UTC adjustment cannot extend a window or increase a Graph page budget. Event timestamps, T0 and deduplication epoch calculations still use UTC. Programmatic `run_trigger` callers inject these independently with `time_fn` (UTC) and `monotonic_fn` (elapsed time).
  3. Execution boundary: Bedside activator is deployed during full platform runs or as the terminal step of standalone `-Phase4` only. It does not run under `-Phase2`, `-Phase3`, `-Phase5`, or `-Phase7`.
  4. **Databricks Alert Path**: An alternative clinical alert definition exists in `azure-databricks/implementation/bundle/resources/sql.yml` and `azure-databricks/implementation/bundle/src/silver_realtime.py`. When enabled, the Databricks SQL alert evaluates `clinical_alert_candidates` every 5 minutes (`0 0/5 * * * ?`) over a 15-minute lookback window, with a 900s (`retrigger_seconds: 900`) re-notification interval. Cooldown is enforced per device, per tier, per 15-minute tumbling window in `silver_realtime.py:149-160` (`clinical_alert_candidates`). Per-tier cooldown isolates WARNING from URGENT/CRITICAL alerts, so an earlier WARNING does not suppress a later higher tier. The SQL resource always deploys with `pause_status: PAUSED`, including when `ALERT_EMAIL` is set. `05-deploy-bundle.sh` passes the recipient but does not activate the alert; `06-run-and-gate.sh` unpauses only the stream job. An enabled SQL alert requires a registered Databricks workspace recipient (D7). Its activation policy remains the open AlertEngine decision.
- **Verification Commands**: See [Verification §4](#4-orchestrator-backend-add-on--quality-model-tests).
- **Known Limits**: Email dispatch requires that the recipient email domain accepts external mail and that the tenant Exchange Online connector has required dispatch permissions. The live device lookup reads a single FHIR search page and requests up to 100 associations. A search with another page or an inconsistent total fails instead of selecting from incomplete results.
- **Status**: Implemented. Verified by [Verification §4](#4-orchestrator-backend-add-on--quality-model-tests). Open: AlertEngine (see [AlertEngine](#alertengine)).

---

### Component 10: Local Orchestrator Backend & Process Engine (`orchestrator/local_server.py`, `orchestrator/activities/`)
- **Purpose**: FastAPI web service providing local and hosted control plane: deployment execution, process supervision, streaming logs via SSE, preflight validation, SQLite persistence, and continuation logic.
- **Entry Points**:
  - `orchestrator/local_server.py`: Primary FastAPI application.
  - `orchestrator/activities/invoke_powershell.py`: Process supervisor and structured log parser.
  - `orchestrator/activities/addons.py`: Add-on background task runner.
  - `orchestrator/shared/database.py`: SQLite deployment registry.
  - `orchestrator/shared/hosted.py`: Hosted authentication and sandbox helpers.
  - `orchestrator/shared/runtime_paths.py`: Runtime persistent paths resolution.
- **Inputs and Configuration**:
  - Port: `PORT` environment variable, default 7071.
  - Directories: `DATA_DIR` defaults to `orchestrator/` (overridden by `HLS_DATA_DIR`), `HLS_SHARED_DATA_DIR` (`/data-share` in hosted), `AZURE_CONFIG_DIR`. State file is `$HLS_DATA_DIR/.orchestrator-state.json`.
  - Database file (`orchestrator/shared/database.py`): Without `HLS_DATA_DIR`, the live SQLite file (`DB_PATH`) is `orchestrator/shared/orchestrator.db`. With `HLS_DATA_DIR`, `DB_PATH` is `orchestrator.db` in a new local temp directory (`tempfile.mkdtemp(prefix="hls-orch-")`), and `$HLS_DATA_DIR/orchestrator.db` (`BACKUP_PATH`) is a snapshot copy. At import, an existing snapshot is copied to `DB_PATH`. `backup_database` writes a new snapshot:
    - from the `sqlite-backup` thread (`_backup_worker`), which checks every 10 seconds and writes only after a commit;
    - from `shutdown_database` at process exit (`atexit`);
    - from the `orchestrator/local_server.py` fatal-signal handler before the backend exits.
  - API endpoints (`@app` decorators in `orchestrator/local_server.py`, plus `orchestrator/shared/hosted.py` `install_hosted_routes`):
    - Deploy: `POST /api/deploy/start`, `POST /api/deploy/preflight`, `GET /api/deploy/check-existing`, `POST /api/deploy/{instance_id}/cancel`, `DELETE /api/deploy/{instance_id}`.
    - Resume and add-ons: `POST /api/deploy/{instance_id}/continue-failed` (resume generic failed run), `POST /api/deploy/{instance_id}/continue-phase7` (Phase 7 resume), `POST /api/deploy/{instance_id}/addons`, `POST /api/deploy/{instance_id}/addons/databricks/continue` (Databricks add-on resume).
    - Run status and reports: `GET /api/deploy/{instance_id}/status`, `/logs`, `/logs/stream` (SSE), `/cloud-state`, `/deployed-resources`, `/after-action-report`; `POST /api/deploy/{instance_id}/validate`.
    - Deployment history: `GET /api/deployments`, `POST /api/deployments/clear`.
    - Teardown: `POST /api/teardown/start`, `POST /api/teardown/batch/start`, `GET /api/teardown/batch/{batch_id}`, `GET /api/teardown/{instance_id}/cloud-state`, `POST /api/teardown/{instance_id}/validate`, `POST /api/teardown/reconcile`.
    - Dismissed teardowns: `GET /api/dismissed-teardowns`, `POST /api/dismissed-teardowns/{instance_id}`.
    - Scan: `GET /api/scan/subscriptions`, `GET /api/scan/resources`, `POST /api/scan/resources/start`, `GET /api/scan/resources/{scan_id}`, `GET /api/scan/fhir-regions` and `GET /api/scan/ahds-regions` (one handler), `GET /api/scan/capacities`.
    - Capacity: `POST /api/capacity/pause`, `POST /api/capacity/resume`, `GET /api/deployment-capacity/{rg_name}`.
    - Locks: `GET /api/locks`, `POST /api/locks/{resource_id:path}`, `DELETE /api/locks/{resource_id:path}`.
    - Form history: `GET /api/form-history/{field}`, `POST /api/form-history/{field}`.
    - Stage ETAs: `GET /api/stage-etas`.
    - Health and auth context: `GET /api/live`, `GET /api/health`, `GET /api/auth/context`, `GET /api/auth/live`.
    - Hosted sign-in and activity (`install_hosted_routes`): `GET /api/hosted/activity`, `GET /api/hosted/whoami`, `GET /api/auth/state`, `PUT /api/auth/target`, `POST /api/auth/device-login`, `GET /api/auth/device-login/{session_id}`, `POST /api/auth/device-login/{session_id}/cancel`, `POST /api/auth/logout`.
    - Web UI: when `orchestrator-ui/dist` exists, `/` serves it (`_SPAStaticFiles`); paths under `api/` never fall back to `index.html`.
- **Behavior Contract**:
  1. **Process Supervision & Process-Group Cancel Guards**: Spawns `Deploy-All.ps1` in an isolated process session (`start_new_session=True` on POSIX). Cancellation (`POST /api/deploy/{id}/cancel`) or server shutdown invokes `_kill_process_group(pid, grace_seconds)`. The cancel guard checks `pgid = os.getpgid(pid)`; it refuses to kill if `pgid == os.getpgrp()` (the server's own process group) or if `pgid != pid` (the process does not lead its group). It sends `SIGTERM` via `os.killpg(pgid, signal.SIGTERM)`, waits up to `grace_seconds` (verifying liveness with `_is_process_group_alive`), and escalates to `SIGKILL` via `os.killpg(pgid, signal.SIGKILL)` if the process group remains alive.
  2. **Preflight Output Parsing**: `run_preflight` parses the final JSON document from PowerShell stdout and logs structured parse failures cleanly.
  3. **Stage-ETA Learning & Pooling**: Implemented in `orchestrator/shared/stage_eta.py` and exposed via `GET /api/stage-etas`. The backend records durations of succeeded phases and add-ons in `$HLS_DATA_DIR/stage_eta_samples.json` with a bounded sample list per stage (`MAX_SAMPLES_PER_STAGE`). Writes are atomic via temporary files and `os.replace`. Hosted sandboxes pool peer samples read-only by scanning subdirectories in `HLS_SHARED_DATA_DIR`, with a size cap on peer file reads. `GET /api/stage-etas` returns `median_minutes` and `sample_count` for every canonical stage. The backend applies no sample threshold. The deploy wizard (`orchestrator-ui/src/pages/DeployWizard.tsx` `getEstimatedDurationDetails`) and the run ETA (`orchestrator-ui/src/stageMapping.ts` `calculateEta`) use a learned median only when `sample_count >= 3`; otherwise they use the built-in estimate.
  4. **Shared Volume (`/data-share`) Architecture & Isolation**: Hosted Container App environments mount a shared Azure Files volume (`/data-share` via `HLS_SHARED_DATA_DIR`). Each reader serves a recorded owner requirement:
     - Stage-ETA pooling: owner instruction 2026-10-27 (keep stage ETAs in memory on the orchestrator tenant so duration estimates are accurate across runs).
     - Peer-history import: owner design answers 2026-10-26 (sync deployment history by portal user and target tenant/subscription; import only after verified sign-in).
     - Hosted Rayfin seed cache: owner decision Q8 (accelerate image conversions across ephemeral sandboxes).
     Cross-sandbox isolation relies on application code: peer SQLite databases are opened read-only, import requires matching tenant and subscription, and Azure credentials are encrypted per user with AES-256-GCM. `import_target_history_from_shared_storage` (`orchestrator/shared/database.py`) requires both target IDs and checks each peer deployment or teardown record on its own. A record names its target in up to three places: `customStatus` (`expectedTenantId`, `subscriptionId`), `customStatus.deployConfig` and the root `config` column (`expected_tenant_id`, `expected_subscription_id`). `customStatus` must be a mapping. `deployConfig` is absent only when its key is missing, and the root `config` only when the column is SQL NULL; any other stored value, including JSON `null`, `[]`, `""`, `0`, `false` or unreadable text, is malformed. An empty mapping is valid but holds no pair. Each ID field must be missing, `null` or a string; a blank string counts as missing, and any other type is malformed. IDs are compared after trimming and lowercasing. A record is imported only when at least one of these places holds both the same tenant and the same subscription, and every other non-empty tenant or subscription field in the record names the same target. A record is never imported when any place is malformed (a matching pair elsewhere does not excuse it), when its fields disagree, when its tenant and subscription appear only in different places, when it has no complete pair, or when it was rebuilt from a ledger (`customStatus.reconciledFrom` is `state-tracking`), because the IDs of a rebuilt record were inferred from a sign-in. The import copies the per-run log of each imported record and derives form history only from the imported records; it copies no other peer form history. State-tracking ledgers (`.deployment-state-<workspace>.json`) record no tenant or subscription, so no peer ledger is copied or rebuilt, even when its workspace name matches an imported run. Ledger recovery stays local: at startup each sandbox rebuilds missing records only from its own state-tracking directory. Peer ledgers and peer databases are never changed or deleted, and history imported under the earlier rules is not deleted. The import returns `importedDeployments` and `importedFormHistory`. The shared mutable volume is documented as an open architectural question (see [DataShare](#datashare)).
  5. SQLite resilience: The live database uses WAL mode on local temp storage, so no WAL file lives on the SMB share. `backup_database` writes the snapshot atomically: the SQLite backup API writes a local copy, the copy goes to `orchestrator.db.tmp` beside the snapshot, and `os.replace` moves it to `$HLS_DATA_DIR/orchestrator.db` (`/data/orchestrator.db` in hosted sandboxes).
  6. **History Retains Active Local Work**: `DELETE /api/deploy/{instance_id}` returns HTTP 409 while the record has a live local add-on or teardown worker, or is a local Running/Pending record. `POST /api/deployments/clear` retains these records and clears eligible inactive history. Starting local add-ons on an imported record adopts it before reserving Pending and awaiting preflight. A failed preflight restores peer provenance when no local add-on task exists. Passive peer history remains removable and nonblocking. A live local worker takes precedence over imported provenance, and peer re-import cannot replace its record. Completed, Failed and Terminated history remains removable once its workers finish.
  7. **Recorded-Target Cloud Evidence**: Run-backed cloud-state, deployed-resource inventory, validation and live continuation reads use the run's recorded subscription, not the Azure CLI default. Cloud-state, inventory and validation endpoints return HTTP 409 when a legacy run records no subscription. Deep `check-existing` instead reports `liveValidated: false` without reading cloud resources. Workspace-only history with no Azure resource-group target also remains unverified. Resource-group and emulator evidence caches include the subscription. A failed or unreadable resource-group probe is unknown, not deleted, and is not cached as an absence.
     Resume sources follow the strict tenant-and-subscription pair rule in Behavior 4. Auto-resume ignores unmatched runs; an explicit foreign or unrecorded source returns HTTP 409 before add-on preflight or any cloud read, including in Phase 7-only mode. Ancestor inheritance stops at the first unmatched record. Successful phases from the same target remain reusable.
     Teardown validation never treats an unreadable Azure or Fabric inventory as deletion. Workspace, item and connection lookups read every page. A failed or malformed page makes the inventory unavailable, not absent or partially complete. Validation reports failed checks and names unreadable sides in `resources.unverified`. A confirmed absent workspace and an absent or empty resource group still pass.
  8. **Selected-Subscription Discovery**: When a scan supplies a subscription, Azure reads use that subscription, and Fabric, Kusto and Entra reads use its tenant's credential. Entra token failure never falls back to the CLI default tenant. Scans without a subscription retain ambient discovery. A failed Entra lookup is not evidence that no identities exist; the scan can return target-scoped stale evidence or no identities with an unavailable status.
- **Verification Commands**: See [Verification §4](#4-orchestrator-backend-add-on--quality-model-tests).
- **Known Limits**: The backend refuses to start a deployment, a teardown (single or batch), or an add-on run with HTTP 409 and the detail `Another deployment or teardown is active for this estate` while another local run targets the same Fabric workspace name or resource group name and is Running or Pending, has a live add-on worker (including under a Completed deployment), or has a live teardown worker. Names compare case-insensitively. Empty names never match. Passive imported peer-sandbox history (`customStatus.importedFrom` set, without a live local worker) and teardown-batch parent records (`customStatus.runType == "teardownBatch"`) do not block. The backend refuses a teardown batch as a whole, before any job starts, if any job collides with an active run or two jobs in the batch share a workspace or resource group name. Runs for different estates can run at the same time in one orchestrator or sandbox. A running teardown cannot be cancelled, because its deletion cannot be interrupted. In hosted mode, Azure sign-in and target changes stay refused while any run is active.
- **Status**: Implemented. Verified by [Verification §4](#4-orchestrator-backend-add-on--quality-model-tests). Open: DataShare (shared mutable /data-share volume trade-off; see [DataShare](#datashare)).

---

### Component 11: Orchestrator Web User Interface (`orchestrator-ui/`)
- **Purpose**: Responsive Material 3 single-page application providing guided deployment wizard, interactive preflight validation, real-time phase monitoring, and history tracking.
- **Entry Points**:
  - `orchestrator-ui/src/pages/DeployWizard.tsx`: Deployment wizard page.
  - `orchestrator-ui/src/pages/PhaseMonitor.tsx`: Progress monitor and streaming log viewer.
  - `orchestrator-ui/src/pages/Preflight.tsx`: Prerequisite validation page.
  - `orchestrator-ui/src/components/HostedSignIn.tsx`: Device-code authentication flyout component.
  - `orchestrator-ui/src/pages/TeardownView.tsx`: Resource discovery, estate selection, and teardown controls.
  - `orchestrator-ui/src/mockDeployment.ts`: Browser-only mock deployment and teardown simulator.
- **Inputs and Configuration**:
  - Build tool: Vite + React 18 + TypeScript.
  - UI libraries (`orchestrator-ui/package.json`): MUI (`@mui/material`, `@mui/icons-material`) with Emotion (`@emotion/react`, `@emotion/styled`), Griffel (`@griffel/react` `makeStyles`), React Router (`react-router-dom`), and SheetJS `xlsx` from the CDN tarball `https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz` (Excel export in `orchestrator-ui/src/pages/PhaseMonitor.tsx`).
  - Serves from `/` on orchestrator port 7071 (or gateway domain).
- **Behavior Contract**:
  1. Wizard flow: Connect -> Configure -> Validate -> Review -> Deploy.
  2. **Device Sign-in Control**: Displays "Next: Copy code & open Microsoft sign-in" as a primary button that copies the user code and opens Microsoft sign-in in a new tab, with a separate "Copy code" button, an outlined warning-colored "Request new token" button to restart pending sign-in if the code is rejected, "Refresh sign-in status", and "Sign out of Azure tools".
  3. Preflight errors: Displays clean error messages extracted from FastAPI 422 bodies via `errorMessageFromBody` rather than `[object Object]`.
  4. Stage progress: Consumes SSE stream (`/api/deploy/{id}/logs/stream`) rendering real-time phase markers `@@PHASE|<Phase>|<Label>|<StepCount>@@` and stage ETAs.
  5. Teardown scan controls and candidate rows wrap at narrow widths. Workspace names remain readable, and row actions remain visible, without page-level horizontal scrolling at 360 px. Refused single or batch starts display the server error and remain on the teardown page without opening a monitor.
  6. **Run-Bound Cloud Evidence**: Cloud-state and validation results belong to a run ID and run type. Switching runs does not show the previous run's passing checks. Failed cloud reads clear previous success, show neutral `unavailable` chips and an inline error, and do not infer Azure resource-group success from a Completed local run. A later successful read replaces the error. Validation failures appear in the resource-state card. Late replies from an earlier run are ignored. Cloud-state polling allows only one logical request at a time and retains the existing 10-second teardown and 30-second deployment cadence.
  7. **Mock Deploy (UI preview only)**: The wizard's "Mock Deploy" button (tooltip: no Azure/Fabric resources created) starts `startMockDeployment` in `orchestrator-ui/src/mockDeployment.ts` and opens the monitor for a `mock-` instance. The browser generates the phases, logs and timing from fixed scripts and keeps the instance in browser memory; the orchestrator API is not called. A blank workspace name is filled with a demo name. Mock output is a UI preview, not deployment evidence or live proof (`orchestrator-ui/src/pages/DeployWizard.tsx:1589-1598,2649-2653`).
  8. **Teardown demo data (UI preview only)**: "Use demo data" on the teardown page shows generated candidates (`scanForTeardownCandidates`) with a demo-mode notice and mock-data banner; it never lists live resources. Starting teardown on those candidates runs `startMockTeardown` in the browser and opens the teardown monitor; no teardown request is sent. A mock teardown is not teardown evidence (`orchestrator-ui/src/pages/TeardownView.tsx:385-395,507-512,770,791-795`).
- **Verification Commands**: See [Verification §6](#6-frontend-web-ui--app-verifications).
- **Known Limits**: Build requires Node.js 18+; UI dist is served statically by FastAPI.
- **Status**: Implemented. Verified by [Verification §6](#6-frontend-web-ui--app-verifications). Open: none.

---

### Component 12: Hosted Orchestrator & Gateway Architecture (`hosted/gateway/`, `hosted/sandbox/`, `hosted/infra/`, `hosted/Deploy-HostedOrchestrator.ps1`)
- **Purpose**: Multi-tenant hosting architecture running the orchestrator inside Azure Container Apps behind an authenticating reverse proxy gateway.
- **Entry Points**:
  - `hosted/gateway/app.py`: Gateway FastAPI web service and reverse proxy.
  - `hosted/gateway/policy.py`: Access rules, allowlist evaluation, and reaper calculations.
  - `hosted/gateway/lifecycle.py`: Container Apps sandbox manager.
  - `hosted/sandbox/Dockerfile`: Hardened sandbox container image definition.
  - `hosted/sandbox/entrypoint.sh`: Sandbox initialization script and hotfix unpacker.
  - `hosted/infra/main.bicep`: Infrastructure as Code ARM template.
  - `hosted/Deploy-HostedOrchestrator.ps1`: Operator release and deployment automation.
  - `hosted/HostedDeployHelper.psm1`: Profile and domain resolution helpers.
  - `hosted/profiles/example.psd1`: Template deployment profile. Operator profiles stay outside Git (`.gitignore` excludes every other `hosted/profiles/*.psd1`).
- **Inputs and Configuration**:
  - Public URL: `https://hls.jbatl.dev`.
  - Azure target: `-SubscriptionId` and `-TenantId` (both required; from the parameter or the deployment profile, otherwise the script stops), `-ResourceGroup` (default `rg-hls-deployer`) and `-Location` (default `westus2`). Explicit parameters override profile values (`hosted/Deploy-HostedOrchestrator.ps1:4-7,39-42,61-62`).
  - Gateway: `hls-gateway` with external HTTPS ingress and custom domain.
  - Sandboxes: `hls-sbx-{user.key}` (where `user.key` is first 12 hex chars of SHA256(`tid:oid`)), 2 vCPU / 4 GiB, max 5 concurrent.
  - `-DeploymentProfile`: A profile name resolved under `hosted/profiles/` or a path to a `.psd1` file (relative, absolute, or `~`). Operator profiles live outside Git (`hosted/profiles/example.psd1` is the template; see `hosted/README.md`).
  - `-GitHubRepo`: GitHub repository (`<owner>/<repo>`), verified with `gh` admin access.
  - `-DnsZone`: Cloudflare DNS zone for automated custom domain DNS.
  - Parameterized names: `-Registry`, `-Vault`, `-Storage`, defaulting to deterministic names (`acrhls<hash>`, `kv-hls-<hash>`, `sthls<hash>`).
  - Access policy parameters: `-AllowedDomains`, `-AllowedUsers`, `-AllowedTenants`.
  - Switches: `-SkipImages`, `-SkipInfra`, `-BootstrapEntra`, `-PublishWardflowBundle`.
  - `-WardflowCommit`: 40-character commit SHA or `none`.
  - `-WardflowPath`: WardFlow git checkout used to build a non-empty bundle (parameter or profile). See Behavior 5.
  - `-CustomDomain` and `-ClientId` (default `$env:HLS_CLIENT_ID`); both can also come from the profile.
  - `-ImageTag`: Specific container image tag to deploy.
- **Behavior Contract**:
  1. **Access Policy & Admission Rules**: Admission evaluates the boolean rule (`hosted/gateway/policy.py:104-105`): user is admitted iff `((tid, oid) in HLS_ALLOWED_USERS or (tid, email) in HLS_ALLOWED_USERS or tid in HLS_ALLOWED_TENANTS)`.
     - **MSAL Authority & Token Claims**: MSAL authority is configured as `https://login.microsoftonline.com/organizations`. Tokens issue from the user's home organization; the ID token provides:
       - `tid`: Tenant ID of the user's authenticating home tenant (`claims.get("tid")`).
       - `oid`: Object ID of the user in that tenant (`claims.get("oid")`).
       - `email`: User email from `preferred_username`, `email`, or `upn` claim.
     - **Admission Evaluation Categories**:

       | User Category | ID Token `tid` | Evaluation Rule | Outcome |
       |---|---|---|---|
       | **Microsoft Corporate Employee** | `72f988bf-86f1-41af-91ab-2d7cd011db47` | Matches Microsoft corporate tenant in `HLS_ALLOWED_TENANTS` (or `(tid, email)` in `HLS_ALLOWED_USERS`). | **Admitted** |
       | **External B2B Guest in Microsoft Tenant** | User's home tenant GUID | Token issued by user's home tenant has home `tid`, not Microsoft `tid`. Does NOT match Microsoft tenant in `HLS_ALLOWED_TENANTS`. | **Denied** (unless explicit `(home_tid, guest_oid)` or `(home_tid, guest_email)` is in `HLS_ALLOWED_USERS`) |
       | **Guest Whose Home Tenant is Allowlisted** | User's home tenant GUID | User's home `tid` matches `HLS_ALLOWED_TENANTS` (or resolved via `-AllowedDomains`). | **Admitted** |

     - **Reference Deployment**: The reference deployment at `https://hls.jbatl.dev` admits accounts whose home tenant is the Microsoft corporate tenant `72f988bf-86f1-41af-91ab-2d7cd011db47` (`microsoft.com` accounts), plus operator accounts set in `HLS_ALLOWED_USERS`.
     - **Self-Hosted Deployments**: Teams deploying their own orchestrator approve domains via `-AllowedDomains`. At deploy time, each domain resolves to an Entra tenant ID through OpenID discovery (`https://login.microsoftonline.com/<domain>/v2.0/.well-known/openid-configuration`), and approving a domain admits that whole tenant. Consumer Microsoft-account tenants (`9188040d-6c67-4c5b-b112-36a304b66dad` and `f8cdef31-a31e-4b4a-93e4-5f571e91255a`) are refused by design. Teams can also approve tenants (`-AllowedTenants`) or individual users (`-AllowedUsers`) directly. Forked deployments receive no default allowlist.
  2. **Allowlist Precedence & Redeploy Authority**: On redeploy, if `HLS_ALLOWED_USERS` or `HLS_ALLOWED_TENANTS` exists in the live gateway environment, the script preserves the live allowlists unless explicit `-AllowedUsers`, `-AllowedTenants`, or `-AllowedDomains` parameters are passed. Empty live allowlists are preserved. Profile `AllowedDomains` is not applied on redeploy unless `-AllowedDomains` is passed explicitly.
  3. **Gateway Registry Resolution**: The gateway extracts the container registry hostname directly from `HLS_SANDBOX_IMAGE` (`registry_server_for(settings.sandbox_image)`) instead of requiring a separate registry environment variable.
  4. **Image Tag Reuse & Rebuilds**: With `-SkipImages` and no `-ImageTag`, the script reuses the live gateway and sandbox images from the running Container Apps without rebuilding. When rebuilding, the sandbox image build uses `node:22-bookworm-slim` for the UI build stage.
  5. **WardFlow Bundling**: `-WardflowCommit none` packages an empty bundle `hls-wardflow-bundle:none` for forks without WardFlow. A non-empty bundle requires `-WardflowPath`; the script stops if the path is missing. When a bundle is needed (`-PublishWardflowBundle`, or images are built without a commit) and `-WardflowPath` is set, the path must be a git checkout, and its `HEAD` becomes the commit when `-WardflowCommit` is not given. With no commit, the script uses `none` (`hosted/Deploy-HostedOrchestrator.ps1:640-662`). Bundling runs `git archive` on only `caldova-cardio` (the separate Caldova snapshot) and `rayfin-wardflow-persona-app` at the commit, halting if either path is missing there (`:355-371`). `-PublishWardflowBundle` also sets the GitHub repository variable `WARDFLOW_REF` when `gh` reports admin access; otherwise it prints a warning to set it manually. For `none`, an existing 40-character `WARDFLOW_REF` is kept, so later CI releases that read the repository variable keep using that commit's bundle (`:380-403,712`). When an image build finds no `none` bundle in the registry, it builds one without touching the variable; a missing commit bundle stops the deployment (`:716-722`).
  6. Header sanitization: Strips incoming `x-hls-*` headers and injects trusted identity headers (`x-hls-user-email`, `x-hls-user-oid`, `x-hls-user-tid`, `x-hls-gateway-key`).
  7. Single device-code sign-in: Spawns `az login --use-device-code` in sandbox; automatically delegates token context to Az PowerShell, eliminating double login.
  8. Auth seal: Encrypts MSAL refresh tokens and subscription profiles to `/data/.encrypted-azure-auth.bin` using AES-256-GCM. HKDF-SHA256 derives the current key from the per-sandbox `HLS_GATEWAY_KEY` and the user's `tid:oid`. Only the current key, the `HLS2` envelope and payload version 2 are accepted; the envelope version is not the key-derivation version. There is no legacy-key migration. An invalid or foreign seal requires a new Azure sign-in. Sealing and restore accept only a complete sign-in: a profile whose `subscriptions` value is a list of objects (an empty list is valid, as with `az login --allow-no-subscriptions`; deploy preflight reports missing subscriptions) and an MSAL cache with a non-empty `RefreshToken` section in which every entry has a non-empty string `secret`. Incomplete CLI state never replaces an existing seal, and a decrypted payload that is incomplete is deleted without touching the active CLI files. Restored files and the seal are written as owner-only temporary files and then swapped in; temporary files are removed on failure. Seal writes, restore, sign-out and the startup sweep serialize on an exclusive-create lock file (`.encrypted-azure-auth.bin.lock`) beside the seal, because the share is mounted with `nobrl` and byte-range locks are not shared between sandboxes. The lock file holds its owner's random token; if writing the token fails, the lock file is removed. A lock older than 60 s is treated as abandoned. A lock is deleted, both when a stale lock is broken and when a holder releases its own lock, only by the winner of an exclusive-create election file named after that lock instance, which re-checks the instance before deleting it, so two waiters never hold the lock at once. The 60 s limit is a lease, not full exclusion: a holder stalled for more than 60 s inside its critical section can lose the lock to a waiter while it is still running. A lock create that fails with "not found" while the directory exists (SMB delete-pending) is retried within the timeout; a missing directory fails at once. Every single wait is bounded: 10 s for the seal lock, 10 s for the in-sandbox write guard, 2 s per peer for the sweep. Sealing and sign-out can each make two waits in sequence (the seal lock, then the write guard), so either can take about 20 s; a write-guard timeout is never retried as a lock failure. Sealing reads and validates the CLI files while holding the lock. Sign-out removes the active CLI files first, then invalidates every in-flight seal in the sandbox and deletes the seal; a sealer that read credentials before sign-out and has not started writing writes nothing. If a seal write of this sandbox is still in flight when sign-out stops waiting for the write guard, that write deletes its own file when it lands, and `/api/auth/logout` returns HTTP 503 with `Retry-After: 10` and advice to sign out again instead of `signed_out`; a retry succeeds once the write has finished. A crash between that late write landing and its cleanup can leave a seal behind, which is why sign-out does not report success while the write is in flight. Async callers run lock-taking work with `asyncio.to_thread` so the event loop never blocks. When the lock is unavailable, restore and the sweep leave the seal in place, sealing keeps the old seal, and sign-out deletes the seal anyway. Startup also removes peer seals whose readable four-byte headers identify an unsupported format. Read failures, truncated peer headers and denied lock creation are retained and logged; token contents are never logged. This cleanup is not filesystem isolation.
  9. **Security Model & Shared Storage**: Every sandbox mounts the entire `sandboxes` Azure Files share at `/data-share` (in addition to its own user-key subdirectory at `/data`). Cross-user isolation of history files relies on application code (peer SQLite databases are inspected read-only, importing only for a verified matching tenant+subscription), while Azure credentials are sealed with the per-sandbox key. This shared volume visibility is a known architectural limit.
  10. **Hosted-Only Shared Seed Cache**: In hosted mode (`HLS_HOSTED=1`), Rayfin imaging first looks for complete lakehouse and volume manifests in the settings-keyed cache under `/data-share/rayfin-imaging-cache` (or the matching legacy default cache). On a miss, it downloads and builds missing imaging artifacts, then attempts to populate the shared cache for later runs. Non-hosted runs never read or write this shared cache. Both modes can reuse artifacts already present in the persistent per-instance working copy instead of downloading or converting them again.
  11. **Idle Reaper**: Implemented in `hosted/gateway/policy.py` (`reaper_decision`). Eviction requires both gateway traffic (`last_seen`) and sandbox activity (`last_activity`) to be older than `HLS_IDLE_MINUTES` (default 120 minutes) and zero `active_runs`. An unreachable sandbox records `unreachable_since`; it is evicted only after `unreachable_since` exceeds `HLS_IDLE_MINUTES` (`(True, "unreachable beyond idle limit")`); while within the window it returns `(False, "unreachable; grace period")`. A malformed activity response (`active_runs` not a non-negative int) returns `(False, "invalid activity response")`. An unparseable `last_activity` timestamp returns `(False, "invalid activity timestamp")`. Known limit: a deployment run inside a sandbox that remains unreachable for longer than `HLS_IDLE_MINUTES` is lost.
- **Verification Commands**: See [Verification §2, §3](#2-infrastructure-as-code-bicep-validation).
- **Known Limits**: Cold-start sandbox provisioning takes 30–60 seconds; storage share is shared across sandboxes.
- **Status**: Implemented. Verified by [Verification §2, §3](#2-infrastructure-as-code-bicep-validation). Open: none.

---

### Component 13: Optional Add-ons Architecture (Databricks, Rayfin Applications & Cardiology)
- **Purpose**: Extends core HLS deployment with Azure Databricks Lakeview analytics, Rayfin clinical web applications, and Caldova cardiology clinical decision support.
- **Entry Points**:
  - `orchestrator/activities/addons.py`: Add-on execution runner.
  - `azure-databricks/implementation/scripts/`: Databricks foundation, bundle, and validation scripts.
  - `azure-databricks/implementation/bundle/databricks.yml`: Databricks Asset Bundle definition.
  - `azure-databricks/implementation/bundle/resources/dashboards.yml`: AI/BI Lakeview dashboards definition.
  - `rayfin-imaging/`: Multimodal pathology and radiology viewer app.
  - `rayfin-health-command-center/`: Hospital operations command center app.
  - `rayfin-clinical-triage-app/`: Real-time bedside triage app.
- **Inputs and Configuration**:
  - Add-on toggles: `deploy_databricks`, `deploy_rayfin_apps`, `deploy_cardiology`.
  - Serialized execution order: `cardiology` -> `rayfin` -> `databricks` (`ADDON_FLAGS`).
  - Environment variable: `WARDFLOW_ROOT`.
  - Add-on subfeatures: `seed_tcga_cohort`, `enable_alert_stopwatch`, `verify_databricks_interop` default to enabled; `enable_researcher_persona` requires explicit opt-in. The enabled-by-default flags accept an absent value, `None`, `True`, or trimmed case-insensitive strings `true`, `1`, `yes`; other values disable them. The researcher flag accepts only `True` or those strings. `researcher_persona_nurse_upn` optionally selects the nurse identity; otherwise the runner uses the deployer UPN.
- **Behavior Contract**:
  1. Post-completion independence: Add-ons execute only after core Phases 1–7 complete; add-on failures do not invalidate the core deployment.
  2. **WARDFLOW_ROOT Resolver**: `resolve_wardflow_root` in `orchestrator/activities/addons.py` searches in order:
     (a) `WARDFLOW_ROOT` environment variable when set (if set to an empty path, raises `RuntimeError("WARDFLOW_ROOT environment variable is set to an empty path")`; if set to a non-existent path, raises `RuntimeError` naming the variable and path);
     (b) sibling checkout `../wardflow` next to the HLS repository root;
     (c) worktree parent sibling `root.parent.parent / "wardflow"` when repository sits under `.worktrees/`;
     (d) legacy developer path `$HOME/git/.worktrees/wardflow-jb-dev`.
     If none exist, returns `None`. When WardFlow is absent, Rayfin skips the persona app with an informational warning and proceeds; cardiology fails fast with an actionable error naming `WARDFLOW_ROOT`.
  3. **Add-on Run Warnings**: Add-on warnings are cleared at the start of each run (`state.pop("warnings", None)`). Non-fatal warnings (such as Databricks alert recipient warnings when the user is not a registered workspace user, or SpO2 alert stopwatch probe warnings) are recorded under `customStatus.addons.<name>.warnings` and surfaced in add-on status.
  4. Rayfin imaging cache: only hosted runs (`HLS_HOSTED=1`) use the shared cache on `/data-share`; a cache miss builds the missing artifacts and attempts to populate it. Non-hosted runs do not access the shared cache. Both modes can reuse manifests and artifacts in their persistent per-instance working copy.
  5. Rayfin publishable keys: Client-side keys (`publishable_key` in `rayfin.yml`) are stripped for fresh deployments.
  6. **Rayfin Imaging Lint**: `rayfin-imaging` uses an ESLint 9 flat configuration (`rayfin-imaging/eslint.config.js`) with `@eslint/js` and `typescript-eslint`.
  7. With `seed_tcga_cohort` enabled and either the Patient 360 seed script or `resource_group_name` present, Rayfin imaging seeds synthetic TCGA FHIR patients and baseline telemetry, exports them to `fhir-export`, runs the HDS clinical ingestion pipeline and reporting notebook, checks Silver TCGA patients, and refreshes Gold SQL metadata. Each Fabric ingestion job has a 3600 s timeout. Researcher opt-in creates the persona and seeds the de-identified clinical silo.
  8. With `enable_alert_stopwatch` enabled and a non-empty `alert_email`, Rayfin imaging deploys the clinical Activator and runs the live SpO2 stopwatch. A missing email skips these steps. Lookup or subprocess failures fail the add-on; warnings do not hide those failures.
  9. With `verify_databricks_interop` enabled, Databricks relists workspace items after deployment validation and runs `azure-databricks/implementation/scripts/09-onelake-interop-proof.py --live`. Missing `clinical_lakehouse`, `imaging_lakehouse` or `patient360` marks this step skipped with a warning and instructions to deploy Rayfin and rerun Databricks.
  10. Rayfin provisions its backend and runtime settings before building. It runs the configured static build in its configured directory through Bash with `pipefail`, with shell operators and quoting preserved, using a Power BI token. A nonzero build exit or failed pipeline stops publication. It publishes static and enabled function assets with native service-specific CLI commands, and registers the observed hosting origin through `scripts/register_rayfin_hosting_origin.mjs`. Registration uses the installed CLI's settings helper, preserves recorded non-auth runtime settings, checks the active item and workspace, and reads back the redirect allowlist. Failure stops the add-on. These post-provision steps do not reapply the data model. Cardiology also uses the required helper for its final origin registration.
- **Verification Commands**: See [Verification §4, §5, §6](#4-orchestrator-backend-add-on--quality-model-tests).
- **Known Limits**: Add-ons run serially, so their runtimes accumulate. Cardiology requires the Caldova snapshot (`caldova-cardio/`) from the private WardFlow repository. The native origin helper uses internal exports from the installed Rayfin CLI; an incompatible package upgrade fails registration rather than skipping it. An existing command-center database with its custom publication guard can reject the initial full schema provision with `Schema drift detected`; asset-only publishing preserves that guard, but does not migrate a changed data model.
- **Status**: Implemented. Verified by [Verification §4, §5, §6](#4-orchestrator-backend-add-on--quality-model-tests). Open: none.

---

### Component 14: Multi-Tenant Teardown Engine (`Teardown-All.ps1`, `orchestrator/shared/full_teardown.py`)
- **Purpose**: Deterministic, subscription-pinned teardown of Azure, Fabric, and Databricks resources created by a deployment, protecting shared infrastructure.
- **Entry Points**:
  - `Teardown-All.ps1`: Interactive and headless operator CLI script.
  - `orchestrator/shared/full_teardown.py`: Core ownership-aware planning and deletion engine.
  - `orchestrator/shared/teardown_scan.py`: Candidate discovery and filtering.
- **Inputs and Configuration**:
  - `-SubscriptionId`: Deployment subscription. Required unless `HLS_SUBSCRIPTION_ID` or the deployment state file supplies it; the script aborts if none resolve (default az account subscription is never used).
  - `-ExpectedTenantId`: Fails closed on mismatch.
  - `-FabricWorkspaceName`, `-ResourceGroupName`.
  - `-FrontEndResourceGroup`: Explicit front-end resource group(s) to remove.
  - `-DicomViewerResourceGroup`: Dedicated DICOM viewer resource group.
  - `-NoFrontEndDiscovery`: Skip automatic front-end discovery.
  - `-SkipAzure`: Skip Azure resource group deletion.
  - `-SkipFabric`: Skip Fabric workspace deletion.
  - `-Plan`: Dry-run preview without deleting resources.
  - `-Force`: Skip interactive confirmation prompt.
- **Behavior Contract**:
  1. **Pinning & Safety**: Refuses execution if subscription or tenant mismatch.
     - **Tag Rules**: A group is tied to the deployment when its `hls-deployment` tag (`DEPLOYMENT_TAG`) equals the deployment workspace name or main resource group name, compared case-insensitively (`_plan_front_ends`).
     - **Fabric Capacity Refusal**: `_judge_group` raises `TeardownRefused` for every candidate group, explicit or discovered, that holds a `PROTECTED_TYPES` resource (`microsoft.fabric/capacities`). This check runs before the explicit and discovered rules. Teardown stops in the Preflight phase.
     - **Explicit Groups (`-FrontEndResourceGroup`)**: `_judge_group` deletes an explicit group when it has at least one tie: a container app or job whose container environment values reference a deployment endpoint, or the `hls-deployment` tag. An explicit group without a tie raises `TeardownRefused` and halts teardown. An explicit group equal to the main resource group is not a front-end candidate. A group that does not exist is skipped.
     - **Discovered Groups (`_plan_front_ends`)**: Unless `-NoFrontEndDiscovery` is set, discovery considers only groups tied to the deployment: groups that hold a container app or job whose container environment values contain a tie value, and groups with a matching `hls-deployment` tag. Tie values are the Fabric workspace ID, the lakehouse SQL, warehouse, and Eventhouse hosts, the FHIR audience host, and the storage and Event Hubs hosts of the main group. `_judge_group` skips a discovered group when it holds a resource type outside `FRONT_END_TYPES`, or a container app or job (`COMPUTE_TYPES`) that is not tied while the group has no matching tag (`skip_reason = "shared resource group: ... not part of this deployment's front end; pass it explicitly to delete it"`). Otherwise it deletes the group.
     - **Control-Plane Safety**: No rule checks the group name `rg-hls-deployer`. Discovery considers that group only if it holds a tied container app or job or has a matching `hls-deployment` tag; the type rules above then apply. If an operator passes it explicitly, teardown deletes it when it has a tie and holds no `PROTECTED_TYPES` resource.
     - **Execution**: `Deploy-All.ps1 -Teardown` delegates directly to `Teardown-All.ps1` with `-Force` and never prompts for confirmation. `Teardown-All.ps1 -Plan` previews planned deletions without mutating resources.
  2. Ordered teardown (`DeploymentTeardown.run`): Preflight (plan; `-Plan` stops here) -> Front-End Apps (Rayfin apps) -> Databricks Unity Catalog -> Fabric Connections -> Workspace Identity -> Delete Workspace -> Front-End Entra Apps (cardiology app registrations owned by each deleted front-end group) -> Front-End Resource Groups -> Azure Resource Group (main) -> Verification. A phase runs only when it has a target. Verification always runs: it reads back every targeted workspace and resource group and fails if any still exists.
  3. **Orphaned Companion Cleanup**: Deletes orphaned companion items (`UserDataFunction` and `SQLDatabase`) for all known Rayfin apps (`KNOWN_RAYFIN_APPS`) even if the parent `AppBackend` was deleted previously.
  4. Capacity preservation: Teardown cleans items but does not pause or delete the shared Fabric capacity.
- **Verification Commands**: See [Verification §1, §4](#1-powershell-syntax-parallel-execution--retry-classification).
- **Known Limits**: Lakehouse/Eventhouse endpoints must be reachable to discover TDS/Eventhouse-only front ends; provide explicit `-FrontEndResourceGroup` if capacity is paused during teardown.
- **Status**: Implemented. Verified by [Verification §1, §4](#1-powershell-syntax-parallel-execution--retry-classification). Open: ESC-4 (opt-in capacity pause on teardown; see [ESC-4](#esc-4)).

---

### Component 15: Public Milestone Tickets & Roadmap (`specs/tickets/BOARD.md`)
- **Purpose**: Tracks modular capability milestones demonstrating zero-copy data virtualization, multimodal clinical imaging, and governed AI-assisted data retrieval across Fabric and Databricks.
- **Entry Points**:
  - `specs/tickets/BOARD.md`: Roadmap tracking board.
- **Status & Roadmap**:
  The roadmap of record is tracked in `specs/tickets/BOARD.md`. The table below summarizes shipped and unshipped demonstration milestones:

  | Ticket | Title | Status | Gap / Notes |
  |---|---|---|---|
  | `001-local-demo-dataset` | Local demo dataset | Shipped | 15 deterministic synthetic patient Parquet files across clinical, genomics, and imaging silos. |
  | `002-tcga-synthetic-ingest` | TCGA synthetic ingest | Shipped | Seeds multimodal records into clinical FHIR, DICOM metadata, and genomic variants without altering baseline Synthea. |
  | `003-zero-copy-proof` | Zero-copy proof | Shipped | Demonstrates clinical triage and imaging reading identical OneLake Delta tables without copying. |
  | `004-realtime-alert-stopwatch` | Real-time alert stopwatch | Shipped | Emits device telemetry drops and measures Fabric Activator alert latency within a 60-second budget. |
  | `005-data-agent-qa` | Plain-English Data Agent questions | Done (`BOARD.md`) | Exists: `rayfin-imaging/src/pages/AskDataAgent.tsx`, `scripts/verify_data_agent_qa.py`. Known gaps: `specs/tickets/005-data-agent-qa/results.md` records E-10 (live Data Agent answer) as FAIL; `scripts/verify_data_agent_qa.py` is an ad-hoc check, not in the deploy path. |
  | `006-phi-persona-views` | PHI persona views | Shipped | Enforces OneLake data access security, permitting nurse clinical views while masking researcher direct identifiers. |
  | `007-standards-view` | Standards view | Shipped | Validates mapping from HL7 FHIR and DICOM PS 3.10 formats into flattened Lakehouse silver tables. |
  | `008-imaging-hero` | Multimodal imaging hero | Shipped | Synchronized CT slices, pathology slides, and genomic mutation panels in Rayfin views. |
  | `009-plain-language-copy` | Plain-language copy pass + glossary | Done (`BOARD.md`) | Exists: `rayfin-imaging/src/lib/glossary.ts`, `rayfin-imaging/src/components/GlossaryTooltip.tsx`, `rayfin-imaging/scripts/audit_ui_copy.py`. Known gaps: none recorded. |
  | `010-databricks-interop` | Databricks lakehouse interop | Shipped | Databricks Serverless queries OneLake Delta tables via Unity Catalog external locations. |
  | `011-demo-packaging` | Demo packaging (60 s film, walkthrough, deploy timer, synthetic badge) | Done (`BOARD.md`) | Exists: `docs/demo/out/hls-fabric-demo-60s.mp4`, `docs/demo/WALKTHROUGH.md`, `docs/demo/render_demo.py`. Known gap: the film uses TTS narration (`docs/demo/VOICEOVER.md`, `docs/demo/assets/audio/voiceover.wav`). This contradicts the owner's later reversal; remove it before 011 ships. |
  | `012-orchestrator-wiring` | Orchestrator wiring for fresh deployments | Done (`BOARD.md`) | Exists: `orchestrator/activities/addons.py` (runs `scripts/manage_researcher_persona.py`), `orchestrator/tests/test_addons.py`. Known gaps: the researcher persona demo account needs a human MFA enrollment; the Data Agent Q&A check (`scripts/verify_data_agent_qa.py`) is an ad-hoc tool, not in the deploy path. |
  | `013-data-agent-live-fix` | Patient 360 Data Agent answers TCGA cohort questions live | Done (`BOARD.md`) | Exists: `phase-2/deploy-data-agents.ps1`, `scripts/verify_data_agent_qa.py`, `specs/tickets/013-data-agent-live-fix/evidence/`. Known gaps: the researcher persona demo account needs a human MFA enrollment; `scripts/verify_data_agent_qa.py` is an ad-hoc tool, not in the deploy path. |
- **Verification Commands**: See [Verification §4, §5](#4-orchestrator-backend-add-on--quality-model-tests).
- **Status**: Reviewed. Open: none.

---

## Alternatives

### 1. Monolithic Procedural PowerShell vs Modular Orchestration
- **Alternative**: Maintain a single large monolithic PowerShell script without a REST backend or modular activity runners.
- **Why it lost**: Monolithic scripts cannot support web UI progress streaming (SSE), cross-sandbox history sharing, hotfix archive injection, or fine-grained phase continuations.

### 2. Fabric Ontology v1 JSON Schema vs Ontology v2 TMDL
- **Alternative**: Continue using Microsoft Fabric Ontology v1 JSON schema definitions.
- **Why it lost**: Fabric IQ retired v1 JSON ontology APIs in favor of Tabular Model Definition Language (TMDL). TMDL enables version-controlled, declarative entity and relationship definitions with Direct Lake partition bindings (replacing deprecated v1 JSON APIs).

### 3. Container App Device Login vs Stored Service Principal Secrets
- **Alternative**: Require hosted portal users to supply long-lived Azure Service Principal client secrets.
- **Why it lost**: Storing external customer credentials introduces unacceptable security risk and credential management overhead. Single-device-code authentication with AES-256-GCM auth seals isolates credentials to ephemeral user sandboxes.

---

## Risks

| Risk | Severity | Impact | Mitigation |
|---|---|---|---|
| **Shared SMB Share Isolation** | High | Multi-user sandboxes mount the shared `sandboxes` volume at `/data-share`. Malicious or buggy container code could attempt cross-tenant file inspection. | Sandboxes run as non-root UID/GID 10001; peer SQLite databases are opened read-only; history import requires a matching target tenant and subscription; Azure credentials use per-sandbox keys derived from `HLS_GATEWAY_KEY` and user `tid:oid`. Legacy keys are not accepted. Rejected seals require a new sign-in. Seal writers and cleanup serialize on a cooperative lock file, so cleanup does not delete a seal that a writer just replaced; a holder stalled for more than 60 s can lose the lock. The shared mount remains an architectural limit. |
| **Fabric Capacity Billing Spike** | Medium | Continuous streaming telemetry and high-frequency claim generation accrue capacity consumption charges on paid Fabric F-SKUs. | Emulators are deployed as Azure Container Instances that can be stopped immediately; eval harness supports `--no-capacity-resume` to prevent unintended auto-resuming. |
| **Transient Cloud API Throttling** | Medium | Fabric REST API returns 403 `RequestDeniedByInboundPolicy` or 429 throttling during rapid resource provisioning. | `Test-P5FabricTransientError` retries transient 403, 429, and 5xx responses with linear backoff (`[Math]::Min(15 * attempt, 90)`), while generic steps use exponential backoff (`10 * 2^n`). |
| **Orphaned Compute Resources** | Medium | Front-end web apps or Databricks Unity Catalog bindings left behind after workspace deletion accrue storage and hosting costs. | `Teardown-All.ps1` executes dependency-ordered teardown, specifically purging orphaned companion items (`UserDataFunction`, `SQLDatabase`) for all `KNOWN_RAYFIN_APPS`. |

---

## Decisions & Assumptions

Columns: ID, Decision or assumption, Why, By (`human` = recorded owner instruction or answer; `agent` = design choice recorded by an agent from code).

| ID | Decision or assumption | Why | By |
|---|---|---|---|
| D1 | Access to `https://hls.jbatl.dev` evaluates the boolean rule: admitted iff `((tid, oid) in HLS_ALLOWED_USERS or (tid, email) in HLS_ALLOWED_USERS or tid in HLS_ALLOWED_TENANTS)`. MSAL authority is `https://login.microsoftonline.com/organizations`, and `tid` reflects the authenticating home tenant. Admits accounts whose home tenant is the Microsoft corporate tenant `72f988bf-86f1-41af-91ab-2d7cd011db47` (`microsoft.com` accounts), plus operator accounts set in `HLS_ALLOWED_USERS`. B2B guests are not admitted via tenant entry. | Restricts reference deployment to verified organization members while supporting operators. | human |
| D2 | Self-hosted deployments approve their own domains via `-AllowedDomains` (each domain resolves to its Entra tenant through OpenID discovery at deploy time; approving a domain admits that whole tenant; consumer Microsoft-account tenants are refused), `-AllowedTenants`, `-AllowedUsers`, or profile PSD1 files; forks receive no default allowlist. Fresh deployments with an empty allowlist stop. There is no gateway-side domain rule. | Ensures forks fail closed without inheriting hardcoded operator identities. | human |
| D3 | Fabric IQ Ontology uses v2 TMDL format (`phase-4/build_ontology_v2.py`) with Direct Lake partitions. | Replaces deprecated Fabric IQ v1 JSON ontology schema and aligns with Fabric IQ GA platform standards. | agent |
| D4 | Bedside Activator alerts run only on full platform or standalone `-Phase4` runs. CLI switch `-Phase2` executes Phase 2 RTI and Phase 3 HDS pipelines, exiting before downstream steps. CLI switch `-Phase5` executes Phase 6 CMS Quality. | Prevents alert configuration runs during imaging-only (`-Phase3`) or quality-only (`-Phase5`) runs. | agent |
| D5 | Teardown preserves Fabric capacities without pausing them. | Capacities are shared across workspaces; pausing capacity could disrupt external workloads. | agent |
| D6 | Non-hosted Rayfin imaging runs always download and convert slides on the fly (`HLS_HOSTED=0`). | Protects private internal cache locations while keeping public accelerator fully functional. | human |
| D7 | Databricks alert recipient dropped if not a workspace user, with alert left PAUSED and warning displayed. | Prevents Databricks Asset Bundle deployment failure on external email addresses. | agent |
| D8 | Process group cancellation on POSIX (`start_new_session=True` + `os.killpg`). | Ensures child PowerShell processes terminate completely when cancelled from web UI. | agent |
| D9 | Alert deduplication design: Stateful Reflex in `scripts/deploy_clinical_activator.py` (`fn_ClinicalAlerts(cooldown_minutes)` KQL source, `SplitEvent` event view, `Device` object view, `AttributeTrigger` on `alert_active` transition `BecomesGreaterThan 0`, `--cooldown-minutes` defaulting to 10, and `--min-tier` defaulting to `URGENT`), while `scripts/trigger_spo2_alert.py` slides the deduplication window and seeds baseline telemetry. | Prevents repeat alert floods on sustained low-SpO2 devices while ensuring alert episodes are reliably captured. | agent |
| D10 | `dim_patient` dimension table: Built in `phase-5/materialize_claims_quality.py` as distinct union of patient IDs across seven patient-level tables (`agg_quality_measures`, `care_gaps`, `agg_medication_adherence`, `agg_risk_scores`, `readmission_risk_scores`, `agg_high_cost_claimants`, and `fact_claim`). Only an absent optional source is skipped and listed in step output; a missing required source, schema drift, or any other read or count error fails the run before the write. The run also fails before the write when no source yields a patient ID, so the existing `dim_patient` stays unchanged. The summary step creates empty schemas only for genuinely absent optional tables, with non-overwriting writes, and halts on missing required tables. | Resolves patient fan-out by providing a unique one-side key for PHQ semantic model patient relationships. | agent |
| D11 | Stage-ETA pooling: Backend records duration of each succeeded phase and add-on in `stage_eta_samples.json` with bounded per-stage sample lists; hosted sandboxes pool peer files read-only from `HLS_SHARED_DATA_DIR` with file-size caps. `GET /api/stage-etas` returns `median_minutes` and `sample_count` for every canonical stage. The UI uses a learned median only when `sample_count >= 3`; otherwise it uses the built-in estimate. | Replaces hardcoded estimates with empirical stage durations without cross-sandbox writes. | agent |
| D12 | Recomputed Gold tables are written with `overwrite` + `overwriteSchema` (`overwrite_gold_table`); the declared placeholder schemas (`EXPECTED_TABLE_SCHEMAS`) are not aligned to the produced schemas. | 13 of 24 produced Gold schemas differ from the declared ones (extra columns, `int` vs `int64`, `date` vs `dateTime`) while every declared column exists in the output; every Gold table is a full recompute, so the produced schema is authoritative and no second schema list has to be kept in step. | agent |

---

## Open questions

### AlertEngine
Keep both platform-specific alert definitions: Fabric Activator for the core path, and the Databricks SQL alert inside the opt-in Databricks add-on, with its SQL schedule left paused until an operator activates it for a registered workspace user?
- *Status*: Open architectural question (see [Component 9](#component-9-real-time-alerts--data-activator-reflexes-scriptsdeploy_clinical_activatorpy-scriptstrigger_spo2_alertpy)).
- *Recommendation*: Yes. Keep the platform-specific definitions. The current bundle always leaves the SQL alert paused; setting `ALERT_EMAIL` alone does not activate it. Any activation must be deliberate and use a registered workspace recipient.

### DataShare
Accept the shared `/data-share` mount for the reference deployment (every sandbox can read the share; isolation is application code plus sealed credentials) while access stays limited to `microsoft.com` accounts?
- *Status*: Open architectural question (see [Component 10](#component-10-local-orchestrator-backend--process-engine-orchestratorlocal_serverpy-orchestratoractivities)).
- *Recommendation*: Yes, and revisit before admitting other tenants. It carries three owner-requested features; per-sandbox shares would drop ETA pooling and peer-history import.
- *Unimplemented alternative summary*: Read-only image layers or immutable blob snapshots. These are recorded options, not a reviewed replacement design. Any future cutover must preserve stage-ETA pooling, verified peer-history import and the hosted Rayfin seed cache.

### ESC-4
Keep teardown capacity-neutral (D5) and add no `-PauseCapacity` switch?
- *Status*: Open operational question (see [Component 14](#component-14-multi-tenant-teardown-engine-teardown-allps1-orchestratorsharedfull_teardownpy)).
- *Recommendation*: Yes. No requester; capacities can host other workspaces; pausing stays an operator step.

---

## Implementation plan

- `specs/README.md` (authoritative component spec): Comprehensive component architecture and operational contract documentation.
- `README.md`: Reference `specs/README.md` in Operations references and top-level navigation.
- `hosted/README.md`: Verify `/data-share` storage mount description, multi-tenant security boundaries, and allowlist configuration parameters.

---

## Verification

Execute the following offline commands from the repository root to verify syntax, contracts, and component integrity:

### 1. PowerShell Syntax, Parallel Execution & Retry Classification
```bash
pwsh -NoProfile -Command "
  \$scripts = @(
    'Deploy-All.ps1',
    'Preflight-Check.ps1',
    'setup-prereqs.ps1',
    'Teardown-All.ps1',
    'deploy-fabric-rti.ps1',
    'phase-1/deploy.ps1',
    'phase-1/deploy-fhir.ps1',
    'phase-2/deploy-data-agents.ps1',
    'phase-4/deploy-ontology.ps1',
    'phase-7/deploy-payer-rti.ps1',
    'hosted/Deploy-HostedOrchestrator.ps1'
  )
  foreach (\$s in \$scripts) {
    \$errors = \$null
    [void][System.Management.Automation.Language.Parser]::ParseFile(\$s, [ref]\$null, [ref]\$errors)
    if (\$errors) { throw \"Syntax error in \$(\$s): \$errors\" }
  }
  Write-Host 'All PowerShell scripts parsed cleanly.' -ForegroundColor Green
"
pwsh -NoProfile -File ./test_deploy_logic.ps1
pwsh -NoProfile -File ./test_parallel_hds_deployment.ps1
pwsh -NoProfile -File ./test_phase6_retry_logic.ps1
```

### 2. Infrastructure as Code (Bicep) Validation
```bash
az bicep build --file hosted/infra/main.bicep --outfile /tmp/hls-hosted-main.json
```

### 3. Hosted Gateway & Deployment Unit Tests
```bash
PYTHONPATH=. pytest hosted/gateway/tests
PYTHONPATH=. pytest hosted/tests
```

### 4. Orchestrator Backend, Add-on & Quality Model Tests
`python3` here is Python 3.10 or later with the orchestrator requirements installed. `phase-5/tests` also needs `pyspark` (verified with 4.0.1): five tests build Spark schemas and fail with `'NoneType' object is not callable` without it.
```bash
PYTHONPATH=orchestrator python3 -m unittest discover -s orchestrator/tests -p 'test_*.py'
python3 -m unittest discover -s phase-5/tests -p 'test_*.py'
python3 -m unittest phase-2/tests/test_seed_cma_sdoh.py
```

### 5. Multi-Ticket Roadmap Milestone Tests & Interop
```bash
pytest fhir-loader/tests
python3 -m unittest synthea/tests/test_seed_tcga_cohort.py
python3 -m unittest azure-databricks/implementation/tests/test_onelake_interop_proof.py
python3 -m unittest discover -s azure-databricks/implementation/tests -v
pwsh -NoProfile -NonInteractive -File phase-7/tests/test_data_agent_selection.ps1
```

### 6. Frontend Web UI & App Verifications
```bash
(cd orchestrator-ui && npm test && npm run build)
(cd rayfin-imaging && npm run lint)

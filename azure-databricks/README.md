# Azure Databricks destination blueprint

This folder defines how to keep the HLS Data Accelerator's Azure source estate while replacing the Microsoft Fabric destination with Azure Databricks.

> [!IMPORTANT]
> This is an implementation-ready architecture and deployment contract, not a second executable deployment path in the current orchestrator. `Deploy-All.ps1`, `Preflight-Check.ps1`, deployment activities, and the evaluation harness retain Fabric dependencies. Shared teardown is the exception: `orchestrator/shared/full_teardown.py`, also exposed through `Teardown-All.ps1`, already includes a Databricks Unity Catalog phase for objects bound to the deployment's Access Connector. That cleanup capability does not prove the broader destination adapter described here is implemented or tested.

Teardown pins tokens to an explicit deployment subscription and optionally checks an expected tenant. It discovers owned front ends (including Rayfin, cardiology, DICOM viewer and hosted orchestrator resources) and reports shared/unrelated groups as skipped. Preview from the repository root with `Teardown-All.ps1 -FabricWorkspaceName <workspace> -ResourceGroupName <rg> -SubscriptionId <subscription> -ExpectedTenantId <tenant> -Plan`. For a deployment without a Fabric workspace, use `python -m shared.full_teardown --subscription <subscription> --resource-group <rg> --expected-tenant <tenant> --delete-resource-group --plan` from `orchestrator/`. Neither preview deletes resources. See [root teardown guidance](../README.md#teardown).


## Decision

Use Azure Databricks as the governed data, analytics, AI, and operational destination. Keep the current Azure producer and landing components:

- Azure Health Data Services FHIR R4 service
- ADLS Gen2 containers for Synthea output, FHIR `$export`, and re-tagged DICOM
- Azure Event Hubs namespace with `telemetry-stream` and `claim-stream`
- Azure Container Registry and Azure Container Instances/jobs
- Azure Key Vault, managed identities, and RBAC
- Optional Durable Functions, Static Web App, Application Insights, and the Azure-hosted OHIF/DICOMweb surface

Add an Azure Databricks Premium workspace, an Access Connector for Azure Databricks, Unity Catalog storage objects, Lakeflow pipelines and jobs, Delta medallion tables, a Databricks SQL warehouse, AI/BI dashboards, Genie Agents, and Databricks SQL alerts.

## The non-portable boundary

Microsoft Healthcare Data Solutions and DTT v1.4.0 in `vendor/microsoft-hds/1.4.0` are deployed through Fabric-specific notebooks, environments, lakehouses, pipelines, semantic models, and reports. Do not upload that deployment package to Databricks and call it migrated.

The Databricks path must reimplement the observable contracts:

- FHIR and DICOM Bronze ingestion
- normalized clinical and imaging Silver tables
- reference-integrity, row-count, and dependency gates
- OMOP, quality, payer, risk, and reporting Gold products
- real-time telemetry and claim enrichment
- governed analytical, agent, imaging, and alerting surfaces

Pure Spark/Python transformations may be reused only after their Fabric dependencies, path assumptions, package metadata, and tests are separated.

## Platform map

| Current capability | Azure Databricks target |
|---|---|
| Fabric workspace + F capacity | Azure Databricks Premium workspace + compute policies |
| Fabric workspace identity | Access Connector managed identity |
| OneLake shortcuts | Unity Catalog storage credential, external locations, and external volumes |
| Fabric Eventstream | Lakeflow streaming table using the Event Hubs Kafka-compatible endpoint |
| Eventhouse + KQL | Delta streaming tables, materialized views, and Databricks SQL |
| HDS Bronze/Silver/Gold lakehouses | Unity Catalog catalog with `bronze`, `silver`, `gold`, and `ops` schemas |
| Fabric pipelines + notebooks | Lakeflow Declarative Pipelines + Lakeflow Jobs |
| Power BI / RTI dashboards | AI/BI dashboards by default; Power BI remains an optional client |
| Data Agents | Genie Agents grounded in Unity Catalog tables and metric views |
| Fabric IQ Ontology | No one-to-one object; use governed tables, relationships, metric views, metadata, and Genie instructions |
| Data Activator | Databricks SQL alerts v2, optionally chained into Lakeflow Jobs or an approved webhook target |
| OneLake-backed OHIF proxy | Keep OHIF in Azure; read DICOM from ADLS and study metadata from Databricks SQL |

The full replacement matrix is in [COMPONENT-MAP.md](COMPONENT-MAP.md).

## Deployment shape


The deployment has two control planes:

1. **Azure ARM/Bicep:** source services, Databricks workspace, Access Connector, storage RBAC, networking, Key Vault, Event Hubs authorization, and optional orchestrator hosting.
2. **Databricks Declarative Automation Bundles:** catalogs/schemas where supported, external locations, volumes, pipelines, jobs, SQL warehouse, dashboards, Genie Agents, alerts, permissions, and run-as identities.

Account-level Unity Catalog metastore creation/assignment and the initial managed-identity storage credential remain privileged bootstrap operations. They must be completed before the workspace bundle.

## Data path


- Auto Loader incrementally ingests FHIR NDJSON and a DICOM file inventory from Unity Catalog external locations.
- The Structured Streaming Kafka connector reads the existing Event Hubs through dedicated Databricks consumer groups.
- Bronze preserves source payloads, Event Hubs offsets, ingestion timestamps, paths, and provenance.
- Silver normalizes FHIR resources, indexes DICOM metadata, enforces references, and deduplicates streaming events.
- Gold materializes OMOP, quality, risk, utilization, cohort, clinical-alert, and payer-worklist products.
- Databricks SQL serves AI/BI dashboards, Genie Agents, alerts, optional Power BI, and the OHIF study index.

## Documents

- [Deployment guide](DEPLOYMENT-GUIDE.md) — prerequisites, resource model, phases, identities, data products, and teardown order
- [Execution runbook](implementation/README.md) — the runnable migration artifacts and the step-by-step commands, with teaching notes on each Fabric-to-Databricks decision
- [Component map](COMPONENT-MAP.md) — preserve/replace/rebuild decision for the current Azure and Fabric estate
- [Validation and operations](VALIDATION-AND-OPERATIONS.md) — fail-closed completion contract, recovery, monitoring, and cost controls

## Safety and scope

- Synthetic/demo data only. A production PHI deployment needs a separate privacy, compliance, network-isolation, retention, key-management, audit, and incident-response design.
- Keep source FHIR and DICOM locations read-only from Databricks. Derived Delta storage uses a separate managed path.
- Do not reuse the current namespace-level `emulator-access` Send+Listen secret for Databricks ingestion. Create a listen-only policy and store it through the existing Key Vault/Databricks secret boundary.
- SQL alerts are scheduled query evaluation, not a zero-latency per-event engine. The alert query must implement tiering and per-device cooldown; use a streaming/job action path when the latency target requires it.
- Completion means fresh data and working user surfaces, not merely created resources.

# Azure Databricks deployment guide

[Overview](README.md) · [Component map](COMPONENT-MAP.md) · [Validation and operations](VALIDATION-AND-OPERATIONS.md)

## Scope

This guide is the target deployment contract for an Azure Databricks destination. It preserves the HLS accelerator's current Azure source estate and replaces Fabric-owned ingestion, transformation, serving, AI, and action workloads.

The current repository does not yet expose a runnable `-Destination Databricks` switch. In particular:

- `Deploy-All.ps1` provisions and calls Fabric throughout the seven phases.
- `Preflight-Check.ps1` requires Fabric workspace/capacity checks.
- `orchestrator/shared/models.py` and the local/Durable orchestrators carry Fabric-specific configuration and resource IDs.
- `eval/deployment_eval_harness.py` proves Fabric items and Fabric runtime behavior.

A real implementation must introduce a destination adapter and migrate every caller. Do not hide Fabric calls behind runtime `try/except` branches or report this blueprint as deployed.

Teardown already uses one shared implementation, `orchestrator/shared/full_teardown.py`, from the local/Durable APIs and `Teardown-All.ps1`. It pins tokens to the supplied subscription, checks `--expected-tenant` when supplied, discovers deployment-owned front ends, and runs a **Databricks Unity Catalog** phase for catalogs, external locations and storage credentials tied to the deployment's Access Connector. This does not implement the remaining Databricks deployment adapter.

## Target invariants

1. The same Azure FHIR, ADLS, Event Hubs, ACR, ACI/job, Key Vault, managed-identity, and optional orchestrator components remain authoritative.
2. Source containers are read-only to Databricks. Managed Delta data uses a distinct catalog storage path.
3. Unity Catalog governs every table, volume, external location, model, dashboard dataset, and agent datasource.
4. Event Hubs ingestion uses the Kafka-compatible endpoint and a dedicated consumer group per stream.
5. Bronze is replayable; Silver is reference-valid and deduplicated; Gold is blocked until selected Silver gates pass.
6. HDS/DTT deployment artifacts are not treated as Databricks-compatible. The business contracts are reimplemented.
7. Bundles run as a service principal; production pipelines and jobs never depend on a developer identity.
8. Deployment completes only after fresh files/events, rows, SQL queries, dashboards, agents, alerts, and OHIF behavior are proven.

## Prerequisites

### Azure

- Owner, or Contributor plus User Access Administrator, on the target resource group/storage scopes.
- Azure CLI, Az PowerShell, PowerShell 7+, Bicep, Python, Node.js, and Git.
- Registered providers for `Microsoft.Databricks`, `Microsoft.Storage`, `Microsoft.EventHub`, `Microsoft.KeyVault`, `Microsoft.ContainerRegistry`, `Microsoft.ContainerInstance`, `Microsoft.HealthcareApis`, `Microsoft.ManagedIdentity`, `Microsoft.EventGrid`, and the optional web/monitoring providers.
- An existing Entra security group for deployment administrators.
- Azure CLI and Az PowerShell set to the same tenant and subscription.

### Azure Databricks

- Account administration access for Unity Catalog metastore assignment.
- A Premium workspace. This design uses Unity Catalog controls and may use Databricks Apps; Apps require Premium.
- A service principal for bundle deployment and workload `run_as` identity.
- A pinned, tested Databricks CLI release whose bundle schema recognizes every selected resource type. The documented resource set includes `catalog`, `schema`, `external_location`, `volume`, `pipeline`, `job`, `sql_warehouse`, `dashboard`, `genie_spaces`, and `alert`.
- Region alignment between the workspace, Access Connector, and ADLS storage.

### Preflight changes required in code

The Databricks implementation must add a platform-neutral preflight. It must not call current Fabric capacity or workspace APIs. Required checks:

- Azure identity/subscription alignment and resource-provider registration
- Databricks CLI authentication with OAuth, not a checked-in PAT
- account/workspace access and Unity Catalog metastore assignment
- destination catalog/schema name availability
- Access Connector and storage RBAC readiness
- ADLS source paths and FHIR `$export` presence
- Event Hubs namespace, both hubs, dedicated consumer groups, and listen-only policy
- bundle validation against the pinned CLI schema
- selected features, alert recipients, network mode, and cost-bearing compute

## Resource model

### Existing Azure source plane

Reuse the behavior implemented by:

- `bicep/infra.bicep`
- `bicep/fhir-infra.bicep`
- `bicep/emulator.bicep`
- `bicep/claim-emulator.bicep`
- `bicep/synthea-job.bicep`
- `bicep/fhir-loader-job.bicep`
- `bicep/dicom-loader-job.bicep`
- `phase-1/deploy.ps1`
- `phase-1/deploy-fhir.ps1`
- the `synthea/`, `fhir-loader/`, `dicom-loader/`, and emulator sources

`phase-1/deploy.ps1` can deploy the base Azure resources independently, and `phase-1/deploy-fhir.ps1` already supports full and selective FHIR/DICOM modes. The Databricks path should extract these behind a platform-neutral source-estate activity rather than retain the misleading `FabricWorkspaceName` naming input.

Add to the existing Event Hubs namespace:

- consumer group `hls-dbx-telemetry` on `telemetry-stream`
- consumer group `hls-dbx-claims` on `claim-stream`
- a namespace or entity authorization rule with **Listen only** for the Databricks reader

Store the listen-only key through the existing Key Vault boundary. Do not reuse the current Send+Listen emulator rule.

### Databricks Azure plane

Provision with Bicep/ARM:

| Resource | Contract |
|---|---|
| `Microsoft.Databricks/workspaces@2026-01-01` | Premium SKU; explicit managed resource group; selected public/private network mode; tags; same region as ADLS |
| `Microsoft.Databricks/accessConnectors` | Managed identity used by Unity Catalog storage credentials |
| Existing ADLS account | Add a `databricks-managed` container/path for managed catalog data; retain `fhir-export` and `dicom-output` as sources |
| Azure RBAC | Source containers: read; managed container: Storage Blob Data Contributor; file-events roles only when Auto Loader file events are enabled |
| Existing Key Vault | Event Hubs listen key and other unavoidable external secrets; no secrets in notebooks or bundle YAML |
| Optional networking | VNet injection/private endpoints/serverless network connectivity are a production profile, not silently added to the demo profile |

The Access Connector identity needs:

- `Storage Blob Data Reader` on `fhir-export` and `dicom-output`
- `Storage Blob Data Contributor` on the `databricks-managed` container
- for automatically managed Auto Loader file events: `Storage Queue Data Contributor`, `Storage Account Contributor`, and `EventGrid EventSubscription Contributor` at the documented scopes

Scope roles to containers/resource groups where Azure permits it. Do not grant subscription-wide data access.

### Unity Catalog layout

Use one catalog per environment:

```text
hls_dev
hls_test
hls_prod
```

Each catalog contains:

```text
bronze   raw and replayable Delta tables
silver   normalized clinical, imaging, telemetry, and payer products
gold     OMOP, quality, risk, utilization, cohort, and reporting products
ops      alert candidates, worklists, deployment evidence, and operational state
meta     source manifests, run lineage, schemas, and validation outcomes
```

Use these storage boundaries:

| Boundary | Storage behavior |
|---|---|
| FHIR `$export` external location | Read-only source path |
| DICOM external location/volume | Read-only source bytes; metadata extracted to Delta |
| Catalog managed location | Read/write path under `databricks-managed/<environment>/` |
| Checkpoints/schema state | Managed under the catalog or a dedicated governed volume; never under a developer home path |

A storage credential wraps the Access Connector managed identity. External locations then bind that credential to exact `abfss://` paths. The supported external-location SQL shape is:

```sql
CREATE EXTERNAL LOCATION IF NOT EXISTS `<location-name>`
URL 'abfss://<container>@<storage-account>.dfs.core.windows.net/<path>'
WITH (STORAGE CREDENTIAL `<credential-name>`)
COMMENT '<purpose>';
```

Create/bind the metastore and storage credential in a privileged bootstrap step before the workspace bundle. Bind credentials and external locations to the intended workspace.

## Deployment phases

### Phase 0 — Plan and preflight

Inputs:

- tenant, subscription, resource group, region
- Databricks account/workspace name and environment target
- Entra admin group and bundle service principal
- patient count/data strategy
- selected FHIR, DICOM, telemetry, payer, AI/BI, Genie, app, Power BI, and alert features
- explicit clinical and payer recipients
- public or private network profile

Exit contract:

- identities and scopes are resolved
- the exact mutation plan is rendered
- cost-bearing compute and alert recipients are explicit
- no cloud mutation has occurred

### Phase 1 — Deploy or reuse the Azure source estate

1. Deploy Event Hubs, ACR, Key Vault, and producer containers from the current Bicep/scripts.
2. Deploy Azure Health Data Services FHIR plus the ADLS account/containers.
3. Generate or reuse the canonical synthetic fixture.
4. Load FHIR resources and device associations.
5. Re-tag/upload DICOM and create matching `ImagingStudy` resources.
6. Run FHIR `$export` into `fhir-export`.
7. Create Databricks-specific Event Hubs consumer groups and the listen-only policy.

Exit contract:

- FHIR resources are queryable
- a complete `$export` exists
- DICOM files and matching `ImagingStudy` resources exist when selected
- both Event Hubs accept controlled producer events

### Phase 2 — Provision Azure Databricks and Unity Catalog

1. Deploy the Premium workspace and Access Connector.
2. Assign the workspace to the regional Unity Catalog metastore.
3. Grant source-read, managed-write, and optional file-event RBAC.
4. Create the storage credential and workspace binding.
5. Create read-only FHIR/DICOM external locations and the environment catalog managed location.
6. Create the `bronze`, `silver`, `gold`, `ops`, and `meta` schemas.
7. Create the SQL warehouse and compute policies selected by the deployment profile.

Exit contract:

- a service-principal query can list both source locations
- source locations reject writes
- a managed test table can be created and deleted under the target catalog
- no user-home storage or personal token is required

### Phase 3 — Deploy Databricks workspace resources

Use Declarative Automation Bundles as the workspace deployment unit. Pin bundle configuration, Python dependencies, permissions, and `run_as` identity in source control.

The bundle resource contract is:

| Bundle resource | Purpose |
|---|---|
| catalogs/schemas/external locations/volumes | governed namespace and storage bindings where supported |
| pipelines | file ingestion, streaming ingestion, clinical/imaging normalization, and Gold products |
| jobs | ordered barriers, materialization, validation, repair, dashboard refresh, and alert branches |
| SQL warehouse | dashboard, Genie, alert, validation, and optional Power BI compute |
| dashboards | clinical telemetry, imaging, population health/quality, and payer operations |
| Genie Agents | Patient 360, Clinical Triage, Imaging Cohort, and Payer Operations domains |
| SQL alerts v2 | clinical and payer threshold evaluation with reviewed notification destinations |
| Databricks App, when selected | custom operational UI; OHIF may remain on its existing Azure host |

Bundle lifecycle:

```bash
databricks bundle validate -t <environment>
databricks bundle deploy -t <environment>
databricks bundle run -t <environment> <bootstrap-job>
databricks bundle run -t <environment> <validation-job>
```

The implementation must define stable job keys for bootstrap and validation; the placeholder names above are not current repository commands.

### Phase 4 — Ingest and transform

#### FHIR and DICOM files

- Use Auto Loader against Unity Catalog external locations.
- FHIR Bronze stores source path, resource type, raw JSON, export/run identity, ingestion timestamp, and schema-rescue data.
- DICOM Bronze stores file path, size, hash where practical, study/series/SOP UIDs, synthetic patient link, modality, and extraction status. Keep pixel bytes in ADLS.
- Use file events when the additional Azure roles/network path are approved; otherwise use bounded directory listing for the demo profile.

#### Telemetry and claims

- Use Lakeflow streaming tables with the built-in Structured Streaming Kafka connector.
- Connect to `<namespace>.servicebus.windows.net:9093` with SASL/SSL.
- Retrieve the listen-only key from the approved secret scope; never embed the connection string.
- Set a unique consumer group for each hub/environment.
- Preserve topic, partition, offset, enqueue timestamp, raw payload, and processing timestamp in Bronze.
- Use deterministic business keys, event-time watermarks, and idempotent merges downstream.

#### Silver

Required clinical/imaging tables mirror the current observable contract, including:

- Patient, Encounter, Condition, Observation, MedicationRequest, Procedure, Immunization, Coverage, Claim/ExplanationOfBenefit
- Device, DeviceAssociation, Location, ImagingStudy, ImagingSeries, ImagingInstance/metadata inventory
- typed telemetry and claim events joined to validated patient/device/payer context

Required gates:

- parse/error quarantine is bounded and visible
- FHIR references resolve for selected resource types
- canonical patient/device associations remain one-to-one
- selected imaging studies join to a known synthetic patient
- stream duplicates do not create duplicate business events

#### Gold and operations

Produce the same business outcomes, not Fabric object identities:

- OMOP CDM/research tables
- population health and quality facts
- Star Ratings, HCC/RAF, readmission, utilization, care-gap, and payer facts
- clinical alert candidates and alert history
- fraud/high-cost/care-gap scoring and payer worklists
- reporting facts and DICOM viewer links

Gold jobs start only after selected Silver row, reference, and freshness gates pass. Optional sidecars cannot turn a failed required gate into success.

### Phase 5 — Experiences and action

- **AI/BI dashboards:** default native report surface over Databricks SQL and metric views.
- **Genie Agents:** separate trusted domains for Patient 360, Clinical Triage, imaging cohorts, and payer operations. Bind only reviewed tables/metric views and include verified questions.
- **Ontology replacement:** encode business semantics in table/column comments, constraints, metric views, curated relationships, Genie instructions, and verified answers. Document that this is not a Fabric IQ graph.
- **SQL alerts v2:** own their query, threshold, schedule, `run_as`, destination, and retrigger interval. Queries implement tiering and cooldown state.
- **Lakeflow Jobs:** branch from an alert task when downstream workflow is required.
- **OHIF:** retain the Azure-hosted viewer/proxy; read DICOM from ADLS with managed identity and study indexes/links from Databricks SQL.
- **Power BI:** optional external BI client through the Azure Databricks connector/SQL warehouse. It is not required for the Databricks-native deployment.

### Phase 6 — Validate, release, and record evidence

Run the fail-closed checks in [VALIDATION-AND-OPERATIONS.md](VALIDATION-AND-OPERATIONS.md). A successful bundle deployment is not completion.

## Orchestrator implementation contract

The existing UI and FastAPI/Durable layers can remain the control plane only after platform-specific code is separated.

Required clean cutover:

- add destination type `fabric | databricks` to the deployment model
- replace Fabric-named generic fields with destination-neutral identifiers
- keep common Azure/FHIR/DICOM activities shared
- implement Databricks workspace, Unity Catalog, bundle, pipeline, SQL, dashboard, agent, alert, validation, and teardown activities
- route every current callsite through the selected adapter
- give Databricks phases their own progress labels and resource state
- remove assumptions that F capacity, Fabric workspace identity, OneLake, or Fabric item IDs always exist
- persist bundle target, catalog, workspace host/ID, pipeline/job IDs, SQL warehouse ID, and deployment evidence
- add a Databricks-specific continuation/repair path; do not overload historical Fabric phase switches

## Databricks-native teardown target

1. Pause/disable SQL alert schedules and producer jobs.
2. Stop Lakeflow continuous pipelines and wait for terminal state.
3. Export final run/validation evidence.
4. Destroy bundle-managed resources for the selected target.
5. Remove workspace bindings, external locations, volumes, schemas/catalog, and storage credential only when not shared.
6. Delete the Databricks workspace and Access Connector if the deployment owns them.
7. Delete Azure source/viewer/orchestrator resource groups only when explicitly selected.
8. Retain or delete source ADLS/FHIR data according to the synthetic-data and evidence policy.

The sequence above remains the target lifecycle for bundle-managed workloads, not a claim that shared teardown already stops alerts/pipelines or destroys bundles. Do not supply a fake Fabric workspace. For an Azure/Databricks deployment without Fabric, preview the existing shared cleanup from `orchestrator/`:

```bash
python -m shared.full_teardown --subscription <deployment-subscription-id> \
  --resource-group <deployment-rg> --expected-tenant <tenant-id> \
  --delete-resource-group --plan
```

`--plan` performs discovery only. The existing cleanup removes deployment-bound Unity Catalog objects before deleting Azure resource groups, discovers owned front ends, and skips shared/unrelated groups with reasons. Use repeatable `--front-end-resource-group <rg>` for explicit groups, still subject to ownership checks, or `--no-front-end-discovery` to disable automatic discovery. A subscription is mandatory; the Azure CLI default is never a teardown target. For Fabric deployments, `Teardown-All.ps1` wraps this same module with `-SubscriptionId`, `-ExpectedTenantId`, `-FrontEndResourceGroup`, `-NoFrontEndDiscovery` and read-only `-Plan`; see [root teardown guidance](../README.md#teardown).

## Official references

- [Azure Databricks workspace Bicep/ARM resource](https://learn.microsoft.com/en-us/azure/templates/microsoft.databricks/workspaces)
- [Use Azure managed identities in Unity Catalog](https://learn.microsoft.com/en-us/azure/databricks/connect/unity-catalog/cloud-storage/azure-managed-identities)
- [Connect Unity Catalog to ADLS Gen2 external locations](https://learn.microsoft.com/en-us/azure/databricks/connect/unity-catalog/cloud-storage/external-locations-adls)
- [Load data in Lakeflow pipelines](https://learn.microsoft.com/en-us/azure/databricks/ldp/load)
- [Use Azure Event Hubs as a pipeline source](https://learn.microsoft.com/en-us/azure/databricks/ldp/event-hubs)
- [Declarative Automation Bundles](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/)
- [Bundle-supported resources](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/resources)
- [AI/BI dashboards](https://learn.microsoft.com/en-us/azure/databricks/dashboards/)
- [Genie](https://learn.microsoft.com/en-us/azure/databricks/genie/)
- [Databricks SQL alerts](https://learn.microsoft.com/en-us/azure/databricks/sql/user/alerts/)
- [Databricks Apps](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/)
- [Power BI with Azure Databricks](https://learn.microsoft.com/en-us/azure/databricks/partners/bi/power-bi/)

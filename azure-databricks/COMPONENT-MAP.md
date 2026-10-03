# Fabric-to-Azure Databricks component map

[Overview](README.md) · [Deployment guide](DEPLOYMENT-GUIDE.md) · [Validation and operations](VALIDATION-AND-OPERATIONS.md)

Legend:

- **Preserve:** same Azure service and behavior
- **Replace:** supported Databricks capability covers the contract directly
- **Rebuild:** business behavior must be reimplemented; there is no safe artifact lift
- **Optional:** retain only when the deployment selects it

## Azure source and control components

| Current asset | Decision | Databricks-destination treatment | Proof required |
|---|---|---|---|
| Azure Health Data Services workspace + FHIR R4 service | Preserve | Remains the clinical system of record | FHIR metadata, patient/resource counts, and a completed `$export` |
| ADLS Gen2 `synthea-output` | Preserve | Producer staging only | Canonical fixture manifest/counts match |
| ADLS Gen2 `fhir-export` | Preserve | Read-only Unity Catalog external location/volume | Service-principal file listing and Auto Loader ingestion |
| ADLS Gen2 `dicom-output` | Preserve | Read-only external location; image bytes stay in ADLS | DICOM inventory, UID uniqueness, and patient linkage |
| Azure Event Hubs namespace | Preserve | Same namespace and Kafka-compatible endpoint | namespace/hub health plus incoming/outgoing metrics |
| `telemetry-stream` | Preserve | Dedicated Databricks consumer group | fresh offsets and Bronze events |
| `claim-stream` | Preserve | Separate Databricks consumer group | fresh offsets and Bronze claim events |
| Namespace `emulator-access` Send+Listen policy | Rebuild security boundary | Producers keep managed identity; Databricks gets a distinct Listen-only policy | rights are Listen only and secret is not in source/bundle |
| ACR | Preserve | Same images for Synthea, loaders, telemetry, and claim producers | image digests and successful pulls |
| ACI/jobs and managed identities | Preserve | Same producer workloads and RBAC | terminal job state and output artifacts/events |
| Key Vault | Preserve | Holds unavoidable Event Hubs listener secret and other external secrets | secret references resolve without exposing values |
| Durable Functions + Static Web App orchestrator | Optional | Keep after adding destination adapter | Databricks plan, run, repair, validation, and teardown paths |
| Application Insights + Log Analytics | Preserve/extend | Keep orchestrator telemetry; add Databricks system-table/job evidence | trace/run correlation without PHI payload logging |

## Fabric platform replacements

| Fabric asset/capability | Decision | Azure Databricks target | Important difference |
|---|---|---|---|
| Fabric workspace | Replace | Azure Databricks Premium workspace | Azure workspace resource plus Databricks account/workspace control planes |
| F-SKU capacity | Replace | jobs/pipeline compute and SQL warehouse/serverless billing | no pause/resume equivalence; control schedules and serverless spend instead |
| Fabric workspace identity | Replace | Access Connector managed identity | Unity Catalog storage credentials reference the connector |
| Fabric REST item deployment | Replace | Declarative Automation Bundles + Databricks REST/CLI | account-level metastore bootstrap remains separate |
| OneLake shortcuts | Replace | Unity Catalog external locations and external volumes | source paths stay in ADLS; grants and workspace bindings govern access |
| Bronze/Silver/Gold lakehouses | Replace | Delta tables in `bronze`, `silver`, `gold`, `ops`, and `meta` schemas | use catalog managed storage for derived tables |
| Fabric Environment | Replace | pinned pipeline/job Python dependencies and compute policies | validate every native/JVM dependency against the selected runtime |
| Fabric notebooks | Replace/reuse code | bundle-managed Python/SQL source, notebooks only where they add value | remove `notebookutils`, Fabric item IDs, and OneLake paths |
| Fabric Data Pipelines | Replace | Lakeflow Jobs and Lakeflow Declarative Pipelines | define dependency barriers and repair jobs explicitly |
| HDS/DTT source deployment | Rebuild | Databricks-native FHIR/DICOM pipelines and libraries | the vendored deployment package is Fabric-specific |
| HDS Clinical/POA/Imaging/OMOP pipelines | Rebuild | separate Lakeflow pipelines/jobs with the same observable gates | preserve ordering: clinical/selected dependencies before imaging/OMOP |
| HDS semantic models/reports | Rebuild | Databricks SQL views/metric views and AI/BI dashboards | no Direct Lake or TMDL object identity |

## Real-time intelligence

| Fabric asset/capability | Decision | Azure Databricks target | Proof required |
|---|---|---|---|
| `MasimoTelemetryStream` Eventstream | Replace | continuous Lakeflow streaming table from Event Hubs Kafka endpoint | current offsets, bounded lag, fresh Bronze rows |
| `ClaimsRTIStream` Eventstream | Replace | independent Lakeflow stream/consumer group | no shared checkpoints or schema collision |
| Eventhouse/KQL database | Replace | Delta streaming tables and Databricks SQL | typed current state and query latency meet demo target |
| `TelemetryRaw` | Replace | `bronze.telemetry_raw` then `silver.telemetry` | source metadata and deterministic event key retained |
| `claims_events` | Replace | `bronze.claim_events` then `silver.claim_events` | claim schema, payer identity, and deduplication proven |
| KQL enrichment functions | Rebuild | SQL views/materialized views or pipeline transformations | patient/device/payer joins use validated Silver keys |
| KQL snapshots/worklists | Rebuild | `ops`/`gold` Delta tables or materialized views | fraud, high-cost, care-gap, and unified worklists return rows |
| RTI dashboards | Replace | AI/BI dashboards over Databricks SQL | rendered current data, not stale cached rows |

## Semantic, AI, BI, and application surfaces

| Fabric surface | Decision | Azure Databricks target | Important difference |
|---|---|---|---|
| Power BI Direct Lake reports | Replace by default | AI/BI dashboards | Power BI remains optional through Databricks SQL, not Direct Lake |
| Population Health & Quality semantic model | Rebuild | Gold Delta star schema plus metric views | Power BI metric-view connector behavior must be tested if Power BI is retained |
| Fabric Data Agents | Replace | Genie Agents | configure trusted tables, metrics, instructions, sample queries, and verified answers |
| Clinical/Payer Operations Agents | Rebuild | Genie Agent plus Lakeflow Jobs/Databricks App for controlled workflows | an agent response does not authorize a side effect |
| Fabric IQ Ontology/GraphModel | Rebuild semantics | Unity Catalog metadata, constraints, relationships, metric views, and Genie rules | no first-class one-to-one ontology/graph replacement is claimed |
| Data Activator/Reflex | Replace behavior | Databricks SQL alerts v2, optionally as Lakeflow Job tasks | scheduled query evaluation; query owns threshold/cooldown semantics |
| Email actions | Replace | alert subscription or approved notification destination | explicit reviewed recipient; no default address |
| OHIF viewer | Preserve | existing Azure-hosted frontend | remains outside Databricks |
| DICOMweb proxy | Rebuild storage adapter | read ADLS with managed identity; query study index through Databricks SQL | remove OneLake/Fabric workspace-role dependency |
| Fabric DICOM Cohorting Agent | Rebuild | curated Gold cohort views + Genie Agent | preserve cohort question/answer contracts, not item identity |
| Optional Power BI | Optional | Azure Databricks connector to SQL warehouse | use OAuth/service principal and validate DirectQuery/import behavior |
| Custom operational UI | Optional | Databricks App or existing Azure web app | Apps require Premium and are billed while running |

## Orchestration and lifecycle

| Current code path | Decision | Required Databricks adaptation |
|---|---|---|
| `Deploy-All.ps1` | Rebuild platform boundary | shared Azure-source phase plus Fabric and Databricks destination adapters |
| `Preflight-Check.ps1` | Rebuild destination checks | Databricks CLI/account/workspace/UC/bundle readiness instead of Fabric capacity |
| `orchestrator/shared/models.py` | Clean migration | destination-neutral config plus platform-specific resource state; migrate every caller |
| local FastAPI orchestrator | Extend | plan/start/status/continue/validate/teardown for Databricks runs |
| Durable Functions activities | Extend | Databricks workspace, bundle, pipeline/job, SQL, agent, alert, and teardown activities |
| deployment state JSON/SQLite | Extend | workspace host/ID, catalog, bundle target, job/pipeline/warehouse IDs, evidence |
| resume/repair switches | Rebuild | named Databricks recovery boundaries; do not overload historical Fabric phase numbers |
| `eval/deployment_eval_harness.py` | Rebuild destination probes | Azure metrics + Databricks REST/SQL + real rendered surfaces |
| `Teardown-All.ps1` / `orchestrator/shared/full_teardown.py` | Shared implementation | subscription-pinned cleanup already discovers owned front ends and removes deployment-bound Unity Catalog objects; stopping streams/alerts and destroying bundle-managed resources remain Databricks-native lifecycle work |

Preview with `Teardown-All.ps1 -SubscriptionId <subscription> -ExpectedTenantId <tenant> -FabricWorkspaceName <workspace> -ResourceGroupName <rg> -Plan`. For Azure/Databricks without Fabric, run `python -m shared.full_teardown --subscription <subscription> --expected-tenant <tenant> --resource-group <rg> --delete-resource-group --plan` from `orchestrator/`. Plans delete nothing; automatic front-end discovery reports shared/unrelated groups as skipped. See [teardown parameters](../README.md#teardown).

## Data product mapping

| Current outcome | Databricks table/view contract |
|---|---|
| HDS clinical Silver | normalized FHIR entity tables with source/resource IDs and reference gates |
| HDS imaging Silver | study/series/instance metadata joined to synthetic patient/ImagingStudy |
| OMOP Gold | OMOP CDM tables produced only after selected clinical/imaging readiness |
| reporting Gold | study, patient, viewer-link, quality, payer, risk, and utilization facts |
| `AlertHistory` / `fn_ClinicalAlerts` | `ops.clinical_alert_candidates` and `ops.clinical_alert_history` |
| payer worklists | `ops.payer_worklist` plus auditable scoring snapshots |
| deployment admin tables | `meta.deployment_runs`, `meta.pipeline_runs`, `meta.validation_results`, and source manifests |

## Clean-cutover rule

Do not create compatibility shims that pretend a Fabric item is a Databricks resource. The destination adapter must replace every platform call, state field, validation probe, teardown operation, help string, and UI label on the selected path. Shared code is limited to genuinely shared Azure source behavior and platform-neutral contracts.

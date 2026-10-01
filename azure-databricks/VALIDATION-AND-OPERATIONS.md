# Azure Databricks validation and operations

[Overview](README.md) · [Deployment guide](DEPLOYMENT-GUIDE.md) · [Component map](COMPONENT-MAP.md)

## Completion contract

A deployment is complete only when every required check for the selected feature set passes. Created Azure resources, a successful Bicep deployment, a successful bundle deployment, or a green pipeline definition alone is insufficient.

Evidence must bind to:

- tenant, subscription, resource group, and region
- Databricks account/workspace ID and host
- Unity Catalog metastore/catalog/schema names
- bundle target and deployed revision/digest
- Azure producer run IDs
- Lakeflow pipeline/job update IDs
- SQL warehouse ID
- validation timestamp and source freshness watermark

## Gate matrix

### 1. Identity and governance

Require:

- Azure CLI, Az PowerShell, Databricks CLI, and bundle service principal resolve to the intended tenant/account.
- The workspace is attached to the expected Unity Catalog metastore.
- Bundle resources run as the deployment/workload service principal, not an individual user.
- FHIR/DICOM external locations are workspace-bound and read-only.
- Managed catalog storage accepts governed table writes.
- Required Entra groups have only the intended catalog/schema/table privileges.
- No PAT, Event Hubs key, storage key, or client secret exists in tracked source, bundle YAML, notebook output, or logs.

Fail on identity drift, writable source paths, missing workspace binding, or personal run ownership.

### 2. Azure source readiness

FHIR:

- FHIR endpoint responds under the expected audience/tenant.
- canonical patient/resource counts match the selected data strategy.
- Device and `device-assoc` records link the demo cohort.
- `$export` reaches terminal success and produces non-empty NDJSON files.

DICOM:

- selected `.dcm` files exist under `dicom-output`.
- UIDs and re-tagged synthetic patient identifiers pass the current loader checks.
- matching FHIR `ImagingStudy` resources exist.

Event Hubs:

- `telemetry-stream` and `claim-stream` exist when selected.
- producers can send through managed identity.
- Databricks uses distinct consumer groups.
- the Databricks authorization rule has Listen only.
- Event Hubs incoming and outgoing message metrics advance after a controlled event.

### 3. Storage and Auto Loader

Require:

- service-principal listing succeeds for both source locations.
- write/delete attempts against source locations are denied.
- Auto Loader discovers a newly staged controlled file.
- schema/checkpoint state uses a governed managed path.
- reprocessing the same source file does not duplicate the business record.
- malformed/quarantined files are visible with bounded counts and source paths.

If file events are enabled, independently verify the Access Connector's queue/storage/Event Grid roles and the event subscription. A configured external location alone does not prove file notification flow.

### 4. Streaming ingestion

For both telemetry and claims:

1. Record Event Hubs incoming/outgoing metrics before the canary.
2. Submit one controlled event with a unique correlation/business key.
3. Observe the expected topic/partition/offset in Bronze.
4. Observe the typed, deduplicated row in Silver.
5. Require `maxOffsetsBehindLatest` or the selected backlog metric to remain within the declared bound.
6. Re-submit the same business event and prove that downstream business state is not duplicated.
7. Stop/restart the pipeline from its checkpoint and prove no gap or uncontrolled replay.

A running pipeline with no fresh row fails. A fresh row without a source offset/correlation trail fails.

### 5. Bronze, Silver, and Gold data

Bronze gates:

- raw payload, source path/topic, partition/offset where applicable, ingestion time, and provenance are populated.
- required FHIR/DICOM/telemetry/claim sources contain rows.
- parse failures remain below the selected demo threshold and are queryable.

Silver gates:

- required FHIR entity tables exist and contain the selected cohort.
- tested references resolve: patient, encounter, device, coverage/claim, and imaging relationships.
- each featured device maps to the intended canonical patient/condition.
- imaging metadata joins to `ImagingStudy` and source DICOM paths.
- stream event keys are unique after deduplication.
- timestamps use one documented storage convention; presentation converts explicitly.

Gold gates:

- OMOP starts only after required clinical and selected imaging gates.
- quality/payer/risk/utilization facts contain required rows for the selected synthetic fixture.
- sparse-cohort behavior is explicit and does not turn a wholly blank model into success.
- clinical alerts and payer worklists include current clinical/payer context.
- optional sidecars never mask a failed required product.

### 6. SQL and experience surfaces

Databricks SQL:

- warehouse reaches a runnable state.
- required views/metric views compile and return rows.
- row filters/masks behave as designed for test principals.
- representative queries have bounded latency for the demo profile.

AI/BI dashboards:

- each selected dashboard is published.
- datasets point at the target catalog and SQL warehouse.
- required pages/visuals render non-error values.
- telemetry/payer pages display the controlled fresh event, not a stale cache.

Genie Agents:

- each Agent is published with only reviewed tables/metric views.
- verified questions cover Patient 360, clinical triage, imaging cohort, and payer operations where selected.
- answers cite/query the intended current data and do not invent clinical advice.
- agent permissions match Unity Catalog permissions.

OHIF/DICOMweb:

- frontend and proxy are reachable.
- proxy identity can read selected ADLS DICOM paths.
- at least one indexed study/series resolves and renders.
- Databricks study metadata and ADLS object paths agree.

Optional Power BI:

- OAuth/service-principal connection resolves to the intended SQL warehouse.
- DirectQuery/import mode is explicit.
- required semantic-model/report visuals render.
- metric views are queried using a currently supported connector pattern; do not assume removed compatibility options.

### 7. Alerts and controlled action

Clinical and payer alerts require:

- explicit reviewed recipients/destinations
- query text bound to the target catalog
- threshold/tier logic
- schedule and `run_as` identity
- per-device or per-business-key cooldown/deduplication logic
- controlled qualifying event
- alert history showing `TRIGGERED`, followed by the expected notification/task evidence
- non-qualifying control event that remains `OK`

SQL alerts evaluate scheduled queries. If the required latency is lower than the schedule can support, use a streaming/job action design and validate that path separately.

Agent output must never directly authorize a clinical or payer side effect. Any action uses an explicit allowlist, reviewed destination, least-privilege identity, and auditable job/webhook boundary.

## Deployment health summary

Persist one bounded summary per run:

```json
{
  "workspace_id": "<id>",
  "catalog": "hls_<environment>",
  "bundle_target": "<environment>",
  "revision": "<source revision>",
  "azure_sources": "passed",
  "unity_catalog": "passed",
  "files": "passed",
  "telemetry_stream": "passed",
  "claims_stream": "passed",
  "bronze": "passed",
  "silver": "passed",
  "gold": "passed",
  "sql": "passed",
  "dashboards": "passed",
  "agents": "passed",
  "alerts": "passed",
  "ohif": "passed",
  "checked_at": "<UTC timestamp>"
}
```

Omitted optional features are `skipped` with a reason, never `passed`.

## Recovery model

### Files

- retain source files and Bronze provenance
- fix schema/code/config at the failed boundary
- replay only the affected files or pipeline update
- prove idempotency before downstream continuation

### Streams

- retain checkpoint and offset evidence
- restart from the existing checkpoint by default
- reset/replay only with an explicit bounded offset/time plan
- compare source offsets, Bronze rows, Silver keys, and downstream action count

### Transformations

- repair the smallest failed pipeline/job
- preserve successful upstream tables
- rebuild downstream products only after the repaired gate passes
- never mark a failed run complete because a later query happens to return old rows

### Experiences

- redeploy only the changed dashboard/Agent/alert/app bundle resource
- republish and query the actual target
- retain previous evidence but mark it superseded

## Monitoring

### Azure

- Event Hubs incoming/outgoing messages, throttles, server errors, and consumer lag indicators
- ACI/job terminal state and restarts
- FHIR request/export failures
- ADLS availability, authorization failures, file-event queues/subscriptions
- Key Vault access failures
- Application Insights/Log Analytics for the orchestrator and Azure-hosted apps

### Databricks

- pipeline update state, event log, data-quality expectations, backlog, and restart count
- job/task failures and duration
- SQL warehouse events, query history, queue time, and cost
- system tables for billing, audit, lineage, and access
- Genie/agent audit and quality metrics
- alert evaluation history
- app logs/telemetry when Databricks Apps are selected

Do not log raw FHIR/DICOM/claim payloads into general operational telemetry.

## Cost controls

- Tag Azure and Databricks resources with environment, owner, workload, and expiration.
- Use triggered pipelines for batch FHIR/DICOM work; continuous compute only for selected real-time streams.
- Bound Event Hubs retention and partitions to the workload profile.
- Apply SQL warehouse auto-stop and maximum-size policies.
- Apply job/pipeline compute policies and serverless budget monitoring.
- Disable alert schedules and stop producers/continuous pipelines when the demo is idle.
- Treat Databricks Apps as hourly-billed compute while running.
- Alert on billing/system tables before the demo budget is exceeded.

## Teardown verification

Before deletion:

- capture ownership and resource inventory
- stop producers, streams, jobs, and alerts
- export final validation/evidence
- show the exact bundle target, catalog, workspace, and Azure resource groups to be removed

After deletion:

- bundle-managed resources are absent
- selected catalog/external-location/workspace bindings are absent
- Databricks workspace and Access Connector are absent when owned by the run
- selected Azure resource groups reach deleted state
- shared metastore, shared storage, and unselected source data remain
- no scheduled job, alert, producer, or orphaned SQL warehouse remains active

Fail closed on ambiguous ownership. Never delete a shared metastore, credential, external location, storage account, or Key Vault based only on a name prefix.

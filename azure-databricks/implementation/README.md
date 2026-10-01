# Azure Databricks migration: execution runbook and teaching notes

[Blueprint overview](../README.md) · [Component map](../COMPONENT-MAP.md) · [Deployment contract](../DEPLOYMENT-GUIDE.md)

This folder is the executable half of the blueprint. Each step below is a real command,
paired with the reasoning for why the Fabric approach does not port directly.

> [!IMPORTANT]
> This deploys a governed Databricks destination over your **existing** Azure source estate.
> It never recreates FHIR, ADLS source containers, Event Hubs entities, ACR, ACI, or Key Vault.
> The HDS/DTT deployment package is Fabric-specific; its business contracts are reimplemented
> here as Lakeflow pipelines, not lifted.

## The one idea that drives every artifact

Fabric gives you a workspace that is simultaneously the compute boundary, the storage
boundary, the governance boundary, and the item catalog. Databricks splits that into four
things you must wire yourself:

| Concern | Fabric | Databricks | Artifact here |
|---|---|---|---|
| Compute | F-SKU capacity | serverless jobs/pipelines + SQL warehouse | `scripts/04-unity-catalog-bootstrap.sh`, pipeline `serverless: true` |
| Storage identity | workspace identity | Access Connector managed identity | `bicep/databricks-foundation.bicep` |
| Governance | workspace + OneLake | Unity Catalog metastore, credential, external locations | `scripts/04-unity-catalog-bootstrap.sh`, `sql/unity_catalog_bootstrap.sql` |
| Item deployment | Fabric REST per item | Declarative Automation Bundles | `bundle/` |

Because of that split, the deployment order is not optional. Storage identity must exist
before governance; governance must exist before any pipeline can resolve a table name.

## Layout

```text
implementation/
├── env.example.sh                      # copy to env.sh, fill in, source it
├── bicep/databricks-foundation.bicep   # workspace, connector, managed container, scoped RBAC
├── sql/unity_catalog_bootstrap.sql     # catalog, schemas, grants, and volumes
├── bundle/                             # versioned pipeline, job, alert, and Genie resources
│   ├── databricks.yml
│   ├── resources/{pipelines,jobs,sql,genie}.yml
│   └── src/                            # pipeline logic and fail-closed gate notebooks
└── scripts/01..08, 99                  # the execution sequence below
```

---

## Step 0 — Set your context

```bash
cd azure-databricks/implementation
cp env.example.sh env.sh
$EDITOR env.sh
source env.sh
```

**Teaching note.** Every value in `env.sh` except the Databricks ones is read from your
current HLS deployment. You are not choosing new source infrastructure; you are pointing
a second destination at the same sources. `STORAGE_ACCOUNT_NAME` and `EVENTHUB_NAMESPACE`
must be the live ones, or nothing downstream resolves.

## Step 1 — Preflight (mutates nothing)

```bash
./scripts/01-preflight.sh
```

Checks identity alignment, resource providers, ADLS hierarchical namespace, both source
containers, and both Event Hubs.

**Teaching note.** The Fabric preflight asked "is there an active paid F-SKU capacity?"
That question has no Databricks equivalent, so it is replaced by "is the ADLS account
hierarchical-namespace enabled, in the target region, and do both hubs exist?" Hierarchical
namespace is a hard Unity Catalog external-location requirement, and a region mismatch is
a silent egress bill rather than an error.

## Step 2 — Create the Databricks plane

```bash
./scripts/02-deploy-databricks-foundation.sh
```

Validates, shows an `az deployment group what-if` change set, asks for confirmation, then
creates the Premium workspace, the Access Connector, the `databricks-managed` container,
and scoped RBAC. Outputs land in `.state/foundation-<env>.json`.

**Teaching note on the RBAC split.** This is the most important security decision in the
migration. The connector identity gets:

- `Storage Blob Data Reader` on the **account** so `fhir-export` and `dicom-output` are ingestible
- `Storage Blob Data Contributor` on the **managed container only** so derived Delta can be written
- `Azure Event Hubs Data Receiver` on the namespace, never Data Sender

A single account-wide Contributor grant would let an analytics pipeline overwrite your FHIR
export. Fabric's trusted-workspace access hid that choice behind a workspace identity;
here you make it explicitly.

Afterwards, export the printed variables and authenticate:

```bash
export DATABRICKS_HOST="$(jq -r '.workspaceUrl.value' .state/foundation-$ENVIRONMENT.json)"
export ACCESS_CONNECTOR_ID="$(jq -r '.accessConnectorId.value' .state/foundation-$ENVIRONMENT.json)"
export MANAGED_LOCATION_URL="$(jq -r '.managedLocationUrl.value' .state/foundation-$ENVIRONMENT.json)"
export FHIR_EXPORT_URL="$(jq -r '.fhirExportUrl.value' .state/foundation-$ENVIRONMENT.json)"
export DICOM_OUTPUT_URL="$(jq -r '.dicomOutputUrl.value' .state/foundation-$ENVIRONMENT.json)"
databricks auth login --host "$DATABRICKS_HOST"
```

### Step 2b — The one manual privileged action

In the Databricks **account console**: Catalog → Metastores → assign the regional metastore
to this workspace.

**Teaching note.** Metastore assignment is account-scoped, not workspace-scoped, and it is
irreversible in practice for a shared metastore. No script in this package performs it,
because a wrong assignment affects every other workspace on that metastore.

## Step 3 — Give Databricks read-only stream access

```bash
./scripts/03-configure-eventhubs-access.sh
```

Creates consumer groups `hls-dbx-telemetry` and `hls-dbx-claims`, creates a **Listen-only**
authorization rule, asserts the rights are exactly `Listen`, stores the key in Key Vault,
and mirrors it into a Databricks secret scope.

**Teaching note.** Two traps here.

1. The existing `emulator-access` rule has `Send` and `Listen` at namespace scope. Reusing it
   would let the analytics plane inject synthetic clinical events. The script fails if the new
   policy has anything other than `Listen`.
2. Each hub needs its own consumer group. In Fabric you were forced into two Eventstreams
   because a topology owns one `DefaultStream`. In Databricks one pipeline can host both
   streams, but shared consumer groups would make the two feeds fight over offsets.

## Step 4 — Build the governance boundary

```bash
./scripts/04-unity-catalog-bootstrap.sh
```

Creates or reuses the serverless SQL warehouse needed for bootstrap, creates the storage
credential and three external locations through the Unity Catalog API, then creates the
`hls_<env>` catalog with `bronze/silver/gold/ops/meta` schemas, least-privilege grants,
two read-only source volumes, and a managed ingestion-state volume. It proves the boundary
behaves: source paths list and managed writes succeed.

**Teaching note on the OneLake replacement.** A OneLake shortcut is one object that bundles
identity, path, and access. Unity Catalog splits it into three:

1. **Storage credential** — the identity (your Access Connector)
2. **External location** — the path plus a reference to that credential
3. **External volume** — a governed, queryable handle onto that path

The source locations are created with `read_only=true`; Azure RBAC independently grants the
Access Connector read-only account access. API `skip_validation` avoids granting temporary
write/delete rights merely to satisfy Unity Catalog's create-time validation probe.

## Step 5 — Deploy workload resources as one release

```bash
./scripts/05-deploy-bundle.sh
```

Runs `bundle validate`, then `bundle plan`, asks for confirmation, then
`bundle deploy --fail-on-active-runs`, then prints the summary.

**Teaching note on why there are five pipelines, not one.** A Lakeflow pipeline publishes into
a single catalog schema. Fabric let one workspace hold Bronze, Silver, and Gold lakehouses
together, so schema boundaries were free. Here the schema boundary is the pipeline boundary:

| Pipeline | Schema | Replaces |
|---|---|---|
| `hls-bronze-files` | `bronze` | OneLake shortcuts + HDS Bronze ingestion |
| `hls-silver-files` | `silver` | HDS clinical and imaging Silver pipelines |
| `hls-bronze-streams` | `bronze` | `MasimoTelemetryStream`, `ClaimsRTIStream` |
| `hls-silver-streams` | `silver` | enriched KQL alert functions |
| `hls-gold-products` | `gold` | OMOP analytics, quality/payer materialization |

If `ALERT_EMAIL` is empty, the clinical alert deploys paused with no recipient. That is
deliberate: no default address is ever invented.

The same release creates five curated Genie Agents that preserve the Fabric Data Agent domains:
Patient 360, Clinical Triage, Multi-Layer Imaging Cohort, Payer Ops Triage, and Healthcare
Graph. They use governed `agent_*` Gold products, tested SQL examples, and the existing
serverless warehouse. The graph agent is explicitly relational: Databricks has no one-to-one
Fabric IQ ontology object, so it traverses a typed edge table and never claims ontology identity.

Authors open **Genie Agents** in the workspace; consumers use the app switcher → **Genie One**
or a bundle-summary URL. Share `CAN RUN`, then grant `SELECT` only on the attached Unity Catalog
objects. The author supplies warehouse compute credentials, but every data query is still
authorized and attributed as the end user's Unity Catalog identity.

## Step 6 — Run the pipelines and pass the gates

```bash
./scripts/06-run-and-gate.sh
```

Runs the batch path (Bronze files → Silver files → Silver gate), then the scheduled serverless
path (Bronze streams → Silver streams → freshness gate → Gold → Gold gate). The latter runs
every five minutes to stay inside the ten-minute freshness gate and scales to zero between
triggered updates. `max_concurrent_runs: 1` plus disabled run queueing drops overlapping ticks
instead of accumulating stale five-minute runs behind a slow serverless startup.

**Teaching note on why gates are jobs, not notes.** The Fabric deployment learned this the
hard way: a created Eventstream with `Running` nodes and zero fresh rows is a failure, and a
queryable semantic model with every fact table empty is a failure. So:

- `gates_silver.py` fails on empty required tables, orphan encounters, duplicate device
  associations, and a partial imaging estate (studies present, no instances joined).
- `gates_gold.py` allows an empty product **only** when its upstream Silver cohort is also
  empty, and never allows a wholly blank Gold estate.
- `gates_streams.py` fails on stale events, on Bronze-with-empty-Silver, and on row count
  not equal to distinct `event_key` count, which is how at-least-once duplication surfaces.

**Teaching note on at-least-once.** Event Hubs through the Kafka connector is at-least-once.
`silver_realtime.py` therefore builds a deterministic `event_key` (`sha2(device_id|observed_at)`),
sets a watermark, and dedupes on that key. Without it, one replay becomes one duplicate page
to a clinician.

## Step 7 — Prove the deployment, do not assume it

```bash
python3 scripts/07-validate-deployment.py --environment "$ENVIRONMENT"
python3 scripts/08-validate-genie-agents.py --environment "$ENVIRONMENT" --ask
```

Both commands are read-only. The first validates storage, Silver/Gold rows, references, stream
freshness, pipelines, and the clinical alert. The second requires all five Genie definitions,
their exact governed sources, at least five curated SQL examples each, nonempty direct SQL
baselines, and one grounded live conversation per agent. A skipped or failed check is not a pass.
Curation is deployed code; changes belong in `resources/genie.yml`, not an untracked portal draft.

## Teardown

```bash
DELETE_CATALOG=true DELETE_WAREHOUSE=true DELETE_FOUNDATION=true ./scripts/99-teardown.sh
```

Order: pause schedules → export final evidence → destroy bundle resources → optionally drop
the catalog, locations, credential, and bootstrap warehouse → optionally delete the workspace
and connector by the exact resource IDs recorded at creation.

**Teaching note.** All destructive flags default to `false`. Workspace deletion requires
`.state/foundation-<env>.json`; warehouse deletion requires `.state/warehouse-<env>.json`
with `created_by_bootstrap=true`. Deleting a shared metastore, credential, or storage account
by name prefix is how a demo teardown takes out someone else's environment.

## What is still yours to decide

| Decision | Why no artifact commits to it |
|---|---|
| AI/BI dashboard layout | needs your reviewed visual and measure set |
| Ontology semantics | there is no one-to-one Fabric IQ graph; encode it in comments, constraints, metric views |
| Network isolation profile | VNet injection and private endpoints are a production profile, not a demo default |
| Orchestrator integration | `Deploy-All.ps1` and the FastAPI activities still call Fabric; a destination adapter must migrate every caller |

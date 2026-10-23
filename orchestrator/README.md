# Deployment Orchestrator — FastAPI Backend + React UI

The orchestrator provides a visual deployment experience for the HLS Data Accelerator. It consists of a Python FastAPI backend and a React + Fluent UI frontend. Deployment invokes `Deploy-All.ps1`; local and hosted teardown use the same `shared/full_teardown.py` implementation as the root `Teardown-All.ps1` wrapper. The [hosted deployer](../hosted/README.md) runs this backend in isolated per-user Container Apps behind an Entra-authenticated gateway.

`POST /api/teardown/start` and each job in `POST /api/teardown/batch/start` require an explicit deployment `subscription_id`, with an optional `expected_tenant_id` guard. Missing subscriptions return HTTP 400; an invalid batch is rejected before any job starts. The API never defaults from `HLS_SUBSCRIPTION_ID` or the Azure CLI account. Front-end discovery includes owned Rayfin, cardiology and DICOM viewer resources; shared/unrelated groups are skipped with reasons. `front_end_resource_groups` explicitly selects groups subject to ownership checks, and `discover_front_ends: false` disables automatic group discovery. The **Databricks Unity Catalog** phase removes objects bound to the deployment's Access Connector before Azure resource group deletion. The shared hosted control plane is not a deployment-owned front end.

The former Azure Functions host and its name-based front-end ownership exception have been removed. The backend is FastAPI in both local and hosted modes.

Records preserve `customStatus.subscriptionId`, `customStatus.expectedTenantId` and `customStatus.frontEndResourceGroups`; final results are in `output.teardown` (`plan`, `deleted`, `failures`, `skipped`, `status`). Interrupted-teardown reconciliation uses only the record's pinned `subscriptionId` and skips legacy unpinned records.

For read-only discovery from `orchestrator/`, run `python -m shared.full_teardown --subscription <subscription> --workspace <workspace> --resource-group <rg> --expected-tenant <tenant> --delete-workspace --delete-resource-group --plan`. The root wrapper exposes the same preview as `Teardown-All.ps1 -SubscriptionId <subscription> -FabricWorkspaceName <workspace> -ResourceGroupName <rg> -ExpectedTenantId <tenant> -Plan`. Plans delete nothing. See [teardown parameters and confirmation behavior](../README.md#teardown).

## 💻 Developer Quick Start

This sub-folder contains the FastAPI backend and React frontend source code for the Deployment Orchestrator dashboard.

> [!NOTE]
> **Deployment Prerequisites:**
> Before setting up your development workspace, make sure your machine and subscription contexts meet all prerequisites. See the root [Prerequisites](../README.md#prerequisites) and [Quick Start](../README.md#deploy).

---

### Local Development Setup

To run, debug, or contribute to the orchestrator services:

#### 1. Configure the Python FastAPI Backend
From the repository root, activate the Python virtual environment and run the FastAPI server:

```bash
# Navigate to the orchestrator sub-directory
cd orchestrator

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1   # Windows (PowerShell)
# source .venv/bin/activate    # macOS / Linux (bash)

# Launch the FastAPI local server (runs on port 7071)
python local_server.py
```

#### 2. Configure the Vite React Frontend
In a separate terminal session, install dependencies and start the Vite development server:

```bash
# Navigate to the frontend UI sub-directory
cd orchestrator-ui

# Launch the Vite development server (runs on port 5173)
npm run dev
```

Open your browser and navigate to [http://localhost:5173](http://localhost:5173) to load the deployment dashboard.

## Architecture

- **FastAPI Backend** — REST API that invokes PowerShell deployment scripts, streams logs in real-time, and manages deployment state in SQLite
- **React Frontend** — Fluent UI v9 dashboard with Deploy wizard, Run History, Teardown scanner, and Phase Monitor
- **SQLite Database** — Persistent deployment/teardown history, resource locks, and form history

## Runtime Database Files

Without `HLS_DATA_DIR`, the orchestrator keeps the existing local layout: SQLite
under `orchestrator/shared/`, logs and cache under `orchestrator/`, and deployment
ledgers under the repository's `state-tracking/`. Do not commit SQLite WAL/SHM files.

When `HLS_DATA_DIR` is set, it contains deployment history, form history, logs,
session logs, resource caches, graph backups and `state-tracking/`. The live SQLite
database is **always on local disk** in a private temporary directory, never on the
Azure Files mount. Startup restores `HLS_DATA_DIR/orchestrator.db`; committed changes
are snapshotted with SQLite's backup API every ten seconds and on graceful shutdown.
`HLS_STATE_DIR` points child PowerShell processes at the durable deployment ledgers.
Azure CLI and PowerShell credentials remain in container-local `HOME`, not this volume.

### Sandbox image locally

Use a clean build context containing this repository at its root and the pinned
Wardflow checkout at `wardflow/`, including `wardflow/.pinned-commit`. The image's
`hosted/sandbox/Dockerfile.dockerignore` replaces the emulator's root ignore rules;
it excludes local state, secrets, virtual environments and `node_modules`.

```bash
docker build --platform linux/amd64 -f hosted/sandbox/Dockerfile -t hls-sandbox .
docker volume create hls-sandbox-data
docker run --rm --init -p 127.0.0.1:7071:7071 \
  -e HLS_DATA_DIR=/data -v hls-sandbox-data:/data hls-sandbox
```

This local command leaves `HLS_HOSTED` unset and serves the built UI at
`http://localhost:7071`. To exercise the hosted sign-in panel, use the gateway or
set `HLS_HOSTED=1`, a random `HLS_GATEWAY_KEY`, and `HLS_SANDBOX_USER_EMAIL`,
`HLS_SANDBOX_USER_OID`, `HLS_SANDBOX_USER_TID`; every request except `GET /api/health`
must then carry the matching `X-HLS-Gateway-Key`. The gateway supplies trusted
`X-HLS-User-*` headers. Bind mounts must be writable by UID 10001. Mount only `/data`,
never `/home/hls`: removing the container must also remove Azure sign-in caches.
The image uses `WARDFLOW_ROOT=/app/wardflow`, listens on 7071, and runs Python 3.13
and PowerShell 7 as a non-root user. Deployment requests require explicit tenant
and subscription UUIDs; the UI obtains them from the authenticated Azure context.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/deploy/start` | Start a new deployment |
| GET | `/api/deploy/{instanceId}/status` | Get deployment status |
| POST | `/api/deploy/{instanceId}/cancel` | Cancel a running deployment |
| POST | `/api/teardown/start` | Start teardown |
| GET | `/api/deployments` | List deployment history |
| DELETE | `/api/deploy/{instanceId}` | Delete a deployment record |
| POST | `/api/deployments/clear` | Clear all deployment history |
| GET | `/api/deploy/check-existing` | Check for prior deployment by workspace/RG |
| GET | `/api/scan/subscriptions` | List Azure subscriptions |
| POST | `/api/scan/resources/start` | Start incremental teardown resource scan |
| GET | `/api/scan/resources/{scanId}` | Poll scan progress |
| GET | `/api/scan/capacities` | List Fabric capacities |
| GET/POST/DELETE | `/api/locks/{resourceId}` | Manage teardown resource locks |
| GET | `/api/deployment-capacity/{rgName}` | Look up capacity for a resource group |

## UI Pages

| Page | Route | Description |
|------|-------|-------------|
| **Deploy** | `/` | Deployment wizard with naming convention, capacity selection, and explicit keep/reseed controls for existing completed deployments |
| **History** | `/history` | Run history with filters (type, name, date range), deployment/teardown badges |
| **Teardown** | `/teardown` | Resource scanner with incremental discovery, paired RG/workspace highlighting, locks |
| **Monitor** | `/monitor/:id` | Real-time phase progress with milestone track, phased log routing, resource verification |

## Reseed an Existing Completed Deployment

The Deploy wizard offers data replacement only for an existing deployment record; teardown records are not reseed targets.

1. Open **Deploy** and enter or select the completed deployment's name. The wizard detects its workspace, resource group, live FHIR counts, and emulator state.
2. Under **Existing FHIR data strategy**, select **Reseed and replace data**. **Keep and reuse current data** remains the safe default.
3. Set **Patient Count** to the final replacement total. This is not an increment: entering `200` replaces the current FHIR dataset with 200 generated patients.
4. Leave **Use cached canonical Synthea fixture** off for a custom total. Selecting it locks the final total to the canonical 100-patient fixture.
5. Review the permanent replacement warning, then preview and start the deployment.

Reseed mode cannot be combined with patient reuse. It forces Synthea generation, the FHIR loader, device associations, a fresh FHIR export, and downstream HDS pipelines. The loader bulk-deletes existing FHIR resources before loading the new set, and stale export blobs are removed before the replacement export.

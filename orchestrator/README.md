# Deployment Orchestrator — FastAPI Backend + React UI

The orchestrator provides a visual deployment experience for the HLS Data Accelerator. It consists of a Python FastAPI backend that calls the same PowerShell scripts (`Deploy-All.ps1`, `Teardown-All.ps1`) and a React + Fluent UI frontend.

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

The orchestrator uses a local SQLite database under `orchestrator/shared/` at runtime.
You may see sidecar files such as `orchestrator.db-wal` and `orchestrator.db-shm` while
the app is running. These are SQLite write-ahead logging artifacts, are machine-local,
and are not required for end users to build or run from source in a fresh environment.
They should remain gitignored.

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

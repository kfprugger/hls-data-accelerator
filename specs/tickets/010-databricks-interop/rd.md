# 010: Azure Databricks Zero-Copy OneLake Interoperability

**Status:** ready
| **Risk** | Medium: Databricks SQL execution hangs or writes unvalidated interop payload to imaging lakehouse |

## Summary
Provide an automated CLI script that executes an Azure Databricks Serverless SQL query directly against the OneLake external location over the shared patient360 / silo tables (validating access to the 15 TCGA patients without copying data), writes an execution proof JSON to the imaging lakehouse Files area, and displays the result as an interoperability proof card on the Rayfin Data Map page.

## Why
Enterprise healthcare architectures frequently leverage Azure Databricks alongside Microsoft Fabric. Proving that Databricks Unity Catalog can query the exact same OneLake Delta tables in place via an external location—without pipeline replication or custom file exports—demonstrates true zero-copy multi-engine analytics and eliminates concerns regarding data lock-in.

## User stories
- As an enterprise data architect, I want to see tangible evidence on the Data Map that Databricks queries the same OneLake tables with zero copies, so that I can be confident that Fabric integrates cleanly with existing Databricks environments.
- As a technical presenter or verification runner, I want a standalone CLI tool (`09-onelake-interop-proof.py`) with bounded polling and timeouts that queries OneLake from Databricks SQL and records a tamper-evident proof file, so that cross-engine interoperability can be verified deterministically.
- As a frontend engineer developing locally, I want the Data Map to render the Databricks interoperability card from a local fixture when offline, so that UI features can be built without a live Databricks connection.

## Functional requirements
- **FR-1**: Add a standalone CLI script `azure-databricks/implementation/scripts/09-onelake-interop-proof.py` supporting `--dry-run`, `--live`, and `--cleanup` modes, defaulting to `--dry-run`.
- **FR-2**: In `--dry-run` mode, `09-onelake-interop-proof.py` must formulate the Databricks SQL statement (`SELECT count(DISTINCT patient_id) AS tcga_patient_count FROM <catalog>.<schema>.patient`), validate SQL warehouse configuration, print the statement and target OneLake external location URL, and exit 0 without issuing live writes.
- **FR-3**: In `--live` mode, `09-onelake-interop-proof.py` must submit the query to the Databricks SQL Statement Execution API (`/api/2.0/sql/statements`), poll with bounded retries (up to 36 attempts at 5-second intervals = 180 seconds total) until completion, assert that the returned count equals 15, and generate a JSON proof object:
  ```json
  {
    "timestamp": "<ISO8601>",
    "engine": "Azure Databricks Serverless SQL",
    "statement": "SELECT count(DISTINCT patient_id) AS tcga_patient_count FROM hls_dev.clinical.patient",
    "warehouseId": "<warehouse_id>",
    "rowCount": 15,
    "executionTimeMs": 1420,
    "oneLakeExternalLocation": "abfss://med-1103a@onelake.dfs.fabric.microsoft.com/clinical_lakehouse",
    "status": "SUCCEEDED",
    "zeroCopyVerified": true
  }
  ```
- **FR-4**: In `--live` mode, `09-onelake-interop-proof.py` must write the generated JSON proof to `Files/interop/databricks_proof.json` in `imaging_lakehouse` via the OneLake DFS REST API (using an Azure storage access token and header `x-ms-fabric-skill: search-consumption-cli`).
- **FR-5**: In `--cleanup` mode, `09-onelake-interop-proof.py` must delete `Files/interop/databricks_proof.json` from `imaging_lakehouse` via DFS REST API and exit 0.
- **FR-6**: The backend API (via a new UDF or extension to `getDataMap` in `function_app.ts` and `local/api.ts`) must return the Databricks interoperability payload:
  - Live mode: reads `Files/interop/databricks_proof.json` from `imaging_lakehouse`.
  - Local mode: reads `rayfin-imaging/local/fixtures/databricks_proof.json`.
- **FR-7**: The Rayfin Data Map page (`rayfin-imaging/src/pages/DataMap.tsx`) must display an "Azure Databricks Interoperability" card showing:
  - Engine name and warehouse ID.
  - Verified SQL statement.
  - Row count result (15 TCGA patients).
  - Execution latency and timestamp.
  - Target OneLake external location path.
  - Verification badge: `Zero-copy read verified`.
- **FR-8** (Fresh deployments): The script `09-onelake-interop-proof.py` must be a standalone, idempotent CLI script that ticket 012 can execute from `AddonRunner` during automated environment verification without requiring modifications to `orchestrator/activities/addons.py` or `Deploy-All.ps1`.

## Non-functional requirements
- **NFR-1**: Responsiveness: The Databricks Interoperability card on the Data Map must scale gracefully across viewports from 1280 px down to 360 px with no horizontal overflow.
- **NFR-2**: Bounded execution: The CLI script must strictly enforce a maximum 180-second timeout on Databricks statement polling and a 30-second timeout on OneLake REST operations.
- **NFR-3**: Privacy & Security: The JSON proof must contain aggregate operational metadata only (counts, query string, latencies) and must never log or store individual patient names, PHI, or credentials.

## Edge cases & error handling
- Missing proof file: If `databricks_proof.json` has not yet been created, the Data Map card must display a designed empty state: `Awaiting Databricks verification (run scripts/09-onelake-interop-proof.py)` without crashing or blocking the rest of the page.
- Databricks statement failure or timeout: If the Databricks warehouse is stopped, authentication fails, or execution times out, the CLI must log the error details, exit with return code 1, and refrain from writing a corrupted proof file.
- Unauthenticated Databricks CLI: If required Databricks credentials or configuration are absent, the CLI script must fail fast with a descriptive error message indicating the missing environment variables.

## Out of scope
- Deploying or reconfiguring Databricks clusters, access connectors, or Unity Catalog metastores (covered by earlier scripts 01–06).
- Writing Databricks analytics outputs back into OneLake Delta tables (this feature specifically proves read interoperability).
- Modifying `orchestrator/activities/addons.py` or `Deploy-All.ps1` (owned by ticket 012).

## Affected areas
- `azure-databricks/implementation/scripts/09-onelake-interop-proof.py`: Standalone CLI script for Databricks query execution and proof persistence.
- `azure-databricks/implementation/tests/test_onelake_interop_proof.py`: Unit tests for query formatting, polling, and payload generation.
- `rayfin-imaging/local/fixtures/databricks_proof.json`: Local offline proof fixture.
- `rayfin-imaging/src/pages/DataMap.tsx`: Rendering of the Azure Databricks Interoperability proof card.
- `rayfin-imaging/rayfin/functions/src/function_app.ts`: Function backend logic reading interop proof from OneLake.
- `rayfin-imaging/local/api.ts`: Local backend implementation reading the proof fixture.
- `rayfin-imaging/rayfin/functions/src/types.ts`: Type definitions for `databricksInterop` payload.
- `rayfin-imaging/src/lib/api.ts`: Frontend client types for `databricksInterop`.

## Do not touch
- `orchestrator/activities/addons.py`
- `orchestrator/tests/test_addons.py`
- `Deploy-All.ps1`
- Existing scripts `azure-databricks/implementation/scripts/01` through `08`
- `rayfin-imaging/src/pages/PatientView.tsx`

## Dependencies
- **waits for 003**: Both tickets 003 and 010 modify `DataMap.tsx`, `function_app.ts`, `local/api.ts`, `types.ts`, and `lib/api.ts`. Ticket 003 establishes the baseline zero-copy proof metrics and shortcut schema on the Data Map; ticket 010 introduces the Databricks cross-engine interop card on top of 003's updated layout.
- Depends on `001-local-demo-dataset` for the 15 TCGA patient records.

## Decisions made
- **Agreed with the user**: Add a CLI (`azure-databricks/implementation/scripts/09-onelake-interop-proof.py`) that runs one Databricks SQL statement against the OneLake external location over patient360/silo tables (e.g. count of 15 TCGA patients), with bounded polling and timeout, and writes a small JSON result to imaging lakehouse Files area; surface the last result as a card on the Data Map (UDF + local fixture). Data map edits wait for 003.
- **Decided by the ticket writer**: The proof query tests the clinical silo: `SELECT count(DISTINCT patient_id) AS tcga_patient_count FROM hls_dev.clinical.patient`, verifying exactly 15 records.
- **Decided by the ticket writer**: The output proof is written to `Files/interop/databricks_proof.json` in `imaging_lakehouse`.
- **Decided by the ticket writer**: The Databricks proof card on `DataMap.tsx` is placed immediately following the OneLake shortcut table, highlighting cross-engine zero-copy validation.

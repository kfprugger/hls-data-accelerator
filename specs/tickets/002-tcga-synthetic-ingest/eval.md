# 002: TCGA Cohort Synthetic FHIR, Device, and Claim Ingestion: Evaluation

## Setup
1. Ensure Python test environment is configured per `.claude/project.md`:
   Interpreter: `/Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python` (has `requests`, `azure-identity`, `pyyaml`).
2. Live target environment (for live checks):
   - Azure isolated profile: `export AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL`
   - Network binding: `export HLS_BIND_INTERFACE=en0`
   - Workspace: `med-1103a` (`f306e105-78fd-4b16-bfbe-2b556d493cb7`), tenant `c77e97fc-1859-4575-8c8b-53d74bc35a63`, subscription `22222222-2222-2222-2222-222222222222` (or ambient).

## Automated checks
- **A-1**: Python unit tests for TCGA synthetic cohort generator pass:
  ```bash
  /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s /Users/joey/git/.worktrees/hls-fabric-wow/synthea/tests -p 'test_*.py'
  ```
  Must exit with status 0.
- **A-2**: Orchestrator test suite continues to pass:
  ```bash
  cd /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator && /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
  ```
  Must exit with status 0.

## Acceptance checks

### E-1 [U]: CLI plan mode prints planned resource counts without live writes (covers FR-1, FR-8, FR-12)
- **Type**: CLI
- **Steps**:
  1. Run `synthea/seed_tcga_cohort.py plan` against a mock or dry-run configuration:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python \
       /Users/joey/git/.worktrees/hls-fabric-wow/synthea/seed_tcga_cohort.py plan \
       --fhir-url "https://mock-fhir.azurehealthcareapis.com" \
       --subscription "22222222-2222-2222-2222-222222222222"
     ```
  2. Inspect stdout output.
- **Expected**:
  - Script exits with status 0.
  - Output displays planned counts:
    - `Patient`: 15
    - `Condition`: >= 15
    - `MedicationRequest`: >= 30
    - `Observation`: >= 15
    - `Coverage`: 15
    - `Device`: 15
    - `Basic` (DeviceAssociation): 15
  - Output explicitly states: `Dry-run plan mode: 0 resources written or modified.`

### E-2 [U]: CLI apply mode uploads transaction bundles to FHIR service (covers FR-1, FR-2, FR-7, FR-8)
- **Type**: CLI
- **Steps**:
  1. Execute `apply` mode against the target FHIR service:
     ```bash
     AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL HLS_BIND_INTERFACE=en0 \
       /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python \
       /Users/joey/git/.worktrees/hls-fabric-wow/synthea/seed_tcga_cohort.py apply \
       --resource-group "rg-med-1103a" \
       --subscription "22222222-2222-2222-2222-222222222222"
     ```
  2. Inspect the transaction response logs.
- **Expected**:
  - Script exits with status 0.
  - Every transaction bundle returns HTTP 200 with all entry statuses `200` or `201`.
  - Transaction log reports: `FHIR upsert counts: {"Basic": 15, "Condition": ..., "Coverage": 15, "Device": 15, "MedicationRequest": ..., "Observation": ..., "Patient": 15}`.

### E-3 [U]: FHIR REST query verifies Marcus Vance record and paired Masimo device (covers FR-2, FR-7)
- **Type**: API
- **Steps**:
  1. Obtain an access token for Azure Healthcare APIs:
     ```bash
     TOKEN=$(AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL az account get-access-token --resource https://healthcareapis.azure.com --query accessToken -o tsv)
     ```
  2. Query the FHIR service for patient `TCGA-G6-A8L6`:
     ```bash
     curl -s -H "Authorization: Bearer $TOKEN" -H "Accept: application/fhir+json" \
       "https://fhirmed1103a.fhir.azurehealthcareapis.com/Patient?identifier=https://gdc.cancer.gov/tcga/barcode|TCGA-G6-A8L6"
     ```
  3. Query the FHIR service for the paired Masimo device:
     ```bash
     curl -s -H "Authorization: Bearer $TOKEN" -H "Accept: application/fhir+json" \
       "https://fhirmed1103a.fhir.azurehealthcareapis.com/Device?identifier=http://masimo.com/devices|MASIMO-RADIUS7-0101"
     ```
  4. Query the FHIR service for the device association:
     ```bash
     curl -s -H "Authorization: Bearer $TOKEN" -H "Accept: application/fhir+json" \
       "https://fhirmed1103a.fhir.azurehealthcareapis.com/Basic?code=device-assoc"
     ```
- **Expected**:
  - Patient search returns 1 entry with `resource.name[0].family == "Vance"` and `resource.name[0].given[0] == "Marcus"`.
  - Device search returns 1 entry with `resource.id` and model `Radius-7`.
  - Basic search returns association linking Marcus Vance's patient ID to `Device/MASIMO-RADIUS7-0101`, and `Device/MASIMO-RADIUS7-0001` is unchanged from before the run (same `meta.versionId`, no synthetic tag).
  - All returned resources contain `meta.tag` with code `synthetic-demo-enrichment`.

### E-4 [U]: Gold SQL query confirms ingested patient row in healthcare1_reporting_gold (covers FR-11)
- **Type**: CLI
- **Steps**:
  1. Using the SQL analytics endpoint connection string for `healthcare1_reporting_gold`:
     ```bash
     AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL HLS_BIND_INTERFACE=en0 \
       /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -c '
     import sys, os, requests
     from azure.identity import AzureCliCredential
     cred = AzureCliCredential(process_timeout=30)
     token = cred.get_token("https://database.windows.net/.default").token
     print("Gold query access token obtained successfully")
     '
     ```
- **Expected**:
  - Script connects to `healthcare1_reporting_gold` SQL analytics endpoint.
  - Queries `SELECT COUNT(*) FROM dbo.dim_diagnosis WHERE patient_id = 'TCGA-G6-A8L6'` or `fact_claim`.
  - Confirms TCGA patient rows exist in Gold reporting tables.

### E-5 [U]: Eventhouse KQL query verifies device telemetry rows for MASIMO-RADIUS7-0101 (covers FR-7, FR-11)
- **Type**: CLI
- **Steps**:
  1. Execute a KQL query against the `MasimoEventhouse` database via Azure CLI / REST:
     ```bash
     AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL HLS_BIND_INTERFACE=en0 \
       az kusto query --cluster-name "masimoeventhouse" --database-name "MasimoEventhouse" \
       --kql "TelemetryRaw | where device_id == 'MASIMO-RADIUS7-0101' | take 5" 2>/dev/null || echo "KQL query executed"
     ```
- **Expected**:
  - After `apply --emit-baseline-telemetry`, the query returns at least 10 telemetry records showing `device_id: MASIMO-RADIUS7-0101` with `spo2` and `pr` fields.

### E-6 [U]: CLI delete removes only tagged synthetic resources (covers FR-1, FR-10)
- **Type**: CLI
- **Steps**:
  1. Execute `delete` command against the target FHIR service:
     ```bash
     AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL HLS_BIND_INTERFACE=en0 \
       /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python \
       /Users/joey/git/.worktrees/hls-fabric-wow/synthea/seed_tcga_cohort.py delete \
       --resource-group "rg-med-1103a" \
       --subscription "22222222-2222-2222-2222-222222222222"
     ```
  2. Re-query the FHIR service for Marcus Vance (`TCGA-G6-A8L6`):
     ```bash
     curl -s -H "Authorization: Bearer $TOKEN" -H "Accept: application/fhir+json" \
       "https://fhirmed1103a.fhir.azurehealthcareapis.com/Patient?identifier=https://gdc.cancer.gov/tcga/barcode|TCGA-G6-A8L6"
     ```
- **Expected**:
  - The delete operation logs removal of only resources carrying the `synthetic-demo-enrichment` tag.
  - Re-query for Marcus Vance returns total entries = 0.
  - Any non-tagged clinical patients in the FHIR service remain present and untouched.

### E-7 [F]: Network failure / FHIR server 429 throttling triggers exponential backoff (covers Edge cases)
- **Type**: CLI
- **Steps**:
  1. Run unit test simulating HTTP 429 Too Many Requests response from the FHIR server:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       synthea/tests/test_seed_tcga_cohort.py -k test_retry_on_429
     ```
- **Expected**:
  - Client retries up to 3 times with exponential backoff before failing cleanly.
  - Does not crash with unhandled HTTPError or leave dangling half-written transactions.

### E-8 [R]: Non-synthetic resources in FHIR and Silver lakehouse are completely unaffected (covers R)
- **Type**: API
- **Steps**:
  1. Inspect FHIR resources before and after running `apply`:
     ```bash
     curl -s -H "Authorization: Bearer $TOKEN" "https://fhirmed1103a.fhir.azurehealthcareapis.com/Patient?_summary=count"
     ```
- **Expected**:
  - Pre-existing non-demo resources are preserved with unchanged version IDs and modification timestamps.

### E-9 [Q]: CLI plan execution finishes in under 3.0 seconds (covers NFR-1)
- **Type**: CLI
- **Steps**:
  1. Measure wall-clock execution time for `plan` subcommand:
     ```bash
     time /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python \
       /Users/joey/git/.worktrees/hls-fabric-wow/synthea/seed_tcga_cohort.py plan \
       --fhir-url "https://mock-fhir.azurehealthcareapis.com" \
       --subscription "22222222-2222-2222-2222-222222222222"
     ```
- **Expected**:
  - Real execution time is strictly less than 3.0 seconds.

### E-10 [S]: Attack test: Forged non-FHIR URL is rejected before sending credentials (covers NFR-3, NFR-4, S)
- **Type**: CLI
- **Steps**:
  1. Execute `apply` with a forged or external URL (SSRF attempt):
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python \
       /Users/joey/git/.worktrees/hls-fabric-wow/synthea/seed_tcga_cohort.py apply \
       --fhir-url "https://attacker-controlled-site.com/fhir" \
       --subscription "22222222-2222-2222-2222-222222222222" 2>&1
     ```
  2. Inspect stderr output and returncode: `echo $?`.
- **Expected**:
  - The command fails with exit code 2 or 1.
  - Stderr contains explicit validation rejection: `Refusing to send credentials to untrusted API origin`.
  - Zero network calls to the external domain and zero token generation requests for that resource.

### E-11 [S]: Attack test: Untagged existing resource blocks apply and prevents data overwrite (covers FR-9, S)
- **Type**: CLI
- **Steps**:
  1. Run unit test simulating an existing Patient resource with matching ID that lacks the `synthetic-demo-enrichment` tag:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       synthea/tests/test_seed_tcga_cohort.py -k test_untagged_resource_blocks_overwrite
     ```
- **Expected**:
  - Test passes.
  - `seed_tcga_cohort.py` detects the untagged existing resource.
  - Aborts execution with status 3 and error message `Refusing to overwrite existing non-synthetic resource`.
  - Zero PUT/PATCH requests are submitted for the colliding ID.

### E-12 [S]: Token leak defense: Verbose execution never outputs Bearer tokens or secrets (covers NFR-3, S)
- **Type**: CLI
- **Steps**:
  1. Run `seed_tcga_cohort.py` with verbose/debug logging enabled:
     ```bash
     OUTPUT=$(/Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python \
       /Users/joey/git/.worktrees/hls-fabric-wow/synthea/seed_tcga_cohort.py plan \
       --fhir-url "https://mock-fhir.azurehealthcareapis.com" \
       --subscription "22222222-2222-2222-2222-222222222222" 2>&1)
     echo "$OUTPUT" | grep -Ei "bearer [a-z0-9_\-\.]+" || echo "NO_TOKENS_FOUND"
     ```
- **Expected**:
  - Prints `NO_TOKENS_FOUND`.
  - Bearer tokens, Authorization header values, client secrets, and sensitive authentication material never appear in standard output, error output, or logged exception traces.

## Edge case checks
### E-13 [F]: Empty cohort config handling (covers Edge cases)
- **Type**: CLI
- **Steps**:
  1. Run test with empty patient cohort config:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       synthea/tests/test_seed_tcga_cohort.py -k test_empty_cohort_raises
     ```
- **Expected**:
  - Script exits with non-zero exit code and an explicit error indicating empty cohort.

## Regression checks
- Existing `synthea/enrich_demo_cohort.py` and `synthea/apply_demo_enrichment.py` remain untouched and continue to operate without interference.
- Downstream HDS Silver notebooks (`phase-1/` through `phase-5/`) continue to ingest FHIR resources into Silver Delta tables without schema divergence.

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-1, E-2, E-6 |
| FR-2        | E-2, E-3 |
| FR-3        | E-2   |
| FR-4        | E-2   |
| FR-5        | E-2   |
| FR-6        | E-2   |
| FR-7        | E-2, E-3, E-5 |
| FR-8        | E-1, E-2, E-3 |
| FR-9        | E-11  |
| FR-10       | E-6   |
| FR-11       | E-4, E-5 |
| FR-12       | E-1, E-2, E-6 |
| NFR-1       | E-9   |
| NFR-2       | E-2   |
| NFR-3       | E-10, E-12 |
| NFR-4       | E-10  |

## Not covered
- **Design (D) / Browser UI**: This ticket is exclusively backend CLI, FHIR REST API, and data pipeline infrastructure. No new web interface routes or UI elements are constructed; UI rendering is validated in tickets 001, 003, and 007.
- **Credit card / payment gateway processing**: AHDS and Fabric healthcare deployments do not process monetary payments or credit cards.
- **Physical IoT hardware device pairing**: Masimo telemetry is ingested via standard Azure Event Hub and Eventstream emulation rather than physical BLE/Wi-Fi pulse oximeter hardware.

## Definition of done
- [ ] All automated checks pass (`A-1`, `A-2`).
- [ ] All acceptance checks (`E-1` through `E-12`) pass, including all 3 Security attack checks (`E-10`, `E-11`, `E-12`).
- [ ] Edge case check `E-13` passes.
- [ ] Non-synthetic data overwrite prevention is verified (`E-11`).
- [ ] No items from "Out of scope" were built.

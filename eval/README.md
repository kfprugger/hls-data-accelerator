# Deployment Evaluation Harness

`deployment_eval_harness.py` validates that a completed HLS Data Accelerator
deployment's **user-facing surfaces actually work** — not merely that the Fabric
items exist. Run it after any deployment (or wire it into `Deploy-All.ps1` as a
post-deploy gate).

## What it checks

| Category | What "pass" means | Catches |
|----------|-------------------|---------|
| **deployment_preflight** | Latest deployment/teardown completed without error logs; all live preflight checks pass without warnings | Stale run history, partial teardown, auth/context drift, missing prerequisites |
| **telemetry_readiness** | Both test producers and every Eventstream node run; both destination tables receive current events | Paused producers/nodes, stale backlog, timestamp drift |
| **reports** | Every model is queryable and all enumerated backing tables return rows | Connection/query failures and empty report facts |
| **report_layout** | Every report page has more than one analytical visual | Single-card/placeholder report pages |
| **rti** | Every KQL/RTI dashboard's backing Eventhouse tables and functions return data | Empty telemetry, alerts, location maps, and payer worklists |
| **agents** | Every published DataAgent returns a grounded domain-specific answer without error/apology text | Unpublished agents, rejected tools, irrelevant nonempty answers |
| **operations_agents** | Fresh authenticated dedicated-backend API evidence has complete response and usable configuration | CLI-token blind spot, truncated goals/instructions, missing knowledge |
| **browser_surfaces** | Fresh Edge Work - Brakekat evidence renders every report page without visual errors and three report-linked OHIF images | API-queryable models whose visuals or DICOM canvas still fail |

It auto-resumes the Fabric capacity if paused (Direct Lake, KQL, and agent runs all
fail while the F64 is suspended), and retries transient transport (SSL/network) blips.

## Usage

```bash
# full run (reports + rti + agents)
python3 eval/deployment_eval_harness.py --workspace med-0719

# persist machine-readable results
python3 eval/deployment_eval_harness.py --workspace med-0719 --json-out eval/med-0719-eval.json

# skip a category (agents are the slowest — each run polls up to ~4 min)
python3 eval/deployment_eval_harness.py --workspace med-0719 --skip agents

# do not auto-resume the capacity (fail fast instead)
python3 eval/deployment_eval_harness.py --workspace med-0719 --no-capacity-resume
```

### Options

- `--workspace`: Fabric workspace display name (required)
- `--resource-group`: Azure resource group for emulator containers (default: `rg-{workspace}`)
- `--subscription`: Azure subscription ID for container lookups (optional)
- `--readiness-timeout`: Timeout for telemetry readiness in seconds (default: `600`)
- `--azure-config-dir`: Path to Azure CLI config dir (default: `/Users/joey/.azure-isolated/BrakeKat`)
- `--json-out`: Write full results JSON to path
- `--skip`: Skip a category (`reports`, `agents`, `rti`); can be repeated
- `--no-capacity-resume`: Do not auto-resume the capacity
- `--operations-evidence`: Fresh JSON from the authenticated OperationsAgent dedicated API flow.
- `--browser-evidence`: Fresh Edge **Work - Brakekat** rendering evidence for reports and report-linked OHIF studies. API checks remain primary; this covers only what APIs cannot prove.
- `--orchestrator-url`: Local orchestrator API base used for deployment history and preflight checks.

### Execution Flow

1. **Capacity Validation:** Requires the Fabric F64 capacity to be `Active`, resuming it when needed. `--no-capacity-resume` disables that mutation, not the check: a paused or unreadable capacity aborts.
2. **Telemetry Readiness Gate:** A mandatory pre-flight check that runs before any category is evaluated. It ensures:
   - Azure container groups `masimo-emulator-grp` and `claim-emulator-grp` and their containers are `Running` (starting stopped producers).
   - Both required Fabric Eventstreams exist and every source, stream, and destination node in the workspace is `Running`. **Test policy: always resume from `Now`, never `WhenLastStopped`.** A running stream delivering only old backlog is paused once and resumed from `Now`. This intentionally skips queued history; it is not the production ingestion policy. Missing topology branches or API errors fail closed.
   - The actual Eventhouse destinations for `TelemetryRaw` and `claims_events` contain events generated **and ingested** within the last 5 minutes. Future timestamps and freshly ingested old backlog do not pass. Both streams must pass in the same polling cycle.
   If this gate times out or fails, the harness writes a failure JSON and exits without running reports, RTI, or agent validation.
   Failure JSON retains the latest node states, KQL queries, event/ingestion timestamps, recent event counts, and startup actions. Readiness is mandatory even when `--skip rti` is specified. Producers and streams remain running after evaluation.
3. **Category Validation:** Only if the telemetry readiness gate passes, the script evaluates the requested `reports`, `rti`, and `agents` categories.

Exit code: `0` = all checks passed · `1` = one or more failures · `2` = setup error

Auth uses the local Azure CLI. Default profile is Joey's isolated BrakeKat
(`--azure-config-dir /Users/joey/.azure-isolated/BrakeKat`); tokens are minted for
Fabric, Power BI, and the Eventhouse query endpoint.

## Known Fabric preview manual step

The ontology graph model still requires a one-time portal action after deployment:

1. **Ontology graph models** need `Refresh graph model` in the portal
   (an auto-created companion GraphModel can remain empty → `GraphNotRefreshable`). Ref:
   `phase-4/deploy-ontology.ps1`. Agents use the ontology for vocabulary grounding
   and query the Lakehouse/KQL directly, so the graph refresh is not required for
   agent functionality.

Data Agent staging publication is automated through the typed Fabric DataAgent API,
and the harness validates published agents through their documented MCP endpoints.

## Interpreting results

- `reports` FAIL with "Direct Lake data source connection failed" = the semantic
  model can't read its backing warehouse/lakehouse → visuals render blank. This is a
  real deploy defect (fix the Direct Lake binding / warehouse permissions), not a
  preview limitation.
- `reports` WARN with partial table coverage is not an automatic pass. Distinguish legitimate sparse cohorts from missing report facts in the rendered report; populated patient dimensions do not prove an outreach/appointment report works.
- `agents` FAIL = staging publication, datasource binding, or MCP execution is broken.
- `rti` FAIL = a genuine data-flow problem (pipeline didn't populate the Eventhouse).

# Phase 7 — Payer RTI + Operations

Phase 7 adds an independent payer event stream, KQL-native fraud/high-cost/care-gap scoring, payer operations alerting, operations agents, and cross-domain graph context.

[← Phase 6](phase-6-population-health-and-quality.md) · [Main README](../README.md) · [Interactive diagram](diagrams/phase-7-payer-rti-and-ops.html) · [Diagram source](diagrams/phase-7-payer-rti-and-ops.dataflow.json)

<a href="diagrams/phase-7-payer-rti-and-ops.html">
  <img src="diagrams/phase-7-payer-rti-and-ops.visual-check.1440x900.light.png#gh-light-mode-only" alt="Phase 7 flow from synthetic payer events and quality Gold through claim-stream and ClaimsRTIStream into payer KQL scoring, DevicePayerOntology, operations agents, graph agent, and PayerOpsActivator">
  <img src="diagrams/phase-7-payer-rti-and-ops.visual-check.1440x900.dark.png#gh-dark-mode-only" alt="Phase 7 flow from synthetic payer events and quality Gold through claim-stream and ClaimsRTIStream into payer KQL scoring, DevicePayerOntology, operations agents, graph agent, and PayerOpsActivator">
</a>

## Exit contract

Phase 7 is complete only when:

- The claim emulator sends current events to `claim-stream` when data production is selected.
- `ClaimsRTIStream` has running source, stream, and Eventhouse destination nodes.
- `claims_events` receives fresh rows.
- Fraud, high-cost, care-gap, and unified payer worklist functions execute.
- Required scoring snapshots materialize when this is not a definition-only deployment.
- `PayerOpsActivator` contains the intended rule when a payer operations recipient is supplied.
- HealthcareOpsAgent/Payer Ops Triage and Healthcare Graph Agent have their intended published datasources.
- The graph path has refreshed `DevicePayerOntology` state when cross-domain traversal is selected.

An updated Eventstream definition alone does not prove flow. An OperationsAgent item alone does not prove a usable playbook or conversation.

## Prerequisites

- [Phase 2](phase-2-active-patient-telemetry.md) deployed the shared Eventhouse and clinical alert state.
- [Phase 6](phase-6-population-health-and-quality.md) is recommended for Gold care-gap, risk, and cost context.
- The base Azure resource group has Event Hubs and ACR.
- Operations Agent, Data Agent, Ontology, and Data Activator tenant features are enabled for the selected capabilities.
- Explicit payer notification recipients are reviewed before activating email rules.

## Independent Eventstream topology

Telemetry and payer claims use separate Eventstreams because a Fabric Eventstream topology supports one `DefaultStream`, while these feeds have different schemas and destinations.

| Domain | Azure Event Hub | Fabric Eventstream | Eventhouse destination |
|---|---|---|---|
| Device telemetry | `telemetry-stream` | `MasimoTelemetryStream` | `TelemetryRaw` |
| Payer claims | `claim-stream` | `ClaimsRTIStream` | `claims_events` |

Phase 7 creates and updates only `ClaimsRTIStream`; it does not replace the Phase 2 telemetry topology.

## Payer event contract

The synthetic producer emits professional, institutional, emergency, and pharmacy claim events. The RTI path lands them in `claims_events` and maintains these scoring snapshots when materialization is enabled:

- `fraud_scores`
- `highcost_alerts`
- `care_gap_alerts`

Definition-only/scaffolding mode deploys schemas and functions but deliberately skips the producer and snapshot materialization.

## KQL functions

| Function | Purpose |
|---|---|
| `fn_FraudRisk(60)` | Scores provider velocity, amount outliers, denial patterns, upcoding, and injected demo flags |
| `fn_HighCostTrajectory(90)` | Computes 30/90-day spend, ED use, readmission flags, risk tier, and trajectory |
| `fn_CareGapOnAlert(60)` | Joins current payer events to available Gold care-gap context |
| `fn_PayerOpsWorklist(60)` | Unifies prioritized fraud, high-cost, and care-gap work |
| `agent_FraudRisk()` | Parameter-free agent wrapper |
| `agent_HighCostTrajectory()` | Parameter-free agent wrapper |
| `agent_PayerOpsWorklist()` | Parameter-free unified worklist wrapper |

When Gold care-gap state is unavailable, the deployer installs a schema-compatible fallback so KQL remains callable. That fallback is not evidence that care-gap data exists.

## Operations surfaces

### PayerOpsActivator

A Reflex over `fn_PayerOpsWorklist(60)` sends payer operations notifications when `-PayerOpsEmail` is supplied. No recipient means the Activator is intentionally skipped.

### HealthcareOpsAgent and Payer Ops Triage

The deployer attempts a native `HealthcareOpsAgent` OperationsAgent when supported, with an explicit DataAgent fallback when the item type is unavailable. `Payer Ops Triage` uses payer KQL and available Gold context.

Validate actual published conversational behavior. A successful definition update or item create is not a substitute for playbook/conversation evidence.

### Healthcare Graph Agent

The graph agent combines current payer KQL with `DevicePayerOntology` for patient → device → diagnosis → claim → payer → risk/care-gap traversal. The deployment writes explicit follow-up instructions for refreshing the graph and confirming the ontology attachment/published MCP surface.

## Run it

```powershell
$account = az account show --output json | ConvertFrom-Json

./Deploy-All.ps1 `
  -Phase7 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -PayerOpsEmail "payer-ops@example.org" `
  -ClaimEventRatePerMinute 60 `
  -ExpectedTenantId $account.tenantId `
  -ExpectedSubscriptionId $account.id
```

Useful exclusions:

| Switch | Effect |
|---|---|
| `-SkipPayerRti` | Skips claim stream, KQL scoring, Eventstream, and producer path |
| `-SkipPayerActivator` | Keeps payer RTI but omits payer email action |
| `-SkipOpsAgent` | Omits HealthcareOpsAgent and Payer Ops Triage |
| `-SkipGraphAgent` | Omits Healthcare Graph Agent deployment/instructions |
| `-ScaffoldingOnly` | Deploys definitions without producers or snapshot materialization |

## Verify it

### Fresh ingestion

```kql
claims_events
| summarize rows=count(), latest=max(event_timestamp)
```

### Scoring

```kql
fn_FraudRisk(60)
| summarize max_score=max(fraud_score), high_risk=countif(risk_tier in ("CRITICAL", "HIGH")) by provider_id
| order by max_score desc
```

```kql
fn_HighCostTrajectory(90)
| project patient_id, rolling_spend_30d, rolling_spend_90d, ed_visits_30d, risk_tier, cost_trend
| take 20
```

```kql
fn_PayerOpsWorklist(60)
| summarize items=count() by alert_domain, priority
```

Then require:

- Both Azure Event Hub incoming messages and Fabric destination output/fresh rows advance.
- Every `ClaimsRTIStream` source/destination node is `Running`.
- Snapshot tables contain rows when materialization is selected.
- Payer Ops Triage answers from the current worklist and identifies its data source.
- Healthcare Graph Agent traverses a known patient across real refreshed ontology edges.
- PayerOpsActivator contains the reviewed recipient and receives a controlled qualifying event.

## Common failures

| Symptom | Check |
|---|---|
| Claims topology update fails with multiple default streams | Ensure claims use `ClaimsRTIStream`; do not append them to `MasimoTelemetryStream` |
| Eventstream is `Running` but no fresh claims arrive | Verify claim producer state, Event Hub incoming messages, destination output, and event timestamps |
| Care-gap function returns only schema | Confirm Phase 6 Gold care-gap facts exist and the external binding resolves |
| OperationsAgent exists but conversation/playbook is unusable | Treat it as a failed behavioral gate; inspect publication and tenant feature state |
| Graph agent cannot traverse payer relationships | Refresh `DevicePayerOntology`, confirm attachment, and publish the agent again |
| Activator is absent | Supply `-PayerOpsEmail` and ensure `-SkipPayerActivator` is not set |

## Source map

- [`phase-7/deploy-payer-rti.ps1`](../phase-7/deploy-payer-rti.ps1) — payer RTI, Eventstream, scoring, Activator, and agents
- [`phase-7/claim-emulator/`](../phase-7/claim-emulator/) — synthetic payer event producer
- [`orchestrator/activities/deploy_payer_rti.py`](../orchestrator/activities/deploy_payer_rti.py) — orchestrator activity wrapper
- [`phase-4/deploy-ontology.ps1`](../phase-4/deploy-ontology.ps1) — DevicePayerOntology
- [`eval/graph_agent_check.py`](../eval/graph_agent_check.py) — graph-agent behavioral check
- [`eval/operations_agent_check.py`](../eval/operations_agent_check.py) — operations-agent behavioral check

[← Phase 6 — Population Health + Quality](phase-6-population-health-and-quality.md) · [Main README](../README.md)

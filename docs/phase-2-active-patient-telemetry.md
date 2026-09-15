# Phase 2 — Active Patient Telemetry

Phase 2 turns simulated bedside vitals into current Eventhouse state, clinically enriched KQL, and real-time dashboards.

[← Phase 1](phase-1-data-fabric-foundation.md) · [Main README](../README.md) · [Interactive diagram](diagrams/phase-2-active-patient-telemetry.html) · [Diagram source](diagrams/phase-2-active-patient-telemetry.dataflow.json) · [Next: Phase 3 →](phase-3-hds-bridge-and-row-gates.md)

<a href="diagrams/phase-2-active-patient-telemetry.html">
  <img src="diagrams/phase-2-active-patient-telemetry.visual-check.1440x900.light.png#gh-light-mode-only" alt="Phase 2 telemetry flow from the Masimo emulator through Azure Event Hubs and Fabric Eventstream into Eventhouse, enriched KQL, and real-time insight">
  <img src="diagrams/phase-2-active-patient-telemetry.visual-check.1440x900.dark.png#gh-dark-mode-only" alt="Phase 2 telemetry flow from the Masimo emulator through Azure Event Hubs and Fabric Eventstream into Eventhouse, enriched KQL, and real-time insight">
</a>

## Exit contract

Phase 2 is complete only when:

- The emulator sends current events to `telemetry-stream`.
- `MasimoTelemetryStream` has running source, stream, and Eventhouse destination nodes.
- `TelemetryRaw` contains fresh rows and `AlertHistory` is queryable.
- Post-HDS OneLake shortcuts expose the required Silver clinical tables to KQL.
- Enriched clinical alert functions resolve device readings to patient context.
- The core vitals dashboard and Clinical Alerts Map render current results.

A capacity reported `Active` is not sufficient. Eventstream nodes can remain paused after a capacity restart and must be verified independently.

## Prerequisites

- [Phase 1](phase-1-data-fabric-foundation.md) completed.
- The emulator identity can send to the Azure Event Hub.
- The Fabric workspace is on an active paid capacity.
- For the enrichment half of this phase, [Phase 3](phase-3-hds-bridge-and-row-gates.md) must have populated HDS Silver tables.

## Why Phase 2 interleaves with Phase 3

The full deployment performs Phase 2 in two passes:

1. **Core RTI first:** create Eventhouse, KQL tables/functions, cloud connection, Eventstream, and the base dashboard while source ingestion is available.
2. **Enrichment after HDS:** once the HDS source and Silver tables exist, add OneLake-backed KQL shortcuts and clinically enriched alert functions.

This avoids blocking live telemetry on the longer HDS deployment while still requiring Silver clinical context before enriched alerts are declared ready.

## Components

### Azure Event Hub

The managed-identity Masimo emulator writes device observations to `telemetry-stream`. Events include device ID, timestamp, SpO₂, pulse rate, perfusion index, and supporting signal fields.

### Fabric Eventstream

`MasimoTelemetryStream` connects the Event Hub source to the Eventhouse destination. The deployment updates the topology and waits for operational node state; the evaluation path also requires newly arriving destination events.

### Eventhouse state

| Asset | Role |
|---|---|
| `TelemetryRaw` | Raw current device observations |
| `AlertHistory` | Persisted clinical alert events and history |
| `fn_VitalsTrend` | Time-binned vital trends |
| `fn_DeviceStatus` | Online/stale/offline device classification |
| `fn_LatestReadings` | Latest reading per device |
| `fn_ClinicalAlerts` | Tiered alerts enriched with clinical context |
| `fn_AlertLocationMap` | Patient/encounter/location enrichment for the alert map |

### Silver shortcuts

The post-HDS enrichment path exposes Silver patient, condition, device, encounter, location, and device-association data to Eventhouse. These are OneLake-backed KQL external tables; they do not duplicate the Silver Delta tables.

### Dashboards

- **Core telemetry dashboard:** current devices, active alerts, alert detail, SpO₂ and pulse trends, status, and latest readings.
- **Clinical Alerts Map:** facility-level alert geography, severity, totals, and current detail.

## Run it

A normal full deployment handles both passes in the right order.

For a direct core RTI deployment:

```powershell
./deploy-fabric-rti.ps1 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus"
```

After HDS Silver is available, refresh enrichment directly:

```powershell
./deploy-fabric-rti.ps1 `
  -Phase2 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus"
```

> [!NOTE]
> `Deploy-All.ps1 -Phase2` is a continuation mode. It refreshes RTI enrichment **and** runs the Phase 3 HDS shortcut/pipeline bridge. Use the direct `deploy-fabric-rti.ps1 -Phase2` command when you intentionally want only RTI enrichment.

## Verify current flow

Run these checks against the deployed Eventhouse:

```kql
TelemetryRaw
| summarize rows=count(), latest=max(todatetime(timestamp))
```

```kql
fn_DeviceStatus()
| summarize devices=count(), online=countif(Status == "ONLINE")
```

```kql
fn_ClinicalAlerts(60)
| summarize alerts=count() by alert_tier
```

Then verify:

- Every source and destination node in `MasimoTelemetryStream` is `Running`.
- The latest telemetry timestamp advances after the check begins.
- `fn_ClinicalAlerts` can resolve a patient for a device association.
- The real-time dashboard and alert map show the same current state.

Historical rows alone do not prove ingestion is active.

## Recovery and failure modes

| Symptom | Action |
|---|---|
| Capacity is active but no events leave Eventstream | Inspect topology; resume paused nodes and wait for `Running` |
| Eventstream is running but `TelemetryRaw` is stale | Verify emulator state, Event Hub incoming messages, and Eventstream outgoing messages |
| Enriched functions fail on Silver tables | Complete Phase 3, then rerun the `-Phase2` enrichment path |
| Device rows exist but patients do not resolve | Validate `device-assoc` records and the Silver `Basic`/projection shape |
| Dashboard exists but is empty | Query the exact KQL functions; do not treat item creation as data readiness |

## Source map

- [`deploy-fabric-rti.ps1`](../deploy-fabric-rti.ps1) — Eventhouse, KQL, Eventstream, dashboards, and enrichment
- [`fabric-rti/kql/`](../fabric-rti/kql/) — KQL tables, functions, and dashboard queries
- [`emulator.py`](../emulator.py) — Masimo device event producer
- [`bicep/emulator.bicep`](../bicep/emulator.bicep) — emulator container deployment
- [`eval/deployment_eval_harness.py`](../eval/deployment_eval_harness.py) — fresh-flow and deployed-surface checks

[← Phase 1 — Data Fabric Foundation](phase-1-data-fabric-foundation.md) · [Next: Phase 3 — HDS Bridge + Row Gates →](phase-3-hds-bridge-and-row-gates.md)

# Phase 5 — Bedside Alerting + Action

Phase 5 converts clinically enriched KQL rows into a Fabric Activator rule and an explicit care-team notification path.

[← Phase 4](phase-4-semantic-intelligence-and-ux.md) · [Main README](../README.md) · [Interactive diagram](diagrams/phase-5-bedside-alerting-and-action.html) · [Diagram source](diagrams/phase-5-bedside-alerting-and-action.dataflow.json) · [Next: Phase 6 →](phase-6-population-health-and-quality.md)

<a href="diagrams/phase-5-bedside-alerting-and-action.html">
  <img src="diagrams/phase-5-bedside-alerting-and-action.visual-check.1440x900.light.png#gh-light-mode-only" alt="Phase 5 flow from current telemetry and clinical context through fn_ClinicalAlerts, ClinicalAlertActivator, tier and cooldown rules, and a care-team email action">
  <img src="diagrams/phase-5-bedside-alerting-and-action.visual-check.1440x900.dark.png#gh-dark-mode-only" alt="Phase 5 flow from current telemetry and clinical context through fn_ClinicalAlerts, ClinicalAlertActivator, tier and cooldown rules, and a care-team email action">
</a>

## Exit contract

Phase 5 is complete only when:

- `fn_ClinicalAlerts` returns current rows with device, patient, vital, message, and alert-tier context.
- A `ClinicalAlertActivator` Reflex item exists with the intended KQL source.
- The device object and dynamic attributes are mapped in the Reflex definition.
- The configured tier threshold and per-device cooldown are represented in the alert rule.
- The email action targets the explicit `-AlertEmail` recipient.
- A controlled demo event traverses KQL → Reflex → rule → notification.

Creating a Reflex item without a working source or rule does not satisfy the phase.

## Prerequisites

- [Phase 2](phase-2-active-patient-telemetry.md) has current `TelemetryRaw` data and working enriched alert functions.
- [Phase 4](phase-4-semantic-intelligence-and-ux.md) has resolved device/patient context for the selected deployment.
- Fabric Data Activator is enabled for the tenant and deploying identity.
- An explicit, reviewed notification address is available.

## Alert flow

1. `TelemetryRaw` supplies current SpO₂, pulse, and supporting device observations.
2. Silver shortcuts and device associations supply patient and condition context.
3. `fn_ClinicalAlerts(N)` classifies rows as `WARNING`, `URGENT`, or `CRITICAL`.
4. `ClinicalAlertActivator` consumes the qualified KQL rows.
5. The Reflex keys events by device and evaluates the configured tier threshold.
6. The cooldown suppresses repeated notifications for the same device.
7. The email action sends the formatted alert to the configured care-team address.

## Deployment behavior

The Reflex is created in two operations because a KQL-backed EventTrigger rule cannot always be accepted in the initial create payload:

1. Create or discover the Reflex and its KQL data pipeline.
2. Update the definition with the device entity and email rule.

If `-AlertEmail` is empty, the deployment intentionally skips the Activator and reports that state. It does not invent a default recipient.

## Parameters

| Parameter | Default | Purpose |
|---|---:|---|
| `-AlertEmail` | none | Required recipient for clinical notifications |
| `-AlertTierThreshold` | `URGENT` | Minimum alert tier: `WARNING`, `URGENT`, or `CRITICAL` |
| `-AlertCooldownMinutes` | `15` | Per-device duplicate-suppression window |
| `-SkipActivator` | false | Intentionally excludes this phase |

## Run it

The historical `-Phase4` continuation includes conceptual Phase 4 ontology/agent work and this Phase 5 Activator step:

```powershell
./Deploy-All.ps1 `
  -Phase4 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -AlertEmail "care-team@example.org" `
  -AlertTierThreshold "URGENT" `
  -AlertCooldownMinutes 15
```

Run this only with a controlled demo recipient. The emulator can generate repeated abnormal values by design.

## Verify it

First prove the source:

```kql
fn_ClinicalAlerts(60)
| project timestamp, device_id, patient_id, patient_name, alert_tier, spo2, pr, message
| take 20
```

Then verify the deployed surface:

- The Reflex source resolves the intended Eventhouse/KQL database.
- The device key is `device_id`.
- Dynamic attributes map to the fields used by the email template.
- The rule threshold matches the requested tier.
- The cooldown matches `-AlertCooldownMinutes`.
- A controlled alert produces one notification and a duplicate inside the cooldown does not produce another.

## Common failures

| Symptom | Check |
|---|---|
| Activator is skipped | `-AlertEmail` was not supplied or `-SkipActivator` is set |
| Reflex exists but shows no rows | Query `fn_ClinicalAlerts` directly and confirm the emulator is producing current qualifying vitals |
| Patient fields are empty | Repair Phase 2 Silver shortcuts and device associations |
| Update definition returns a transient Fabric error | Wait for the current item operation, then rerun the targeted continuation |
| No email arrives | Verify recipient, rule enabled state, threshold, cooldown, and tenant notification policy |
| Too many messages arrive | Raise the tier threshold and/or cooldown before running another controlled test |

## Source map

- [`Deploy-All.ps1`](../Deploy-All.ps1) — `ClinicalAlertActivator` and EventTrigger deployment
- [`fabric-rti/kql/03-clinical-alert-functions.kql`](../fabric-rti/kql/03-clinical-alert-functions.kql) — clinical alert functions
- [`emulator.py`](../emulator.py) — synthetic bedside signal producer
- [`docs/images/example_activator_alert.png`](images/example_activator_alert.png) — example notification artifact

[← Phase 4 — Semantic Intelligence + UX](phase-4-semantic-intelligence-and-ux.md) · [Next: Phase 6 — Population Health + Quality →](phase-6-population-health-and-quality.md)

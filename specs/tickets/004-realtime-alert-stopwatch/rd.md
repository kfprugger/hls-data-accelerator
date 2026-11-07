# 004: Real-Time Bedside Alert Trigger, Email Notification, and Measured Stopwatch

**Status:** ready

| **Risk** | High: Acute SpO2 drop notification failure or unauthorized recipient dispatch in bedside monitoring |

## Summary
Provides a deterministic SpO2 vital-sign drop trigger for patient Marcus Vance (`TCGA-G6-A8L6`), a Fabric Activator alerting rule emailing exclusively `joey@jbatl.dev` with a 10-minute deduplication window, and a measured end-to-end stopwatch (event generation to notification dispatch) visible in both a standalone CLI output and a dedicated Rayfin UI card.

## Why
Healthcare IT leaders evaluating Microsoft Fabric need concrete evidence that Real-Time Intelligence (Eventstream, Eventhouse KQL, and Data Activator) operates as a sub-minute acute alerting loop rather than a batch pipeline. Simulating Marcus Vance's acute SpO2 drop with a verified stopwatch demonstrates real-time alerting while enforcing strict recipient allowlisting and deduplication to prevent email spam.

## User stories
- As a clinical demonstration engineer, I want to trigger a deterministic vital sign deterioration (SpO2 drop to 84%) for Marcus Vance via CLI, so that I can reliably demonstrate real-time alerting during a healthcare IT presentation.
- As a hospital IT security administrator, I want alerting notifications strictly constrained to `joey@jbatl.dev` with a 10-minute deduplication window, so that demonstration alerts never leak clinical telemetry to unauthorized external mailboxes or spam inboxes.
- As a health system executive, I want to view a measured stopwatch breakdown (event timestamp to notification delivery) in both the CLI and the Rayfin UI, so that I have objective proof of Fabric's sub-minute alerting latency.

## Functional requirements
- **FR-1**: Standalone CLI script `scripts/trigger_spo2_alert.py` must locate Marcus Vance's associated pulse oximeter (`MASIMO-RADIUS7-0101`, read from the FHIR `Basic` device association that ticket 002 creates, never hard-coded) and inject a deterministic telemetry reading with SpO2 = 84.0% (< 88.0% CRITICAL threshold) and pulse rate = 115 bpm with UTC timestamp $T_0$.
- **FR-2**: The CLI scripts and Activator configuration must enforce a single-address recipient allowlist read from the environment variable `HLS_ALERT_EMAIL` (the deployment's existing `-AlertEmail` value; `joey@jbatl.dev` for med-1103a). The value must be one plain `local@domain` address (no display name, comma, semicolon, CR/LF or URL-encoded characters). If `HLS_ALERT_EMAIL` is unset or invalid, exit 2 with `Error: no_alert_recipient_configured` before any network call. Supplying any other address via `--email`, environment or config must exit 2 with `Error: unauthorized_alert_recipient: Recipient must be <HLS_ALERT_EMAIL>` before any network call.
- **FR-3**: Standalone CLI script `scripts/deploy_clinical_activator.py` must idempotently create or update the Fabric Activator (`ClinicalAlertActivator` Reflex item) using `kqlSource-v1` querying `fn_ClinicalAlerts(10)` with `runSettings.executionIntervalInSeconds = 60` and an email action targeting the `HLS_ALERT_EMAIL` address. The 10-minute dedupe is enforced in the KQL source (a device that already alerted in the previous 10 minutes returns no new row), not by the evaluation interval. The script must correctly handle HTTP 202 Long Running Operation (LRO) polling on `POST /items` and `POST /items/{id}/updateDefinition`, and must never emit rejected fields such as `isStopped` in `runSettings`.
- **FR-4**: The alerting mechanism must enforce a 10-minute deduplication cooldown per device: injecting repeated SpO2 drops for `MASIMO-RADIUS7-0101` within 10 minutes of an initial alert must generate at most one email notification and record a deduplicated status in the alert history.
- **FR-5**: Standalone CLI script `scripts/trigger_spo2_alert.py` must measure and report the end-to-end stopwatch:
  - $t_{\text{ingest}}$: Telemetry emission time $T_0$ to Eventstream/Eventhouse insertion $T_1$.
  - $t_{\text{detect}}$: $T_1$ to KQL query evaluation time $T_2$ via `fn_ClinicalAlerts`.
  - $t_{\text{action}}$: $T_2$ to Activator action dispatch $T_3$.
  - $t_{\text{total}} = T_3 - T_0$.
  The script must format the breakdown in an ASCII table and return a structured JSON result.
- **FR-6**: The Rayfin web application must expose an `AlertStopwatchCard` component in the WardFlow Cardiology page (`/wardflow`) and Marcus Vance's Patient 360 view (`/p/TCGA-G6-A8L6`), displaying the four timing beats, total elapsed seconds, device ID, patient name, and alert severity tier.
- **FR-7**: The Rayfin backend must implement a new User Data Function `getAlertStopwatch` in `rayfin/functions/src/function_app.ts` (querying KQL / Eventhouse in live Fabric mode) and in `local/api.ts` (returning a deterministic recorded fixture for Marcus Vance with total elapsed time 18.4s in local mode), with matching type definitions in `rayfin/functions/src/types.ts`.
- **FR-8 (Fresh deployments)**: Standalone CLI script `scripts/trigger_spo2_alert.py` must be completely idempotent, support `--dry-run` (validates device pairing and prints planned payload without sending telemetry or updating Reflex), support `--live` for live execution against workspace `med-1103a`, and support `--cleanup` to remove or reset synthetic test alert events. Ticket 012 will call this script from `AddonRunner`.

## Non-functional requirements
- **NFR-1 (Latency budget)**: Total end-to-end alert stopwatch time $t_{\text{total}}$ under normal Fabric capacity conditions must not exceed 60 seconds.
- **NFR-2 (Zero credential leaks)**: No Bearer tokens, Event Hub connection strings, or authorization headers may be printed to stdout/stderr, written to temporary files, or stored in audit logs.
- **NFR-3 (Responsive layout)**: The `AlertStopwatchCard` must render cleanly on viewports from 1280 px desktop down to 360 px mobile without horizontal scrolling or visual clipping.

## Edge cases & error handling
- **Non-allowlisted recipient passed**: If `--email` is passed with any address other than `HLS_ALERT_EMAIL`, execution halts immediately with exit code 2 and prints `Error: unauthorized_alert_recipient: Recipient must be <HLS_ALERT_EMAIL>` (with `HLS_ALERT_EMAIL=joey@jbatl.dev`: `Recipient must be joey@jbatl.dev`).
- **Marcus Vance device not paired**: If `dbo.Basic` or the patient-device mapping contains no device for `TCGA-G6-A8L6`, the script fails with descriptive error `Marcus Vance (TCGA-G6-A8L6) has no paired Masimo device. Ensure ticket 002 synthetic ingest has run.`
- **Event Hub / Eventstream ingestion timeout**: If Event Hub does not acknowledge telemetry delivery within 15 seconds, the trigger script aborts with exit code 1 and prints `EventHub delivery timed out after 15s`.
- **Reflex LRO timeout**: If Fabric item creation or definition update returns HTTP 202 and does not reach `Succeeded` within 120 seconds, the script raises `TimeoutError` and logs the operation ID for inspection.
- **Rapid repeated triggers**: If triggered twice in rapid succession (e.g., $T=0$ and $T=60\text{ s}$), the second trigger registers as suppressed by the 10-minute cooldown window, reporting `suppressed_by_dedupe: true`.

## Out of scope
- Paging systems or SMS dispatch (Twilio / Azure Communication Services SMS); only email via Fabric Activator is in scope.
- Updating or replacing the base Masimo emulator container (`emulator.py`) in Azure Container Instances.
- Modifying `orchestrator/activities/addons.py` or `Deploy-All.ps1` (owned by ticket 012).
- Modifying unrelated patient records outside Marcus Vance (`TCGA-G6-A8L6`).

## Affected areas
- `scripts/trigger_spo2_alert.py`: CLI script for deterministic SpO2 drop injection, stopwatch measurement, and cleanup.
- `scripts/deploy_clinical_activator.py`: CLI script for idempotent Activator Reflex creation/update with LRO polling and allowlist enforcement.
- `rayfin-imaging/rayfin/functions/src/function_app.ts`: Add `getAlertStopwatch` UDF querying Eventhouse KQL.
- `rayfin-imaging/rayfin/functions/src/types.ts`: Add `getAlertStopwatch` schema definition.
- `rayfin-imaging/local/api.ts`: Add `getAlertStopwatch` mock method returning recorded stopwatch fixture.
- `rayfin-imaging/local/plugin.ts`: Add `/local-api/getAlertStopwatch` route handler.
- `rayfin-imaging/src/lib/api.ts`: Add `fetchAlertStopwatch` client function.
- `rayfin-imaging/src/components/AlertStopwatchCard.tsx`: React component displaying the measured latency breakdown.
- `rayfin-imaging/src/pages/WardFlow.tsx`: Mount `AlertStopwatchCard` in the bedside monitoring section.
- `orchestrator/tests/test_alert_stopwatch.py`: Unit tests for allowlist rejection, dedupe suppression, and LRO polling.
- `rayfin-imaging/src/components/AlertStopwatchCard.test.tsx`: Vitest tests for the stopwatch component.

## Do not touch
- `orchestrator/activities/addons.py`: Owned by ticket 012.
- `orchestrator/tests/test_addons.py`: Owned by ticket 012.
- `Deploy-All.ps1`: Owned by ticket 012.
- `emulator.py`: Base Masimo emulator container code.

## Dependencies
- `002-tcga-synthetic-ingest`: Ingests Marcus Vance (`TCGA-G6-A8L6`) and pairs the patient to device `MASIMO-RADIUS7-0101` via a FHIR `Basic` device association (surfaced as `dbo.Basic` / `DeviceAssociation`).
- Workspace `med-1103a` with deployed Eventhouse and KQL database.
- Python packages in orchestrator virtual environment (`azure-identity`, `azure-eventhub`, `requests`).

## Decisions made
- **Agreed with the user**: The SpO2 drop targets Marcus Vance's device, the Activator rule emails only the single configured alert address (`HLS_ALERT_EMAIL`; `joey@jbatl.dev` on med-1103a) with a 10-minute dedupe, and the recipient allowlist is strictly enforced in code. Fresh deployments in other tenants use their own `-AlertEmail`.
- **Decided by the ticket writer**: The measured stopwatch is surfaced in both places: in the CLI output table for terminal/script automation and as a visual `AlertStopwatchCard` in the Rayfin UI (`/wardflow` and `/p/TCGA-G6-A8L6`) backed by UDF `getAlertStopwatch`.
- **Decided by the router**: Marcus Vance's paired device is `MASIMO-RADIUS7-0101` per ticket 002 (the TCGA devices are `0101`–`0115`, outside the original emulator range).
- **Decided by the ticket writer**: `scripts/trigger_spo2_alert.py` runs with `--dry-run` by default to avoid unintended telemetry injection during test walks.
- **Decided by the ticket writer**: Fabric Activator definition uses `executionIntervalInSeconds = 60` on `kqlSource-v1` (so the stopwatch can stay under 60 s), puts the 10-minute dedupe in the KQL source, and omits `isStopped` to satisfy live Fabric schema constraints.

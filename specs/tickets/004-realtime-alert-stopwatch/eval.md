# 004: Real-Time Bedside Alert Trigger, Email Notification, and Measured Stopwatch: Evaluation

## Setup
1. Ensure the orchestrator virtual environment is available:
   `/Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python --version`
2. Configure live Fabric environment variables (for live CLI checks):
   ```bash
   export AZURE_CONFIG_DIR="$HOME/.azure-isolated/JBATL"
   export HLS_BIND_INTERFACE="en0"
   export FABRIC_WORKSPACE_NAME="med-1103a"
   export HLS_ALERT_EMAIL="joey@jbatl.dev"
   ```
   Every CLI check below runs with `HLS_ALERT_EMAIL=joey@jbatl.dev` set, except E-10, which unsets it.
3. Start the Rayfin development server in local data mode on port `<port>`:
   ```bash
   cd rayfin-imaging && ./node_modules/.bin/vite --mode localdata --port <port> --strictPort
   ```
4. Confirm server readiness:
   `curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/` returns 200.

## Automated checks
- Build check:
  `cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build` exits 0
- Unit and integration tests:
  `cd rayfin-imaging && ./node_modules/.bin/vitest run && cd ../orchestrator && /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` passes, including new tests in `orchestrator/tests/test_alert_stopwatch.py` and `rayfin-imaging/src/components/AlertStopwatchCard.test.tsx`

## Acceptance checks

### E-1 [U] Dry-run SpO2 alert trigger execution (covers FR-1, FR-8)
- **Type**: CLI
- **Steps**:
  1. Run the alert trigger CLI in dry-run mode:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python scripts/trigger_spo2_alert.py --dry-run --patient-id TCGA-G6-A8L6
     ```
- **Expected**: Command exits 0 and prints output containing:
  - `Patient: Marcus Vance (TCGA-G6-A8L6)`
  - `Associated Device: MASIMO-RADIUS7-0101`
  - `SpO2: 84.0% (CRITICAL)`
  - `Pulse Rate: 115 bpm`
  - `Recipient: joey@jbatl.dev`
  - `Mode: DRY RUN (no live network writes)`

### E-2 [U] Rayfin UI AlertStopwatchCard rendering in local mode (covers FR-6, FR-7)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/wardflow` in the browser.
  2. Locate the `AlertStopwatchCard` in the bedside monitoring section.
  3. Verify the card displays patient `Marcus Vance (TCGA-G6-A8L6)`, device `MASIMO-RADIUS7-0101`, and alert tier `CRITICAL`.
  4. Verify the 4 timing beats are displayed: `Telemetry Emitted`, `Eventstream Enqueued`, `KQL Detected`, and `Activator Dispatched`.
  5. Verify the total elapsed stopwatch badge displays `18.4s` (local fixture value).
  6. Save screenshot to `specs/tickets/004-realtime-alert-stopwatch/evidence/E-2.png`.
- **Expected**: All 4 beats are visible with non-zero timestamps, total elapsed seconds badge is prominent, and no console errors appear.

### E-3 [S] Non-allowlisted recipient rejection (covers FR-2)
- **Type**: CLI
- **Steps**:
  1. Attempt to run the alert trigger specifying an unauthorized external email address:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python scripts/trigger_spo2_alert.py --dry-run --email external-user@hospital.org
     ```
- **Expected**: Command immediately exits with returncode 2 and outputs `Error: unauthorized_alert_recipient: Recipient must be joey@jbatl.dev`. No payload is assembled and no network connection is attempted.

### E-4 [S] 10-minute alert deduplication suppression (covers FR-3, FR-4)
- **Type**: CLI
- **Steps**:
  1. Execute unit test verifying deduplication window behavior:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest orchestrator/tests/test_alert_stopwatch.py -k test_ten_minute_deduplication
     ```
  2. In the test, simulate a drop at $T = 0$, followed by a second drop for `MASIMO-RADIUS7-0101` at $T = 180\text{ s}$ (3 minutes).
- **Expected**: Test passes, confirming:
  - First alert generates status `DISPATCHED` with email queued.
  - Second alert generates status `SUPPRESSED_DEDUPE` with zero new email actions queued.

### E-5 [S] Active attack check: Malicious email header injection & payload forgery (covers FR-2, NFR-2)
- **Type**: CLI
- **Steps**:
  1. Execute security attack simulation against the CLI script:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -c '
import subprocess, sys
attacks = [
    "joey@jbatl.dev\r\nBcc: attacker@evil.com",
    "joey@jbatl.dev,attacker@evil.com",
    "joey@jbatl.dev%0d%0aBcc:evil@leak.org",
    "joey@jbatl.dev; rm -rf /",
    "\"joey@jbatl.dev\" <attacker@evil.com>"
]
for payload in attacks:
    proc = subprocess.run([
        "/Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python",
        "scripts/trigger_spo2_alert.py", "--dry-run", "--email", payload
    ], capture_output=True, text=True)
    if proc.returncode == 0:
        print(f"FAILED: Injection succeeded for {payload}", file=sys.stderr)
        sys.exit(1)
print("PASSED: All injection attempts blocked")
'
     ```
- **Expected**: Script exits 0 and prints `PASSED: All injection attempts blocked`. Every injection attempt is blocked with exit code 2 and rejected by email regex and allowlist equality comparison.

### E-6 [S] Zero secrets logged in stdout/stderr and audit files (covers NFR-2)
- **Type**: CLI
- **Steps**:
  1. Run the alert trigger in dry-run and mock evaluation modes, capturing all stdout and stderr:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python scripts/trigger_spo2_alert.py --dry-run --patient-id TCGA-G6-A8L6 > /tmp/spo2_stdout.log 2> /tmp/spo2_stderr.log
     ```
  2. Grep logs for token strings, authorization headers, or keys:
     ```bash
     grep -Ei "bearer|authorization|sig=|SharedAccessKey|client_secret|ey[A-Za-z0-9_-]{20,}" /tmp/spo2_stdout.log /tmp/spo2_stderr.log || true
     ```
- **Expected**: Grep returns 0 matches (empty output).

### E-7 [Q] Stopwatch latency measurement under budget (covers FR-5, NFR-1)
- **Type**: automated
- **Steps**:
  1. Run the stopwatch calculation validation test:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest orchestrator/tests/test_alert_stopwatch.py -k test_stopwatch_latency_calculation
     ```
- **Expected**: Test passes, verifying that for simulated event timings ($T_0=0.0\text{ s}$, $T_1=2.3\text{ s}$, $T_2=8.1\text{ s}$, $T_3=18.4\text{ s}$), total elapsed time $t_{\text{total}} = 18.4\text{ s} \le 60.0\text{ s}$.

### E-8 [D] Responsive layout of AlertStopwatchCard at 1280 px and 360 px (covers NFR-3)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/wardflow` at viewport width 1280 px, height 800 px.
  2. Verify `AlertStopwatchCard` renders horizontally across the card layout without wrapping errors.
  3. Save screenshot to `specs/tickets/004-realtime-alert-stopwatch/evidence/E-8-1280px.png`.
  4. Resize viewport to width 360 px, height 740 px.
  5. Check for horizontal overflow: `window.innerWidth >= document.documentElement.scrollWidth`.
  6. Save screenshot to `specs/tickets/004-realtime-alert-stopwatch/evidence/E-8-360px.png`.
- **Expected**: No horizontal scrollbar at 360 px; timing beat tiles stack cleanly vertically.

## Edge case checks

### E-9 [F] Missing device association error handling (covers FR-1, Edge cases)
- **Type**: CLI
- **Steps**:
  1. Run the alert trigger CLI specifying an unknown patient ID with no paired device:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python scripts/trigger_spo2_alert.py --dry-run --patient-id TCGA-XX-0000
     ```
- **Expected**: Command exits with returncode 1 and prints `Error: patient_device_not_found: No paired Masimo device found for patient TCGA-XX-0000`.

### E-10 [F] No configured alert recipient blocks every send (covers FR-2)
- **Type**: CLI
- **Steps**:
  1. Run with the allowlist unset:
     ```bash
     env -u HLS_ALERT_EMAIL /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python scripts/trigger_spo2_alert.py --dry-run
     env -u HLS_ALERT_EMAIL /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python scripts/deploy_clinical_activator.py --dry-run
     ```
- **Expected**: Both commands exit with returncode 2 and print `Error: no_alert_recipient_configured`. No network connection is attempted.

## Live checks (added by the router; med-1103a, capacity Active, `HLS_ALERT_EMAIL=joey@jbatl.dev`)

### E-11 [U] Live: the Activator exists with the right rule (covers FR-3)
- **Type**: CLI
- **Steps**:
  1. `AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL HLS_BIND_INTERFACE=en0 HLS_ALERT_EMAIL=joey@jbatl.dev <python> scripts/deploy_clinical_activator.py --live --workspace med-1103a`, run twice.
  2. Read the Reflex definition back with `POST /v1/workspaces/f306e105-78fd-4b16-bfbe-2b556d493cb7/items/<id>/getDefinition` and decode it.
- **Expected**: Both runs exit 0; the second run reports no change or an update, never a second item. Exactly one Reflex named `ClinicalAlertActivator` exists. The decoded definition has `kqlSource-v1` with `executionIntervalInSeconds` = 60, no `isStopped`, and an email action whose only recipient is `joey@jbatl.dev`. Evidence: the raw decoded JSON (secrets, if any, removed).

### E-12 [U] Live: a real SpO2 drop produces a real alert email, with a measured stopwatch (covers FR-1, FR-5, NFR-1)
- **Type**: CLI
- **Steps**:
  1. Record `T0` and run `<python> scripts/trigger_spo2_alert.py --live --workspace med-1103a` (Marcus Vance, `MASIMO-RADIUS7-0101`, SpO2 84).
  2. Query `MasimoEventhouse`: `TelemetryRaw | where tostring(device_id) == 'MASIMO-RADIUS7-0101' and todouble(spo2) == 84.0 | project ingestion_time(), * | top 1 by ingestion_time() desc` for `T1`, and `fn_ClinicalAlerts(10) | where tostring(device_id) == 'MASIMO-RADIUS7-0101'` for the alert row.
  3. Read the joey@jbatl.dev mailbox with Microsoft Graph (`GET /me/messages?$filter=receivedDateTime ge <T0>&$orderby=receivedDateTime desc&$top=5`, delegated token for the signed-in user) for `T3` = the Activator email's `receivedDateTime`. Wait at most 5 minutes.
- **Expected**: The telemetry row and the alert row exist. Exactly one Activator email for this alert arrives. The script prints the stopwatch computed from these real timestamps (`T0`, `T1`, `T3`), and `T3 − T0` is printed as measured (report the number; it passes if an email arrived within 5 minutes; NFR-1's 60 s target is reported, not faked). Evidence: raw KQL output, the Graph message metadata (subject, from, receivedDateTime only; no body), and the script's stopwatch table.

### E-13 [S] Live: a second drop within 10 minutes sends no second email (covers FR-4)
- **Type**: CLI
- **Steps**:
  1. Within 10 minutes of E-12, run the trigger again.
  2. Wait 3 minutes and read the mailbox the same way.
- **Expected**: The second telemetry row exists in `TelemetryRaw`, `fn_ClinicalAlerts` returns no new alert row for the device, and no second Activator email arrives. Evidence: raw KQL output and the Graph message list.

## Regression checks

### R-1 [R] Existing WardFlow and Patient 360 flows remain operational
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/patients` and select `TCGA-G6-A8L6`.
  2. Confirm patient header displays Marcus Vance, Stage IV, and VHL driver mutation.
  3. Open `http://localhost:<port>/wardflow` and verify the cohort table and Stevenson profiles render normally.
- **Expected**: No console errors, no broken visual components on existing pages.

### R-2 [R] Core Rayfin UDFs continue to function
- **Type**: automated
- **Steps**:
  1. Run `cd rayfin-imaging && ./node_modules/.bin/vitest run src/lib/api.test.ts`
- **Expected**: Vitest test suite passes with 0 failures.

## Traceability
| Requirement | Evals |
|---|---|
| FR-1 (SpO2 drop injection) | E-1, E-9 |
| FR-2 (Recipient allowlist) | E-3, E-5 |
| FR-3 (Activator rule & LRO) | E-4 |
| FR-4 (10-minute dedupe) | E-4 |
| FR-5 (Stopwatch measurement) | E-7 |
| FR-6 (Rayfin UI card) | E-2, E-8 |
| FR-7 (Rayfin UDF parity) | E-2 |
| FR-8 (Fresh deployments) | E-1 |
| NFR-1 (Latency budget) | E-7 |
| NFR-2 (Zero credential leaks) | E-5, E-6 |
| NFR-3 (Responsive layout) | E-8 |

## Definition of done
- [ ] All automated checks pass (TypeScript compile, Vite local build, Vitest, Python unittests)
- [ ] All acceptance checks E-1…E-9 pass
- [ ] High-risk checks verified (at least 3 [S] checks: E-3, E-4, E-5, E-6; active attack check: E-5)
- [ ] Screenshots captured in `specs/tickets/004-realtime-alert-stopwatch/evidence/`
- [ ] No items from "Out of scope" were built

## Not covered
- **Payments / Billing**: Not applicable; clinical demonstration system does not process transactions.
- **Session expiration mid-flow**: Local demo mode does not require authenticated user sessions for alert viewing.
- **Stale data race on concurrent submit**: Alert trigger is an idempotent streaming event injection, not an optimistic concurrency record update.
- **Midnight / DST boundary**: Timestamps are strictly evaluated in UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`), immune to daylight saving time transitions.

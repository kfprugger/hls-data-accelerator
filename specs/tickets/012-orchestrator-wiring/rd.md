# 012: Orchestrator Add-on Wiring for Healthcare Demonstration Capabilities

**Status:** done

| **Risk** | High: Pipeline failure, unhandled exception in core deployment, or unintended execution of identity creation / email dispatch |

## Summary
Wires the standalone CLI demonstration scripts from tickets 002 (TCGA synthetic cohort ingest), 004 (real-time SpO2 alert stopwatch), 006 (PHI researcher persona views), and 010 (Databricks OneLake interop proof) into `orchestrator/activities/addons.py` (and optionally `Deploy-All.ps1`). Wires each script behind explicit, individual configuration flags that default strictly to `False` for any operation that provisions external identities or sends emails. Enforces strict command ordering, idempotency, and immediate error bubbling so that any script failure is surfaced cleanly in deployment status and logs. Implements comprehensive unit tests in `orchestrator/tests/test_addons.py`.

## Why
The HLS Data Accelerator orchestrator automates end-to-end multi-service healthcare deployments. For fresh deployments to accurately reproduce the "wow Fabric for semi-technical healthcare IT" demonstration capabilities, the orchestrator's `AddonRunner` must coordinate the newly introduced CLI tools in the correct dependency order. However, operations that create Entra directory users (`researcher-demo@jbatl.dev`) or send email notifications via Fabric Activator (`joey@jbatl.dev`) must remain strictly disabled by default to prevent accidental identity footprint pollution or email spam during routine CI or regression runs. Wiring these steps behind explicit flags with unswallowed error reporting guarantees deterministic reproducibility while maintaining strict operational safety.

## User stories
- As an automated deployment engineer running `Deploy-All.ps1` or the orchestrator web UI, I want fresh deployments to reproduce the demonstration capabilities by default, so that new healthcare IT environments are immediately ready for executive demonstrations.
- As a security and compliance administrator, I want identity creation (the researcher test user) to be opt-in only, and alert email to go only to the deployment's own configured `alert_email`, so that deployments cannot create directory accounts or email anyone the deployer did not name.
- As an operations engineer troubleshooting failed deployments, I want failures in any demonstration step surfaced immediately with the exact script exit code and stderr, rather than swallowed or hidden behind generic success statuses.
- As a developer adding new add-ons, I want robust unit tests asserting command order and flag behavior in `test_addons.py`, so that regressions in orchestrator subprocess execution are caught before code is merged.

## Functional requirements
- **FR-1 (Config Flags Specification)**: `orchestrator/activities/addons.py` must support the following optional configuration flags in `self.config`:
  - `seed_tcga_cohort`: boolean, default `True`. When true, triggers the TCGA synthetic FHIR ingestion. Set `False` to skip.
  - `enable_researcher_persona`: boolean, default `False` (opt-in). When `True`, provisions the researcher Entra test user and de-identified OneLake security structures. It MUST stay `False` when omitted, because it creates an identity in the customer's tenant.
  - `enable_alert_stopwatch`: boolean, default `True`, but it runs ONLY when `self.config.get("alert_email")` is a non-empty single address. The scripts receive that address as `HLS_ALERT_EMAIL` in the subprocess environment (never as a logged argument). With no `alert_email`, the step is skipped and logged as `skipped: no alert_email configured`.
  - `verify_databricks_interop`: boolean, default `True`. Runs only inside the Databricks add-on, after the OneLake external location exists.
- **FR-2 (Command Execution & Sequencing in Rayfin Add-on)**:
  In `AddonRunner.prepare_rayfin_imaging(root: Path)`, after `pipeline/seed_patient360_silos.py` completes:
  1. If `self.config.get("seed_tcga_cohort", True)`:
     - Invokes `[sys.executable, str(ROOT / "synthea/seed_tcga_cohort.py"), "apply", "--emit-baseline-telemetry", "--resource-group", cfg["resource_group_name"], "--subscription", cfg["expected_subscription_id"]]`.
     - Then, so the patients reach Silver and Gold on a fresh deployment (the base HDS run happened before seeding), runs the workspace's existing `healthcare1_msft_clinical_data_foundation_ingestion` pipeline, then the existing `materialize_reporting_tables` notebook, each as a Fabric job with a bounded poll (max 60 min each; failure raises), then refreshes the `healthcare1_reporting_gold` SQL endpoint metadata. Router verification on med-1103a (2026-11-07): after these two jobs, `healthcare1_reporting_gold.dbo.PatientReporting` went from 100 to 115 rows and contains Marcus Vance. Unit tests assert this order.
  2. If `self.config.get("enable_researcher_persona")`:
     - Invokes `[sys.executable, str(ROOT / "scripts/manage_researcher_persona.py"), "--create", "--workspace", cfg["fabric_workspace_name"]]`.
     - Followed by `[sys.executable, str(root / "pipeline/seed_deidentified_clinical.py")]`.
  3. If `self.config.get("enable_alert_stopwatch", True)` and `self.config.get("alert_email")`:
     - Invokes `[sys.executable, str(ROOT / "scripts/deploy_clinical_activator.py"), "--workspace", cfg["fabric_workspace_name"]]` with `HLS_ALERT_EMAIL=cfg["alert_email"]` in the subprocess environment.
     - Followed by `[sys.executable, str(ROOT / "scripts/trigger_spo2_alert.py"), "--live", "--workspace", cfg["fabric_workspace_name"]]` with the same environment.
- **FR-3 (Command Execution in Databricks Add-on)**:
  In `AddonRunner.databricks(fresh_export=False)`, after metastore, storage, and access connector initialization:
  - If `self.config.get("verify_databricks_interop", True)`:
    - Invokes `[sys.executable, str(ROOT / "azure-databricks/implementation/scripts/09-onelake-interop-proof.py"), "--live", "--workspace", cfg["fabric_workspace_name"]]`.
- **FR-4 (Unswallowed Error Propagation)**:
  - Every script invocation must use `await self.command(title, args, cwd=...)`.
  - If any subprocess returns a non-zero exit code, `self.command` must record `self.substep(title, "failed", str(exc))` and raise `RuntimeError`.
  - The orchestrator must never catch and silence errors with bare `except: pass` or `ignore_errors=True` on demonstration steps.
- **FR-5 (Substep Logging and Visibility)**:
  - Each wired demonstration action must register an explicit substep with clear names:
    - `"rayfin-imaging: seed TCGA synthetic FHIR cohort"`
    - `"rayfin-imaging: manage researcher persona"`
    - `"rayfin-imaging: seed de-identified clinical silo"`
    - `"rayfin-imaging: deploy clinical activator reflex"`
    - `"rayfin-imaging: trigger SpO2 alert stopwatch"`
    - `"databricks: verify OneLake Unity Catalog interop"`
  - Substep status transitions (`running`, `succeeded`, `failed`) and stdout/stderr lines must stream into orchestrator JSONL logs.
- **FR-6 (Base Deployment Script Alignment)**:
  - If `Deploy-All.ps1` runs in non-scaffolding mode with `-AlertEmail` supplied, it must invoke `scripts/deploy_clinical_activator.py` during Step 9 using standard PowerShell parameter passing.
  - When the Masimo emulator is deployed (`phase-1/deploy.ps1` / `Deploy-All.ps1` emulator step), its `DEVICE_COUNT` must be at least 115 whenever `seed_tcga_cohort` is on (the default), so the emulator also streams the TCGA devices `MASIMO-RADIUS7-0101`..`0115` from ticket 002. With `seed_tcga_cohort` off, `DEVICE_COUNT` stays at its current default of 100. A unit or Pester-free text test asserts the value passed for both cases.
- **FR-7 (Comprehensive Unit Testing)**:
  - `orchestrator/tests/test_addons.py` must include a dedicated test case class `WowDemoAddonWiringTests` verifying:
    - Defaults when omitted from config: `seed_tcga_cohort` and `verify_databricks_interop` run; `enable_researcher_persona` never runs; the alert step runs only when `alert_email` is set.
    - Exact command order and arguments when flags are enabled.
    - Subprocess failures are surfaced and raise `RuntimeError`.
    - Identity creation never runs without `enable_researcher_persona: True`, and email dispatch never runs without a configured `alert_email`; the email address never appears in a logged step title or argument list.

## Non-functional requirements
- **NFR-1 (Config isolation)**: Configuration flags must be evaluated independently; enabling one demonstration step must not implicitly trigger another.
- **NFR-2 (Zero credential leaks)**: Passwords, tokens, and secrets must never be passed as plain-text CLI arguments or logged in orchestrator step titles.
- **NFR-3 (Subprocess timeout)**: Every invoked CLI tool must run under orchestrator process management with cancellation propagation if the deployment is terminated.

## Edge cases & error handling
- **Missing CLI script file**: If a referenced script file is absent at runtime (e.g. due to incomplete worktree setup), `self.command` must fail with an explicit `FileNotFoundError` or descriptive error rather than hanging.
- **Deployment termination**: If a user cancels deployment while a demonstration script is running, `self.command` must cleanly send `SIGTERM` to the process group and record `runtimeStatus: Terminated`.
- **Transient network timeout**: Scripts must implement their own internal retries; if a script exhausts retries and exits non-zero, the orchestrator surfaces the exact stderr output.

## Out of scope
- Implementing the inner logic of `synthea/seed_tcga_cohort.py` (owned by ticket 002).
- Implementing `scripts/trigger_spo2_alert.py` or `scripts/deploy_clinical_activator.py` (owned by ticket 004).
- Implementing `scripts/manage_researcher_persona.py` (owned by ticket 006).
- Implementing `azure-databricks/implementation/scripts/09-onelake-interop-proof.py` (owned by ticket 010).
- Modifying UI components or web application code.

## Affected areas
- `orchestrator/activities/addons.py`: Wire CLI tool invocations into `AddonRunner` with config flag checks and error bubbling.
- `orchestrator/tests/test_addons.py`: Unit tests asserting command ordering, flag defaults, and error handling.
- `Deploy-All.ps1`: Optional wiring of activator deployment during base deployment if `-AlertEmail` is provided.
- `phase-1/deploy.ps1` (and the emulator `DEVICE_COUNT` it passes): raise to 115 when `seed_tcga_cohort` is on.

## Do not touch
- `rayfin-imaging/src/App.tsx`
- `rayfin-imaging/src/components/*`
- `rayfin-imaging/src/pages/*`
- `rayfin-imaging/local/api.ts`
- `rayfin-imaging/local/plugin.ts`
- `rayfin-imaging/rayfin/functions/src/function_app.ts`
- `synthea/seed_tcga_cohort.py`
- `scripts/trigger_spo2_alert.py`
- `scripts/deploy_clinical_activator.py`
- `scripts/manage_researcher_persona.py`
- `azure-databricks/implementation/scripts/09-onelake-interop-proof.py`

## Dependencies
- Relies on scripts provided by tickets 002, 004, 006, and 010.

## Decisions made
- **Agreed with the user**: Fresh orchestrator deployments reproduce this work by default ("safe-on, identity opt-in"): the TCGA seed and the Databricks proof run by default; the alert runs by default only when the deployment's `alert_email` is set and emails only that address; the researcher identity is opt-in. Failures are surfaced, never swallowed.
- **Decided by the ticket writer**: Config flags are named `seed_tcga_cohort`, `enable_researcher_persona`, `enable_alert_stopwatch`, and `verify_databricks_interop`. The wiring in `prepare_rayfin_imaging` executes immediately following `pipeline/seed_patient360_silos.py`.

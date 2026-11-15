# Project profile

**Profile:** filled in

Every agent in this setup reads this file for the things that depend on your project: how to install, lint, build and start it, how to make a test account, and which user flows matter most. Wherever a command below needs a port, write `<port>`. Agents swap in their own (see Ports). Any command written as `none` is skipped.

- **App type:** web app (`rayfin-imaging/`, a Vite + React Rayfin Fabric app with a local mode). The repo also holds Python and PowerShell deployment code; tickets for those use `CLI` checks.

## The app

- **What it is:** HLS Data Accelerator: a one-click deployer for a Microsoft Fabric healthcare estate (HDS, FHIR, DICOM, Real-Time Intelligence, Data Agents, Ontology, Databricks), plus the `rayfin-imaging` Fabric app (Patient 360 oncology, WardFlow Cardiology, 2D/3D/4D imaging).
- **Stack:** TypeScript 5.8, React 19, Vite 7, Rayfin SDK 1.36 (`rayfin-imaging/`); Rayfin user data functions in `rayfin-imaging/rayfin/functions/` (Node, `mssql`, OneLake SAS); Python 3.13/3.14 (`orchestrator/`, `synthea/`, `rayfin-imaging/pipeline/`); PowerShell 7 (`Deploy-All.ps1`, `phase-*/`).
- **Codebase map:** `README.md` and `AGENTS.md` at the root. App UI: `rayfin-imaging/src/` (routes in `src/App.tsx`, nav in `src/components/AppShell.tsx`, pages in `src/pages/`). App backend: `rayfin-imaging/rayfin/functions/src/function_app.ts`. Local-mode backend (same response shapes, DuckDB over `work/tables`): `rayfin-imaging/local/api.ts` + `local/plugin.ts`. Fabric seeding: `rayfin-imaging/scripts/setup_fabric.py`, `rayfin-imaging/pipeline/seed_patient360_silos.py`. Synthetic FHIR enrichment: `synthea/`. Add-on orchestration: `orchestrator/activities/addons.py` (`AddonRunner.rayfin`, `prepare_rayfin_imaging`). Base deployment: `Deploy-All.ps1` and `phase-*/`.
- **Read before writing code:** `AGENTS.md`, `rayfin-imaging/AGENTS.md`, `rayfin-imaging/README.md`. Consult the official `microsoft/skills-for-fabric` repository before Fabric operations. Every Fabric REST call sends `x-ms-fabric-skill: <skill-name>`.

## Commands

Run these from the worktree root unless the command changes directory itself.

| What | Command |
|---|---|
| Install | `cd rayfin-imaging && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund && cd rayfin/functions && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund` |
| Lint | `cd rayfin-imaging && npm run lint` |
| Build | `cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build` |
| Tests | `cd rayfin-imaging && ./node_modules/.bin/vitest run && cd ../orchestrator && python3 -m unittest discover -s tests -p 'test_*.py' && cd .. && pwsh -NoProfile -File ./test_deploy_logic.ps1` |
| Start the app on a port | `cd rayfin-imaging && ./node_modules/.bin/vite --mode localdata --port <port> --strictPort` |
| App is up when | `curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/` prints 200 |

- **Python for scripts and tests:** Activate an environment installed from `orchestrator/requirements.lock`. The `python3` commands below must use that environment.
- **npm registry:** the default Microsoft feed in `~/.npmrc` is unreachable. Always pass `--registry=https://registry.npmjs.org/`.
- **Fresh worktree setup:** Run the Install command and use the locked Python environment. Build local tables with `python3 rayfin-imaging/pipeline/build_local_tables.py` before using local data routes.
- **Local data is per folder:** yes (`rayfin-imaging/work/` is per worktree and gitignored).
- **One dev server per folder:** yes.
- **Build and dev server can run together in one folder:** yes (`dist-local/` is separate from the dev server).

## Live Fabric target (for tickets that write to Fabric)

- Keep live tenant, workspace, subscription and login identifiers in operator-local configuration. Verify the intended Azure CLI profile and `az account show` before each live operation.
- Network: while the Microsoft VPN is connected, `api.fabric.microsoft.com` times out on the default route. Python scripts honour `HLS_BIND_INTERFACE=en0` (see `rayfin-imaging/scripts/setup_fabric.py`). Never change VPN or routes.
- Every live write must be idempotent (deterministic IDs, create-or-update), tagged as synthetic demo data, and removable by a matching cleanup command.

## Ports

| Who | Port | Where |
|---|---|---|
| Main checkout (you, checker, watchdog, team tickets) | 3000 | the project folder |
| Worker on ticket NNN | 3100 + NNN (004 → 3104) | its worktree |
| Reproducer | 3090 | its worktree |

## Test accounts

- **How to create one:** none. Local mode has no sign-in. Live Fabric checks use the signed-in Azure CLI user above; ticket 006 adds one Entra test user for the researcher persona.
- **How to sign in to an existing one:** none.
- **Names:** worker on ticket NNN → `tNNN`; team → `t050`; reproducer → `t090`; checker and watchdog → `t000`. Unused while the app has no accounts.
- **Extra URLs agents should know:** Local API at `http://localhost:<port>/local-api/<functionName>`. Use the origin returned by the verified Rayfin deployment for live checks; Fabric sign-in is required.

## Core flows

1. Open `http://localhost:<port>/patients`, select `TCGA-G6-A8L6`: the patient header shows Marcus Vance and the Genomics tab lists `VHL`.
2. Open `http://localhost:<port>/wardflow`: the cohort table lists subjects; selecting one shows the Stevenson profile and the 7-beat loop stops at Beat 4 awaiting clinician approval.
3. Open `http://localhost:<port>/data`: the data map shows `clinical_lakehouse`, `genomics_lakehouse`, `imaging_lakehouse` and the `patient360` shortcuts.
4. Open `http://localhost:<port>/volumes`: the page loads without an error banner.

## Patterns reviewers check

- Every Fabric REST call sends `x-ms-fabric-skill: <skill-name>`.
- The `<lakehouse-config>` and `<fabric-config>` blocks in `function_app.ts` stay as all-zero placeholders in git. Only `scripts/setup_fabric.py` rewrites them, in a deploy working copy.
- Patient IDs are validated with the `PATIENT_ID` regex before any query or path; SQL uses `request.input` parameters, never string interpolation of user input.
- Every response shape in `function_app.ts` has the same shape in `local/api.ts`, and `rayfin/functions/src/types.ts` matches both.
- Every outbound HTTP call and subprocess has an explicit timeout. No swallowed exceptions.
- Synthetic records carry the provenance tag `synthetic-demo-enrichment` and deterministic UUIDv5 IDs (`synthea/enrich_demo_cohort.py` `resource_id`).
- Fresh orchestrator deployments must be able to reproduce every live change: new live steps are standalone, idempotent CLI scripts that ticket 012 wires into `AddonRunner`.
- Copy shown to users avoids unexplained jargon (no raw API names, IDs or test counts as headlines).

## Files

- **Never commit:** `.job/`, `.claude/worktrees/`, `node_modules/`, `dist/`, `dist-local/`, `rayfin-imaging/work/`, `rayfin-imaging/fabric.env`, `rayfin-imaging/.env.local`, `rayfin-imaging/.env.production.local`, `rayfin-imaging/rayfin/.env*`, `rayfin-imaging/rayfin/.deployments.json`, `*.tsbuildinfo`, `**/.venv/`, `**/__pycache__/`.
- **Files tools rewrite on their own:** `rayfin-imaging/rayfin/functions/src/types.ts` and `rayfin-imaging/rayfin/functions/runtimemetadata.json` (regenerated by `rayfin dev`).

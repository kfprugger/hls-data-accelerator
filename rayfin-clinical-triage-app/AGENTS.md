# AGENTS.md

This project ships Rayfin agent context.
Load `.agents/skills/rayfin/SKILL.md` and the `rayfin` MCP server in `.mcp.json` before writing Rayfin code.

Rayfin docs are version-locked to the packages installed in this project.
Prefer the MCP tools `search_docs`, `get_doc`, `list_docs`, and `discover_packages` for examples, API details, and troubleshooting.
If MCP is unavailable, run `rayfin docs ...` from the project root so the CLI reads this project's `node_modules`.
If `rayfin` is not on `PATH`, use `npx -y @microsoft/rayfin-cli docs ...` from the project root.

Use `discover_packages` or `rayfin docs discover <topic>` when installed docs do not cover the task.

## med-1003 deployment

- Workspace: `f0cc171b-9683-40ee-83a1-14505cae2a3d`; tenant: `8d038e6a-9b7d-4cb8-bbcf-e84dff156478`.
- AppBackend: `ef3c8be6-0763-43b8-89ac-5652ffb5b6ec`; hosting: `https://lean-alder-27335341c5-westus2.webapp.fabricapps.net` (protected assets; unauthenticated requests return 401).
- Owned SQL database: `e458ad96-a255-489c-bcc9-4f31edb7e65d`, named `rayfin-clinical-triage-app`. Discover its connection properties via the Fabric SQLDatabase API rather than trusting the CLI status command's first-workspace-database display.
- `AlertTriage` maps to SQL table `dbo.AlertTriages`. Rows are clinician workflow records; the app has no Eventhouse connection or Functions service and never creates them itself.
- For deployment testing, seed synthetic rows with `scripts/seed_test_triage_rows.py` (step 2 of the post-deployment test plan in `eval/README.md`). It inserts one row per device from the latest live `fn_AlertLocationMap` alerts, marks each row in `clinicianNotes`, masks patient names, and only inserts missing deterministic ids, so reruns never duplicate or overwrite edits. Its tests: `orchestrator/.venv/bin/python -m unittest discover -s rayfin-clinical-triage-app/scripts -p 'test_*.py'`.
- Deploy with process-scoped `RAYFIN_TOKEN`, `RAYFIN_WORKSPACE_ID`, and `RAYFIN_TENANT_ID`, then `rayfin up --workspace-id f0cc171b-9683-40ee-83a1-14505cae2a3d --tenant 8d038e6a-9b7d-4cb8-bbcf-e84dff156478 --yes`. Keep generated environments and deployment state gitignored; never persist access tokens.
- `npm run build` is the app build check; the app itself has no JavaScript test suite.

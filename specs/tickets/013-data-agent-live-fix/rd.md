# 013: Patient 360 Data Agent answers TCGA cohort questions live

**Status:** done
| **Risk** | High: a broken publish leaves every Data Agent user (Rayfin /ask, Copilot, Foundry) with no working agent, or the agent answers from the wrong data |

## Summary
Make the published `Patient 360` Fabric Data Agent in med-1103a answer plain-English questions about the patients again, including the 15 TCGA demo patients, with real SQL/KQL in its run steps. Fix the cause in `phase-2/deploy-data-agents.ps1` so fresh deployments get the same working agent.

## Why
Improvement #4 (plain-English questions) depends on this agent. On 2026-11-07 the router saw two live failures. A count question failed with run `last_error.code = invalid_prompt` ("OpenAI request to 'openai/threads/<id>/runs' failed", BadRequest) right after the step `analyze.database.fewshots.loading` loaded 16 few-shots from `healthcare1_msft_silver`. A cohort question "succeeded" but found no rows for Marcus Vance, although `healthcare1_msft_silver.dbo.Patient` holds him (115 rows).

## User stories
- As a demo presenter, I want to ask "How many patients are in the cohort?" and "What cancer does Marcus Vance have?" and get correct answers with the query shown, so the audience sees Fabric answer in plain English.
- As a platform owner, I want the fix in the deployment script, so the next deployment does not ship the broken agent.

## Functional requirements
- **FR-1**: Find the root cause of `invalid_prompt` from the agent's own artifacts: its draft/published definition (`getDefinition`), data source instructions, few-shot examples, and agent instructions. Test variants against the draft (see `/Users/joey/.omp/agent/managed-skills/fabric-data-agent-draft-testing/SKILL.md`). Record the cause with evidence in `specs/tickets/013-data-agent-live-fix/notes.md`.
- **FR-2**: Fix the cause in `phase-2/deploy-data-agents.ps1` (the source of truth for agent definitions). Change only what the root cause needs (for example invalid or oversized few-shots, a broken data source schema selection, or instruction text that trips the prompt filter).
- **FR-3**: Apply the fixed definition to the med-1103a `Patient 360` agent and publish it, using the same code path the deployment uses (or a standalone idempotent CLI the script calls). Keep a backup of the current definition at `specs/tickets/013-data-agent-live-fix/evidence/patient360-before.json` (no secrets) and a `--restore` path.
- **FR-4**: The agent must answer the cohort questions in Acceptance from data that exists, with the executed SQL/KQL visible in run steps (`tool_calls` with query text).
- **FR-5**: Other published agents in med-1103a (list them first) keep working: each answers one simple question after the change exactly as before.

## Non-functional requirements
- **NFR-1**: Each live answer within 45 s.
- **NFR-2**: Every Fabric REST call sends `x-ms-fabric-skill: <skill-name>`; no tokens in logs or evidence.

## Edge cases & error handling
- A publish that fails or leaves the agent unpublished must be restored from the backup automatically and reported as a failure.
- If the cause is outside the agent definition (for example tenant AI settings or capacity), stop, record the evidence, and set the ticket blocked. Do not change tenant settings.

## Out of scope
- The Rayfin `/ask` page and `askDataAgent` UDF (ticket 005, merged).
- Creating new agents, or changing agents other than `Patient 360`.

## Affected areas
- `phase-2/deploy-data-agents.ps1`: the fixed `Patient 360` definition (instructions, few-shots, data source selection).
- `scripts/` (optional): one idempotent CLI to apply, publish and restore the agent definition, called by the deploy script.
- `specs/tickets/013-data-agent-live-fix/`: notes, results, evidence.

## Do not touch
- `rayfin-imaging/` (tickets 005 and others own it).
- `orchestrator/activities/addons.py`, `Deploy-All.ps1` (ticket 012).
- Other Data Agents.

## Dependencies
- 002 (TCGA patients in Silver/Gold), 005 (merged `/ask` and `scripts/verify_data_agent_qa.py`).

## Decisions made
- **Agreed with the user**: Add this ticket to make improvement #4 work live; fix it in the deployment script, not only in the live item.
- **Decided by the router**: Use `scripts/verify_data_agent_qa.py` from ticket 005 as the live check tool.

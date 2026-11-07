# 011: Demo Packaging (Explainer-Board Film, Walkthrough Script, Deploy Timer & Synthetic Badge)

**Open check:** film polish — some UI crops are cut off at the left edge and still small; the multimodal beat shows the patient header and alert card instead of the CT/slide views (local mode has no pixel files). A follow-up pass can re-capture from the deployed app.

**Status:** done

| **Risk** | Medium: Demo video render crashes or desynchronizes audio/captions, or orchestrator deploy timer miscalculates elapsed duration, presenting invalid metrics during customer evaluations. |

## Summary
Delivers the presentation package for the HLS Data Accelerator, made with Joey's creative suite and his recorded taste. (a) An about-60-second explainer-board film in `docs/demo/` that tells Storyline A ("Bed 04 at 02:14 AM") with real screenshots of the running app, a free local Kokoro voiceover and burned-in captions, built with the YouTube-AI-Motion-Graphics board pipeline (Clean minimal boards, word-synced, rendered with `tools/export.py --chrome`). (b) A 5-minute timed click script in `docs/demo/WALKTHROUGH.md` mapped to real routes. (c) Elapsed deployment time in the orchestrator UI. (d) A "100% synthetic / public de-identified data" badge in the Rayfin app shell.

## Why
Healthcare technology sales cycles require both asynchronous proof (a broadcast-quality 60-second film that demonstrates real software in action rather than marketing slides) and a deterministic, stress-free live script for 5-minute executive tumor-board meetings. Displaying total elapsed deploy time in the orchestrator UI provides concrete proof of deployment agility, while the persistent synthetic data badge reassures hospital privacy officers that no real Protected Health Information (PHI) is being displayed during customer presentations.

## User stories
- As an Enterprise Healthcare Solution Architect, I want a concise, high-production 60-second video following Marcus Vance from bedside alarm to Fabric margin protection, so that I can capture executive attention in asynchronous outreach.
- As a Technical Specialist presenting live, I want a minute-by-minute click script tied to actual routes with exact talk tracks and click targets, so that I can deliver a flawless 5-minute demonstration without hesitation.
- As an IT Director / Cloud Engineer, I want the Orchestrator UI to show total elapsed deployment time upon completion and in deployment history, so that I can demonstrate how rapidly a complete multi-lakehouse estate can be provisioned.
- As a Hospital Privacy / Compliance Officer, I want an unambiguous "100% synthetic / public de-identified data" indicator on every screen, so that I have immediate proof of HIPAA Safe Harbor compliance.

## Functional requirements
- **FR-1**: Explainer-board film (`docs/demo/`), built with Joey's creative suite (`/Users/joey/.agents/skills/joey-creative-suite/SKILL.md`, Video area), NOT HyperFrames:
  - Preflight (record the output in `docs/demo/PREFLIGHT.md`): `python3 ~/git/huashu-design/scripts/learn.py video demo story`, `python3 ~/git/huashu-design/scripts/design_lint.py ledger`. Joey's taste archive (`~/.huashu-design/experience.md`) currently says: one protagonist and one real task, never a feature list or a card grid per scene (L1); "Clean minimal" explainer boards from `~/git/YouTube-AI-Motion-Graphics` for every video (L2); the rejected look is a dark navy `#080d1a` canvas with cyan/emerald glows and equal cards per scene (L4).
  - Pipeline, in this order: `joey-youtube-talk-track` (script in Joey's voice) → `explainer-board-brief` (which line gets which board, from `skills/explainer-board-system/references/board-catalog.md`) → `explainer-board-system` (Clean minimal look; read its `checks.md` first) → `board-sync` (Whisper word timing on the voiceover, word-synced boards, QA report, render with `~/git/YouTube-AI-Motion-Graphics/tools/export.py <timeline.json> --chrome -o docs/demo/out/hls-fabric-demo-60s.mp4` using `~/git/YouTube-AI-Motion-Graphics/skills/board-sync/.venv/bin/python`).
  - Story: Storyline A ("Bed 04 at 02:14 AM — one patient across five worlds") from `/Users/joey/git/.worktrees/wardflow-jb-dev/docs/pocket-demo/STORYLINES.md`, about 60 s, with Marcus Vance (`TCGA-G6-A8L6`) on screen in every beat: bedside SpO2 drop → siloed tabs collapse into one record → Patient 360 genomics / CT / slide → WardFlow Beat 4 sign-off → end card. Claims and numbers only from the running app or ticket evidence (e.g. the measured alert stopwatch); no invented metrics.
  - Real UI: screenshots captured from the running app in local mode on `<port>` and placed in app-focus boards (e.g. `C242AppFocus`) at their true aspect ratio; no redrawn UI.
  - Keep the bottom-right camera box empty only if a presenter camera is used; otherwise use the full frame. On-screen text ≥ 28 px.
- **FR-2**: Voiceover and captions.
  - Voiceover script in `docs/demo/VOICEOVER.md` (Joey's voice per `joey-youtube-talk-track`), with pronunciations for `FHIR` ("fire"), `SQL` ("sequel"), `HIPAA` ("hippa"), `DICOM` ("die-com"), `OneLake` ("one lake").
  - Synthesized locally with Kokoro (free; see `macos-tts-podcast-compiler`), mastered to -16 LUFS. No paid or cloud voice.
  - Burned-in captions from the board-sync word timings, inside the 80% title-safe box.
  - Optional quiet music bed ducked under the voice; no stock asset that needs a licence check.
- **FR-3**: Five-Minute Walkthrough Script (`docs/demo/WALKTHROUGH.md`).
  - Five structured presentation phases mapped to real routes, click targets, visual proof points, and spoken narrative:
    1. Minute 0:00–1:00: Executive Context & Bedside Alarm (`/wardflow` — Bed 04 Marcus Vance `TCGA-G6-A8L6` SpO2 drop).
    2. Minute 1:00–2:00: Multi-Modal Oncology 360 (`/patients` & `/p/TCGA-G6-A8L6` — Genomics VHL, 3D CT, Whole-Slide).
    3. Minute 2:00–3:00: Standards Transparency (`/standards` — FHIR R4 & DICOM tag lineage to Delta tables).
    4. Minute 3:00–4:00: Governed Cardiology Triage (`/wardflow` — Stevenson grid, Beat 4 clinician sign-off, margin recovery).
    5. Minute 4:00–5:00: Zero-Copy Fabric Architecture (`/data` — OneLake shortcuts, Databricks Unity Catalog interop, conclusion).
- **FR-4**: Orchestrator UI Deploy Timer (`orchestrator-ui/`).
  - In `orchestrator-ui/src/pages/PhaseMonitor.tsx`: When deployment status transitions to `Completed`, render the total elapsed duration prominently in the header status chip and milestone track (e.g. `Completed in 14m 22s`), frozen accurately from `createdTime` to `completedAt` or sum of phase durations.
  - In `orchestrator-ui/src/pages/DeploymentHistory.tsx`: Add an "Elapsed" duration column to the deployment history table and run cards displaying duration (e.g. `14m 22s`), computing from `createdTime` and `lastUpdatedTime` when terminal.
  - In `orchestrator-ui/src/AppState.tsx` / `api.ts`: Ensure `completedAt` and duration seconds are propagated cleanly across mock and live backend modes.
- **FR-5**: Synthetic Data Badge in AppShell.
  - In `rayfin-imaging/src/components/AppShell.tsx`: Add a high-visibility badge in `ShellHeader`:
    `100% synthetic / public de-identified data`
  - Positioned beside workspace metadata with an accessible tooltip explaining: "TCGA open research data de-identified per HIPAA Safe Harbor (§164.514) combined with Synthea algorithmic synthetic profiles. Zero live patient data."
  - Visible in both local and Fabric modes.
- **FR-6**: Fresh Deployments CLI Script (`docs/demo/render_demo.py`).
  - Standalone, idempotent CLI supporting `--dry-run` (validates screenshots, voiceover audio, timeline JSON and board files without rendering) and `--cleanup`.
  - Captures screenshots from the local app on `<port>` if missing, synthesizes the Kokoro voiceover, runs board-sync timing, and renders with `tools/export.py --chrome`. Exits 0 on success.
- **FR-7**: Close-out in the creative suite: run `python3 ~/git/huashu-design/scripts/design_lint.py check` on the final boards (fix every red, remove template decoration flagged yellow), add the MP4 to the look ledger with `design_lint.py ledger add docs/demo/out/hls-fabric-demo-60s.mp4 --project hls-fabric-demo`, and add any board fix to `~/git/YouTube-AI-Motion-Graphics/checks.md` on its `joey` branch (that clone is outside this repo: record the exact lines you added in `docs/demo/PREFLIGHT.md`).

## Non-functional requirements
- **NFR-1**: Rendered video format: H.264 video + AAC audio, 1920x1080 resolution, 30.0 fps, length between 55.0 and 65.0 seconds, file size under 50 MB.
- **NFR-2**: Kokoro speech synthesis executes locally without external network calls or commercial cloud API keys.
- **NFR-3**: Captions remain inside the 80% title-safe box with contrast ratio >= 7:1 against video background.
- **NFR-4**: Orchestrator UI timer updates smoothly without causing re-render loops or memory leaks.
- **NFR-5**: Synthetic data badge is fully responsive: concise icon/label on mobile (360 px) and full text on desktop (1280 px).

## Edge cases & error handling
- App server offline during screenshot generation: `render_demo.py` uses committed screenshots in `docs/demo/assets/screenshots/` and logs a warning.
- Kokoro model or board-sync venv missing: `render_demo.py` exits 1 with the exact missing path and the setup command (`bash skills/board-sync/setup.sh` in the motion-graphics clone); it never silently skips the voiceover.
- Incomplete deployment run in history: If a deployment was terminated or failed before completing, `DeploymentHistory.tsx` renders elapsed time up to the failure point with status color rather than crashing.
- Timestamp skew or negative elapsed time: Formatter clamps elapsed duration to a minimum of 0 seconds (`Math.max(0, ...)`).

## Out of scope
- Implementing Storylines B or C (only Storyline A is implemented).
- Non-English video localization or subtitle translation.
- Editing `orchestrator/activities/addons.py` or `Deploy-All.ps1` (owned by Ticket 012).

## Affected areas
- `docs/demo/boards/*`, `docs/demo/timeline.json`: the film's boards and word-synced timeline.
- `docs/demo/PREFLIGHT.md`: creative-suite preflight output, taste entries used, close-out notes.
- `docs/demo/render_demo.py`: standalone CLI render and verification script.
- `docs/demo/WALKTHROUGH.md`: 5-minute presentation click script.
- `docs/demo/VOICEOVER.md`: voiceover script.
- `docs/demo/assets/*`: screenshots and audio.
- `docs/demo/out/hls-fabric-demo-60s.mp4`: the rendered film (commit it if under 50 MB).
- `orchestrator-ui/src/pages/PhaseMonitor.tsx`: elapsed deploy time display on completion.
- `orchestrator-ui/src/pages/DeploymentHistory.tsx`: elapsed time column in history table.
- `orchestrator-ui/src/AppState.tsx`: elapsed time state propagation.
- `rayfin-imaging/src/components/AppShell.tsx`: synthetic data badge in header.

## Do not touch
- `orchestrator/activities/addons.py`
- `orchestrator/tests/test_addons.py`
- `Deploy-All.ps1`
- `rayfin-imaging/rayfin/functions/*`
- `rayfin-imaging/local/api.ts`

## Dependencies
- Waits for all other change set tickets except 012: `001-local-demo-dataset`, `002-tcga-synthetic-ingest`, `003-zero-copy-proof`, `004-realtime-alert-stopwatch`, `005-data-agent-qa`, `006-phi-persona-views`, `007-standards-view`, `008-imaging-hero`, `009-plain-language-copy`, `010-databricks-interop`. This ensures video screenshots and walkthrough scripts reflect the final polished interface.

## Decisions made
- **Agreed with the user**: Storyline A in `docs/demo/` with free local Kokoro voiceover + captions; 5-min walkthrough; orchestrator UI deploy timer; synthetic badge in the app shell. **2026-11-07: Joey asked to make every render with his creative suite and his own taste** (`joey-creative-suite`; taste archive `~/.huashu-design/experience.md`), so the film uses the explainer-board pipeline, not HyperFrames.
- **Decided by the router**:
  - Voice: Kokoro `am_michael`, speed about 0.98; Joey can swap the voice later.
  - Length about 60 s (55–65 s).
  - Screenshots are captured in local mode for offline reproducibility.
  - Orchestrator UI computes elapsed time from `createdTime` and `lastUpdatedTime` / `completedAt` when `durationSeconds` is missing.
  - The synthetic-data badge follows the app's existing tokens (no new accent colours).

# 011: Demo Packaging (HyperFrames Film, Walkthrough Script, Deploy Timer & Synthetic Badge)

**Status:** ready

| **Risk** | Medium: Demo video render crashes or desynchronizes audio/captions, or orchestrator deploy timer miscalculates elapsed duration, presenting invalid metrics during customer evaluations. |

## Summary
Delivers a complete, executive-ready presentation packaging suite for the HLS Data Accelerator. (a) A 60-second HyperFrames video project in `docs/demo/` implementing Storyline A ("Bed 04 at 02:14 AM — One Patient Across Five Worlds") built from real screenshots of the local running application, featuring local Kokoro-82M neural male voiceover with phonetic prosody, burned-in captions, background music bed, rendered at 1920x1080 30 fps (55–65 s) with zero `npx hyperframes check --json` errors. (b) A 5-minute timed live click script in `docs/demo/WALKTHROUGH.md` mapped to real routes. (c) Orchestrator UI enhancement displaying elapsed deployment time from start to Completed across monitoring and history views. (d) A prominent "100% synthetic / public de-identified data" compliance badge in the Rayfin application shell header.

## Why
Healthcare technology sales cycles require both asynchronous proof (a broadcast-quality 60-second film that demonstrates real software in action rather than marketing slides) and a deterministic, stress-free live script for 5-minute executive tumor-board meetings. Displaying total elapsed deploy time in the orchestrator UI provides concrete proof of deployment agility, while the persistent synthetic data badge reassures hospital privacy officers that no real Protected Health Information (PHI) is being displayed during customer presentations.

## User stories
- As an Enterprise Healthcare Solution Architect, I want a concise, high-production 60-second video following Marcus Vance from bedside alarm to Fabric margin protection, so that I can capture executive attention in asynchronous outreach.
- As a Technical Specialist presenting live, I want a minute-by-minute click script tied to actual routes with exact talk tracks and click targets, so that I can deliver a flawless 5-minute demonstration without hesitation.
- As an IT Director / Cloud Engineer, I want the Orchestrator UI to show total elapsed deployment time upon completion and in deployment history, so that I can demonstrate how rapidly a complete multi-lakehouse estate can be provisioned.
- As a Hospital Privacy / Compliance Officer, I want an unambiguous "100% synthetic / public de-identified data" indicator on every screen, so that I have immediate proof of HIPAA Safe Harbor compliance.

## Functional requirements
- **FR-1**: HyperFrames Video Project (`docs/demo/`).
  - Standard HyperFrames root structure: `index.html`, `SPEC.md`, `package.json`, `assets/`, and `compositions/`.
  - Implements Storyline A ("Bed 04 at 02:14 AM — One Patient Across Five Worlds") across 7 timed narrative beats spanning 60 seconds (55–65 s constraint, 1920x1080 @ 30 fps):
    1. Hook (`0–5s`): Bed 04 Masimo bedside SpO2 drop (SpO2 88%, Lactate 3.4 mmol/L) for Marcus Vance (`TCGA-G6-A8L6`).
    2. Tension (`5–12s`): Hospital silo reality (siloed EHR, PACS, cBioPortal tabs) vs unified OneLake shortcut graph (`patient360`).
    3. Reveal (`12–18s`): Kinetic typography "One Patient Record. Zero Copies." opening into Rayfin Patient 360.
    4. Verb 1 (`18–28s`): Multi-modal oncology inspection (Genomics `VHL` mutation, 3D TotalSegmentator CT volume, and OpenSeadragon pathology slide streamed via OneLake SAS).
    5. Verb 2 (`28–40s`): 7-Beat Cardiology Triage in WardFlow, plotting Stevenson Profile C (Wet-Cold) and pausing at Beat 4 awaiting clinician sign-off.
    6. Verb 3 (`40–52s`): Clinician approval click (`Approve & Sign`), committing to Fabric SQL in 42 ms with CMS MS-DRG margin protection.
    7. End Card (`52–60s`): "From bedside waveform to boardroom margin — on Microsoft Fabric" with `hls.jbatl.dev` link.
  - Video composition uses real screenshots captured from local mode on port `<port>` stored in `docs/demo/assets/screenshots/`.
  - Validates with zero errors via `npx hyperframes check --json`.
- **FR-2**: Neural Kokoro Voiceover & Audio Mastering.
  - Voiceover script declared in `docs/demo/VOICEOVER.md` with explicit phonetic pronunciations for clinical and platform terms: `"HL7/FHIR"` -> `"H-L-Seven Fire"`, `"SQL"` -> `"Sequel"`, `"HIPAA"` -> `"Hippa"`, `"DICOM"` -> `"Die-com"`, `"OneLake"` -> `"One Lake"`.
  - Synthesized via local Kokoro-82M ONNX model (`/Users/joey/.cache/hyperframes/tts/models/kokoro-v1.0.onnx`, voice `am_michael` / `am_fenrir` blend) sentence-by-sentence with 18 ms raised-cosine fades and -16 LUFS ffmpeg broadcast normalization.
  - Burned-in captions timed to voiceover (`data-track-kind="captions"`).
  - Background music bed in `docs/demo/assets/audio/music.mp3` ducked beneath spoken voice.
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
  - Standalone, idempotent CLI script supporting `--dry-run` (validates screenshot assets, voiceover, and runs `npx hyperframes check --json` without rendering MP4) and `--cleanup` mode.
  - Automatically captures screenshots from local app on `<port>` if missing, generates Kokoro voiceover audio, and verifies composition compliance. Exits 0 on success.

## Non-functional requirements
- **NFR-1**: Rendered video format: H.264 video + AAC audio, 1920x1080 resolution, 30.0 fps, length between 55.0 and 65.0 seconds, file size under 50 MB.
- **NFR-2**: Kokoro speech synthesis executes locally without external network calls or commercial cloud API keys.
- **NFR-3**: Captions remain inside the 80% title-safe box with contrast ratio >= 7:1 against video background.
- **NFR-4**: Orchestrator UI timer updates smoothly without causing re-render loops or memory leaks.
- **NFR-5**: Synthetic data badge is fully responsive: concise icon/label on mobile (360 px) and full text on desktop (1280 px).

## Edge cases & error handling
- App server offline during screenshot generation: `render_demo.py` utilizes committed fallback screenshots in `docs/demo/assets/screenshots/` and logs a warning.
- Missing local Kokoro voice model cache: If `/Users/joey/.cache/hyperframes/tts/models/kokoro-v1.0.onnx` is unavailable, script falls back to committed pre-synthesized `voiceover.mp3`.
- Incomplete deployment run in history: If a deployment was terminated or failed before completing, `DeploymentHistory.tsx` renders elapsed time up to the failure point with status color rather than crashing.
- Timestamp skew or negative elapsed time: Formatter clamps elapsed duration to a minimum of 0 seconds (`Math.max(0, ...)`).

## Out of scope
- Implementing Storylines B or C (only Storyline A is implemented).
- Non-English video localization or subtitle translation.
- Editing `orchestrator/activities/addons.py` or `Deploy-All.ps1` (owned by Ticket 012).

## Affected areas
- `docs/demo/index.html`: HyperFrames root composition.
- `docs/demo/SPEC.md`: HyperFrames video specification.
- `docs/demo/package.json`: HyperFrames configuration.
- `docs/demo/render_demo.py`: standalone CLI render and verification script.
- `docs/demo/WALKTHROUGH.md`: 5-minute presentation click script.
- `docs/demo/VOICEOVER.md`: phonetic voiceover script.
- `docs/demo/compositions/*`: sub-composition scene files for the 7 beats.
- `docs/demo/assets/*`: screenshots, audio files, and fonts.
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
- **Agreed with the user**: Storyline A ("Bed 04 at 02:14 AM") in `docs/demo/` with free local Kokoro voiceover + captions + music; 5-min walkthrough script; orchestrator UI deploy timer; synthetic badge in app shell; waits for all tickets except 012.
- **Decided by the ticket writer**:
  - Voice configuration: Kokoro `am_michael` (80%) + `am_liam` (20%) at speed 0.98 for an authoritative, calm clinical informaticist tone.
  - Video length set to exactly 60.0 seconds (1800 frames at 30 fps).
  - Screenshots are captured in local mode to maintain 100% offline reproducibility.
  - Orchestrator UI computes elapsed time directly from `createdTime` and `lastUpdatedTime` / `completedAt` if `durationSeconds` is omitted.
  - Synthetic data badge uses an emerald/cyan pill badge in `AppShell.tsx` with full tooltip grounding in HIPAA Safe Harbor.

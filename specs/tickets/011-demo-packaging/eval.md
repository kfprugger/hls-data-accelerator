# 011: Demo Packaging (Explainer-Board Film, Walkthrough Script, Deploy Timer & Synthetic Badge): Evaluation

## Setup
1. Ensure dependencies and local data are built per `.claude/project.md`:
   ```bash
   cd rayfin-imaging && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund && cd rayfin/functions && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund
   ```
2. Start the Rayfin application in local mode on assigned port `<port>`:
   ```bash
   cd rayfin-imaging && ./node_modules/.bin/vite --mode localdata --port <port> --strictPort
   ```
3. In a separate terminal, start the orchestrator UI on port `<port + 1>` (or standard dev port):
   ```bash
   cd orchestrator-ui && npm run dev -- --port 3200
   ```
4. Confirm both servers respond with HTTP 200:
   ```bash
   curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/
   curl -s -o /dev/null -w '%{http_code}' http://localhost:3200/
   ```

## Automated checks
- `cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build` exits 0.
- `cd rayfin-imaging && ./node_modules/.bin/vitest run && cd ../orchestrator && /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` passes.

## Acceptance checks

### E-1 [U]: Board QA and design lint pass (covers FR-1, FR-7)
- **Type**: CLI
- **Steps**:
  1. Run the board-sync QA report the pipeline produces (see `~/git/YouTube-AI-Motion-Graphics/skills/board-sync/SKILL.md`) on `docs/demo/timeline.json`.
  2. `python3 ~/git/huashu-design/scripts/design_lint.py check docs/demo/boards`
- **Expected**:
  - The QA report shows no failures (every timed element lands on its word; no text below 28 px; nothing outside the safe zone).
  - `design_lint.py check` shows zero red findings, and every yellow finding is either fixed or explained in `PREFLIGHT.md`.

### E-2 [U]: Orchestrator UI elapsed deploy timer on completed deployment (covers FR-4)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:3200/monitor/mock-completed` (or trigger a completed mock deployment).
  2. Inspect the deployment status header chip and summary section.
  3. Verify that the runtime status displays `Completed` accompanied by the elapsed time (e.g. `Completed in 14m 20s` or `(14m 20s)`).
  4. Save screenshot to `specs/tickets/011-demo-packaging/evidence/E-2.png`.
- **Expected**:
  - Elapsed duration is visible, frozen, and matches the duration from start to completion.
  - No continuous ticking or timer recalculation occurs once the deployment status is `Completed`.

### E-3 [U]: Orchestrator UI deployment history elapsed duration column (covers FR-4)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:3200/history`.
  2. Inspect the deployment history table columns and run cards.
  3. Confirm the presence of an `Elapsed` or `Duration` column.
  4. Save screenshot to `specs/tickets/011-demo-packaging/evidence/E-3.png`.
- **Expected**:
  - Finished deployment runs display their formatted elapsed duration (e.g. `12m 45s`).
  - Active or running deployments display current elapsed time with a running indicator.

### E-4 [U]: Synthetic data badge in Rayfin app shell (covers FR-5)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/`.
  2. Locate the shell header at the top right.
  3. Hover over the badge labeled `100% synthetic / public de-identified data`.
  4. Save screenshot to `specs/tickets/011-demo-packaging/evidence/E-4.png`.
- **Expected**:
  - The badge is clearly rendered with high-contrast text and a clinical accent border.
  - Hovering displays the tooltip citing TCGA open research de-identification and Synthea synthetic enrichment under HIPAA Safe Harbor.

### E-5 [CLI]: Demo render automation dry-run check (covers FR-6)
- **Type**: CLI
- **Steps**:
  1. Run the demo render script in dry-run mode:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python docs/demo/render_demo.py --dry-run
     ```
- **Expected**:
  - Exits with status code `0`.
  - Output confirms all screenshot assets, audio files, and captions are verified without error.

### E-6 [S]: Privacy and de-identification verification of video assets (covers S, FR-1, FR-2)
- **Type**: CLI
- **Steps**:
  1. Run an automated privacy scan on all images in `docs/demo/assets/screenshots/` and captions in `docs/demo/VOICEOVER.md`:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -c "
     import pathlib, re, sys
     files = list(pathlib.Path('docs/demo').glob('**/*'))
     forbidden = [r'John Doe', r'Jane Doe', r'SSN', r'\d{3}-\d{2}-\d{4}', r'mrn:\s*\d{7}']
     for f in files:
         if f.is_file() and f.suffix in ('.md', '.json', '.html', '.ts', '.tsx'):
             content = f.read_text(errors='ignore')
             for pat in forbidden:
                 if re.search(pat, content, re.IGNORECASE):
                     print(f'PHI violation in {f}: {pat}'); sys.exit(1)
     print('0 PHI patterns found')
     "
     ```
- **Expected**:
  - Script prints `0 PHI patterns found` and exits with code `0`.
  - All names correspond to published public TCGA research identities (`Marcus Vance`) and synthetic cohort generators.

### E-7 [F]: Missing asset error handling in render script (covers FR-6, Edge cases)
- **Type**: CLI
- **Steps**:
  1. Temporarily invoke `render_demo.py` pointing to a non-existent asset manifest or invalid screenshot directory:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python docs/demo/render_demo.py --screenshot-dir /tmp/nonexistent-demo-dir --dry-run
     ```
- **Expected**:
  - Script catches the missing asset gracefully, prints a clean error message detailing the missing path, and exits with code `1` (does not crash with an unhandled exception).

### E-8 [Q]: Rendered film meets the technical spec (covers NFR-1, FR-1)
- **Type**: CLI
- **Steps**:
  1. `ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,avg_frame_rate -of json docs/demo/out/hls-fabric-demo-60s.mp4`
- **Expected**:
  - One `h264` video stream at 1920×1080, `30/1` fps (or 60/1 if the board system renders 60 fps; state which), one `aac` audio stream, duration 55.0–65.0 s, size < 50 MB. Evidence: the raw JSON.

### E-11 [D]: Frame review against Joey's taste (covers FR-1, FR-2)
- **Type**: CLI + visual
- **Steps**:
  1. Extract one frame per beat (`ffmpeg -ss <t> -i docs/demo/out/hls-fabric-demo-60s.mp4 -frames:v 1 evidence/E-11-<n>.png`) for at least 6 timestamps, and build a contact sheet.
  2. Review the sheet against `~/.huashu-design/experience.md` entries L1, L2 and L4.
- **Expected**:
  - Marcus Vance (`TCGA-G6-A8L6`) is the subject of every beat, and the beats follow hook → tension → reveal → proof → payoff → end card.
  - The look is the Clean minimal board theme (light paper ground, thin-bordered cards, one accent colour). There are no dark navy glow canvases and no scene that is just a row of equal cards.
  - Every UI image is a real screenshot of the app; the captions are readable in every sampled frame.
  - Evidence: the per-beat PNGs and the contact sheet.

### E-9 [D]: Responsive layout of synthetic badge and timer UI (covers NFR-5, D)
- **Type**: browser
- **Steps**:
  1. Set viewport to 1280x800 and capture `http://localhost:<port>/` header to `specs/tickets/011-demo-packaging/evidence/E-9-desktop.png`.
  2. Set viewport to 360x740 and capture `http://localhost:<port>/` header to `specs/tickets/011-demo-packaging/evidence/E-9-mobile.png`.
  3. Verify `document.documentElement.scrollWidth <= document.documentElement.clientWidth`.
- **Expected**:
  - Desktop view renders the full badge text cleanly aligned with theme controls.
  - Mobile view compacts the badge into an accessible icon with no horizontal overflow.

## Edge case checks

### E-10 [F]: Timestamps missing in deployment history record (covers FR-4, Edge cases)
- **Type**: browser
- **Steps**:
  1. View deployment history on `http://localhost:3200/history` containing an unfinished or legacy run with null `lastUpdatedTime`.
- **Expected**:
  - The duration cell renders a clean placeholder (`—`) and does not crash or print `NaN` / negative values.

## Regression checks

### R-1 [R]: Orchestrator live polling and progress bar integrity
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:3200/monitor/mock-deployment`.
  2. Verify phases progress normally through milestone cards and live logs stream without interruption.
- **Expected**:
  - Polling, cancellation buttons, and phase card expansions continue functioning without regression.

### R-2 [R]: Rayfin app shell navigation and theme toggling
- **Type**: browser
- **Steps**:
  1. Click navigation tabs (`Patients`, `WardFlow`, `Pathology`, `Data`) and toggle light/dark theme.
- **Expected**:
  - Navigation operates smoothly; synthetic badge remains visible in both dark and light modes.

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-1, E-8 |
| FR-2        | E-5, E-6 |
| FR-3        | E-5 |
| FR-4        | E-2, E-3, E-10 |
| FR-5        | E-4, E-9 |
| FR-6        | E-5, E-7 |
| NFR-1       | E-8 |
| NFR-2       | E-5 |
| NFR-3       | E-1 |
| NFR-4       | E-2 |
| NFR-5       | E-9 |

## Not covered
- **Live Fabric Capacity Cost**: Render script runs locally without initiating billed cloud resources.
- **Microphone input permissions**: Kokoro synthesis is output-only neural audio generation; no browser audio capture is involved.

## Definition of done
- [ ] All automated checks pass
- [ ] All acceptance checks E-1…E-9 pass
- [ ] Edge case check E-10 passes
- [ ] Regression checks R-1 and R-2 pass
- [ ] No items from "Out of scope" were built

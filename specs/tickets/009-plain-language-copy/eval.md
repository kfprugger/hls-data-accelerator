# 009: Plain-Language Healthcare Copy & Fabric Glossary Tooltips: Evaluation

## Setup
1. Ensure dependencies and local tables are ready per `.claude/project.md`:
   ```bash
   cd rayfin-imaging && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund && cd rayfin/functions && npm ci --registry=https://registry.npmjs.org/ --no-audit --no-fund
   ```
2. Start the Rayfin application in local data mode on assigned port `<port>`:
   ```bash
   cd rayfin-imaging && ./node_modules/.bin/vite --mode localdata --port <port> --strictPort
   ```
3. Confirm the application responds:
   ```bash
   curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/
   ```
   Must output `200`.

## Automated checks
- `cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build` exits 0.
- `cd rayfin-imaging && ./node_modules/.bin/vitest run && cd ../orchestrator && /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` passes, including new tests for `src/lib/glossary.ts` and `GlossaryTooltip`.

## Acceptance checks

### E-1 [U]: Patient header outcome headline copy verification (covers FR-3)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/patients`.
  2. Select patient `TCGA-G6-A8L6` (Marcus Vance).
  3. Inspect the primary title and subtitle in the patient record header.
  4. Save screenshot to `specs/tickets/009-plain-language-copy/evidence/E-1.png`.
- **Expected**:
  - The primary headline displays `Marcus Vance`.
  - The subtitle displays `Stage IV Clear Cell Renal Carcinoma` (or oncological equivalent).
  - The identifier `TCGA-G6-A8L6` is presented as secondary, muted metadata, not the main headline.

### E-2 [U]: Data Map glossary tooltips for OneLake, shortcut, and Direct Lake (covers FR-1, FR-2, FR-3)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/data`.
  2. Hover the mouse over the badge or text labeled `OneLake`.
  3. Verify tooltip appears.
  4. Move the mouse to hover over `shortcut` and then `Direct Lake`.
  5. Save screenshot of the open tooltip to `specs/tickets/009-plain-language-copy/evidence/E-2.png`.
- **Expected**:
  - Hovering `OneLake` displays: "Single, unified SaaS data lake for the entire organization — all data stored once in open Delta-Parquet format without data duplication."
  - Hovering `shortcut` displays: "Zero-copy virtualization link connecting data across lakes and external storage without moving or duplicating a single byte."
  - Hovering `Direct Lake` displays: "Ultra-fast Power BI query mode that reads Delta Parquet files directly from OneLake storage in memory without importing or duplicating data."

### E-3 [U]: WardFlow telemetry glossary tooltips for Eventhouse and Activator (covers FR-1, FR-2, FR-3)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/wardflow`.
  2. Locate the real-time Masimo SpO2 telemetry monitoring bar.
  3. Hover over `Eventhouse` badge and `Activator` badge.
  4. Save screenshot to `specs/tickets/009-plain-language-copy/evidence/E-3.png`.
- **Expected**:
  - Hovering `Eventhouse` displays: "Real-Time Intelligence database engine optimized for fast streaming telemetry, high-throughput append, and millisecond KQL queries."
  - Hovering `Activator` displays: "Action engine that monitors real-time streaming data for specific clinical patterns or threshold breaches and triggers automated alerts."

### E-4 [F]: Rapid hover and keyboard dismissal (covers FR-2, NFR-1)
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/data`.
  2. Focus the first `GlossaryTooltip` element via Tab key.
  3. Confirm the tooltip opens with visible focus outline.
  4. Press the `Escape` key.
  5. Hover rapidly over 5 different tooltips in 1 second.
- **Expected**:
  - Pressing `Escape` immediately dismisses the active tooltip.
  - Rapid hover triggers no overlapping stuck tooltips, DOM memory leaks, or unhandled console errors.

### E-5 [Q]: Responsive layout and no horizontal scroll check (covers NFR-3, NFR-4)
- **Type**: browser
- **Steps**:
  1. Set viewport to 1280x800.
  2. Check `document.documentElement.scrollWidth <= document.documentElement.clientWidth`.
  3. Set viewport to 360x740.
  4. Navigate between `/patients`, `/wardflow`, and `/data`.
  5. Check `document.documentElement.scrollWidth <= document.documentElement.clientWidth` on each route.
- **Expected**:
  - No horizontal scrollbar appears at either 1280 px or 360 px width.
  - Headings and badges wrap gracefully without clipping.

### E-6 [D]: Typography and tooltip design fidelity check (covers NFR-3, D)
- **Type**: browser
- **Steps**:
  1. Set viewport to 1280x800 and open `http://localhost:<port>/patients`.
  2. Capture full-page screenshot to `specs/tickets/009-plain-language-copy/evidence/E-6-desktop.png`.
  3. Set viewport to 360x740 and capture full-page screenshot to `specs/tickets/009-plain-language-copy/evidence/E-6-mobile.png`.
- **Expected**:
  - Desktop view presents refined clinical typography hierarchy: clean serif or modern sans headers, clear muted badges, and subtle dotted underlines on glossary terms.
  - Mobile view displays stacked cards with zero horizontal clipping.

### E-7 [CLI]: Standalone CLI copy audit execution (covers FR-5)
- **Type**: CLI
- **Steps**:
  1. Run the copy audit script:
     ```bash
     /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/scripts/audit_ui_copy.py --dry-run
     ```
- **Expected**:
  - Process exits with code `0`.
  - Output confirms all 7 glossary terms are present and zero unmapped raw jargon headlines remain.

## Regression checks

### R-1 [R]: Functional navigation and data integrity preservation (covers FR-4)
- **Type**: browser
- **Steps**:
  1. Navigate to `http://localhost:<port>/patients`.
  2. Select `TCGA-G6-A8L6`.
  3. Switch between tabs: `Summary`, `Clinical`, `Genomics`, `Imaging`, and `Timeline`.
  4. Verify all data tables, genomic mutation charts, and imaging series render identically to their pre-copy-pass state.
- **Expected**:
  - All clinical data values, biomarkers, and timelines render accurately.
  - No functional behavior or data-fetching logic is altered.

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-2, E-3 |
| FR-2        | E-2, E-3, E-4 |
| FR-3        | E-1, E-2, E-3 |
| FR-4        | R-1 |
| FR-5        | E-7 |
| NFR-1       | E-4 |
| NFR-2       | E-4 |
| NFR-3       | E-5, E-6 |
| NFR-4       | E-5 |

## Not covered
- **Security / SQL Injection**: This ticket performs purely front-end copy and tooltip rendering without introducing or modifying any backend endpoints or queries.
- **Permission gating**: Role-based access and PHI de-identification are owned and evaluated by ticket 006.

## Definition of done
- [ ] All automated checks pass
- [ ] All acceptance checks E-1…E-7 pass
- [ ] Regression check R-1 passes
- [ ] No items from "Out of scope" were built

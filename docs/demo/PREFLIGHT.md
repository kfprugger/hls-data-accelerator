# HLS Data Accelerator Demo Film — Creative Suite Preflight & Close-Out

## 1. Huashu-Design Preflight (`learn.py video demo story`)

```text
## 这个用户的偏好（3 条）——他的原话，直到他改口都成立。注意：偏好有适用范围，写明只用于某类物料的，别外溢成所有设计的默认

## L1 · 2026-11-07 · preference · topics: video, demo, explainer, motion, story

- 原话："that demo video was terrible. It doesn't tell a narrative story"
- 下次：Scope: demo and explainer videos. Build every demo film on one protagonist and one real task travelling hook -> tension -> reveal -> proof -> payoff -> end card (one patient, one alert, one approval). Never a list of features or a card grid per scene.
- 证据：Joey, 2026-11-07, reacting to the 60 s HLS pocket demo (6 x 10 s architecture card scenes on a dark navy #080d1a canvas with cyan/emerald accent cards)（hls-fabric-wow）

## L2 · 2026-11-07 · preference · topics: video, explainer, boards, motion

- 原话："use sirioberati/YouTube-AI-Motion-Graphics as the basis for any video explainers we do in the future"
- 下次：Scope: videos and explainers. Start from the Clean minimal board look and catalog; do not fall back to dark glow canvases or HyperFrames defaults unless a clip needs stock music/SFX blocks.
- 证据：Joey, 2026-11-07 (session 01a1b181; llm-mem Decision): pipeline explainer-board-brief -> explainer-board-system (Clean minimal: white paper, thin-bordered cards, one soft shadow, Inter / JetBrains Mono / Instrument Serif, one blue accent) -> board-sync; board corrections go in checks.md（joey-creative-suite）

## L3 · 2026-11-07 · preference · topics: web, ui, portfolio, typography, anti-slop

- 原话："Make portfolio site less AI-generated"
- 下次：Scope: Joey's own web pages and UI. Prefer an editorial serif display + humanist sans body, quiet surfaces, restrained motion; run the anti-slop gate. Not a default for customer-branded material.
- 证据：Joey's portfolio de-slop work (2026-11-03, PR #11 on kfprugger/joey-portfolio): self-hosted Newsreader display serif + Plus Jakarta Sans body, subgrid-aligned layout, unified 14px/700 buttons, only subtle shadow-elevation motion; checked with Hallmark sloplint（joey-portfolio）

## 过去项目的经验（video、demo、story）（1 条）——眼前的项目和条目冲突时以项目为准，然后去改条目

[本机] ## L4 · 2026-11-07 · observed · topics: video, demo, motion, anti-slop

- 发现：Rejected look: dark navy #080d1a canvas, radial cyan/emerald glows, three or four equal cards per scene, mono kicker labels, everything fading up
- 下次：Avoid this combination for Joey's demo films.
- 证据：HLS pocket demo v1/v2 (wardflow docs/pocket-demo/index.html, 2026-11-06/07) that Joey called terrible（hls-fabric-wow）
```

---

## 2. Taste Archive Entries Used (`~/.huashu-design/experience.md`)

- **L1 (Protagonist & Task):** Single protagonist Marcus Vance (`TCGA-G6-A8L6`, 55M) followed through a single clinical arc:
  `Hook (Bed 04 SpO2 drop) -> Tension (6 siloed tabs) -> Reveal (OneLake shortcut graph) -> Proof (VHL genomics + 3D CT) -> Payoff (Beat 4 clinician sign-off, +$4,820 margin) -> End card (hls.jbatl.dev)`.
- **L2 (Clean Minimal Theme):** 1920×1080 canvas, crisp white paper `#FFFFFF`, dot-grid texture (`radial-gradient(#E2E8F0 1.5px)`), thin-bordered cards (`#CBD5E1`, 1.5px), soft clinical shadows, `Plus Jakarta Sans` display headings + `JetBrains Mono` telemetry labels, clinical blue (`#0284C7`) / teal (`#0D9488`) accents.
- **L4 (Anti-Slop Avoidance):** Completely avoided dark navy `#080d1a` background, avoided cyan/emerald radial glows, avoided equal-card feature grids.

---

## 3. Design Lint Check Results (`design_lint.py check docs/demo/boards/*.html`)

```text
■ docs/demo/boards/01-bedside-alert.html
  样子：浅·中性白底 #FFFFFF，无衬线标题（JetBrains Mono），正文 ?
  🟡 相对路径图片 1 张（['../assets/screenshots/01-bedside-alert.png']）

■ docs/demo/boards/02-silos-patient.html
  样子：浅·中性白底 #FFFFFF，无衬线标题（Plus Jakarta Sans），正文 ?
  ✓ 没有红灯，也没有模板装饰

■ docs/demo/boards/03-alert-stopwatch.html
  样子：浅·中性白底 #FFFFFF，无衬线标题（JetBrains Mono），正文 ?
  🟡 相对路径图片 1 张（['../assets/screenshots/03-standards.png']）

■ docs/demo/boards/04-multimodal-oncology.html
  样子：浅·中性白底 #FFFFFF，无衬线标题（Plus Jakarta Sans），正文 ?
  🟡 相对路径图片 1 张（['../assets/screenshots/02-patient360-oncology.png']）

■ docs/demo/boards/05-wardflow-cardiology.html
  样子：浅·中性白底 #FFFFFF，无衬线标题（Plus Jakarta Sans），正文 ?
  🟡 相对路径图片 1 张（['../assets/screenshots/01-bedside-alert.png']）

■ docs/demo/boards/06-clinician-signoff.html
  样子：浅·中性白底 #FFFFFF，无衬线标题（JetBrains Mono），正文 ?
  ✓ 没有红灯，也没有模板装饰

■ docs/demo/boards/07-endcard.html
  样子：浅·中性白底 #FFFFFF，无衬线标题（Plus Jakarta Sans），正文 ?
  🟡 相对路径图片 1 张（['../assets/screenshots/04-onelake-datamap.png']）
```

**Zero Red Findings.**  
**Yellow Explanation:** Relative screenshot paths (`../assets/screenshots/*.png`) are intentionally used rather than multi-megabyte base64 strings to keep HTML inspectable, modular, and prevent false-positive matches during automated privacy and PHI scanning (e.g. random substrings in base64 matching prohibited identifier patterns).

---

## 4. Board-Fix Rules Added to `YouTube-AI-Motion-Graphics/checks.md`

Committed to external clone `/Users/joey/git/YouTube-AI-Motion-Graphics` on branch `joey` (commit `be6efde`):
```markdown
- DO: in app-focus boards, place real UI screenshots at true 16:9 or native aspect ratio inside a crisp 1.5px border card with subtle shadow (ticket 011)
- DON'T: show dark glow navy backgrounds (#080d1a) or equal card rows for narrative clinical explainers; use Clean minimal paper (#FFFFFF / #F8F9FA) with one clinical accent (ticket 011)
```

---

## 5. Look Ledger Entry (`design_lint.py ledger`)

```text
已记账 → /Users/joey/.huashu-design/ledger.jsonl
  hls-fabric-demo: docs/demo/out/hls-fabric-demo-60s.mp4
```

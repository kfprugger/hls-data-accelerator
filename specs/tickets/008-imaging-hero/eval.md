# 008: Multimodal Imaging Hero View: Evaluation

## Setup
1. Ensure the local data files exist:
   ```bash
   /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python rayfin-imaging/pipeline/build_local_tables.py
   ```
2. Start the local development server:
   ```bash
   cd rayfin-imaging && ./node_modules/.bin/vite --mode localdata --port <port> --strictPort
   ```
3. Verify the app answers:
   ```bash
   curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/
   ```
   Expected: prints 200.

## Automated checks
- **A-1**: Build check
  ```bash
  cd rayfin-imaging && ./node_modules/.bin/tsc -b && ./node_modules/.bin/vite build --mode localdata --outDir dist-local && cd rayfin/functions && ./node_modules/.bin/tsc --build
  ```
- **A-2**: Test suite check
  ```bash
  cd rayfin-imaging && ./node_modules/.bin/vitest run && cd ../orchestrator && /Users/joey/git/.worktrees/hls-auth-refresh/orchestrator/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
  ```

## Acceptance checks
### E-1 [U] [browser] Multimodal hero side-by-side view rendering for Marcus Vance
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/patients?id=TCGA-G6-A8L6&tab=multimodal`.
  2. Verify that the "Multimodal hero" tab is selected.
  3. Verify that three panes are displayed: Radiology (3D CT), Pathology (H&E slide), and Genomics (Drivers).
  4. Verify that Marcus Vance's driver mutations (including `VHL`) are listed in the genomics pane.
- **Expected**: All three modality sections are visible concurrently in a side-by-side grid, with driver gene names, protein alterations, and variant allele frequencies clearly shown.
- **Evidence**: `specs/tickets/008-imaging-hero/evidence/E-1.png`

### E-2 [U] [browser] Real catalog size labels displayed on all three modalities
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/patients?id=TCGA-G6-A8L6&tab=multimodal`.
  2. Inspect the label on the Radiology pane.
  3. Inspect the label on the Pathology pane.
  4. Inspect the label on the Genomics pane.
- **Expected**: Each pane includes the exact prefix `Streamed from OneLake, never copied:` followed by the formatted byte size (e.g. `6.2 MB volume (72.0 MB raw DICOM)` for radiology, `1.4 GB slide` for pathology, and the Delta table size for genomics).
- **Evidence**: `specs/tickets/008-imaging-hero/evidence/E-2.png`

### E-3 [D] [browser] Responsive side-by-side layout at 1280 px and 360 px
- **Type**: browser
- **Steps**:
  1. Set viewport to 1280 × 800 px and capture screenshot of `/patients?id=TCGA-G6-A8L6&tab=multimodal`.
  2. Set viewport to 360 × 640 px and inspect layout flow.
  3. Verify horizontal scroll state: `document.documentElement.scrollWidth <= window.innerWidth`.
- **Expected**: At 1280 px, the three panes sit in a 3-column grid. At 360 px, the panes stack vertically with full width and no horizontal clipping.
- **Evidence**: `specs/tickets/008-imaging-hero/evidence/E-3-1280.png`, `specs/tickets/008-imaging-hero/evidence/E-3-360.png`

### E-4 [F] [browser] Designed empty state fallback when local image files are absent
- **Type**: browser
- **Steps**:
  1. In local mode without downloaded `.svs` or `.nii.gz` pixel files in `work/lakehouse/imaging/`:
  2. Open `http://localhost:<port>/patients?id=TCGA-G6-A8L6&tab=multimodal`.
  3. Observe the Radiology and Pathology viewer areas.
- **Expected**: The React application does not crash. The Radiology and Pathology slots display clean, designed fallback cards with the message `Local mode: pixel files not downloaded` and instructions to run download scripts, while metadata pills and the Genomics driver table remain completely intact and styled.
- **Evidence**: `specs/tickets/008-imaging-hero/evidence/E-4.png`

### E-5 [S] [automated] Safe asset URL generation and parameter validation
- **Type**: automated
- **Steps**:
  1. Run unit test in `rayfin-imaging/src/components/patient/tests/MultimodalHero.test.tsx` verifying file URL construction:
     ```bash
     cd rayfin-imaging && ./node_modules/.bin/vitest run src/components/patient/tests/MultimodalHero.test.tsx -t "security"
     ```
- **Expected**: Test passes; file URL builders sanitize relative paths against path traversal sequences (`../`), and reject non-allowed schemes.

### E-6 [R] [browser] Independent Pathology, Radiology, and Genomics tabs regression check
- **Type**: browser
- **Steps**:
  1. Open `http://localhost:<port>/patients?id=TCGA-G6-A8L6&tab=pathology`. Verify pathology viewer loads.
  2. Open `http://localhost:<port>/patients?id=TCGA-G6-A8L6&tab=radiology`. Verify radiology series viewer loads.
  3. Open `http://localhost:<port>/patients?id=TCGA-G6-A8L6&tab=genomics`. Verify genomics chromosome map loads.
- **Expected**: All three individual modality tabs continue to function as expected without visual or interaction regression.
- **Evidence**: `specs/tickets/008-imaging-hero/evidence/E-6.png`

### E-7 [Q] [automated] Memory cleanup and canvas unmount lifecycle validation
- **Type**: automated
- **Steps**:
  1. Run Vitest component unmount test for `MultimodalHero`:
     ```bash
     cd rayfin-imaging && ./node_modules/.bin/vitest run src/components/patient/tests/MultimodalHero.test.tsx -t "unmount"
     ```
- **Expected**: Verifies that unmounting the component destroys OpenSeadragon viewers and Niivue instances, releasing WebGL contexts without throwing errors or retaining references.

## Edge case checks
### E-8 [F] [browser] Patient with no radiology series empty state
- **Type**: browser
- **Steps**:
  1. Load a patient bundle mock with empty `radiologySeries: []`.
  2. Render `MultimodalHero`.
- **Expected**: Radiology slot displays `No radiology series available for this patient` while slide and genomics panes display normally.
- **Evidence**: `specs/tickets/008-imaging-hero/evidence/E-8.png`

### E-9 [F] [browser] Patient with zero driver mutations empty state
- **Type**: browser
- **Steps**:
  1. Load a patient bundle mock with empty `drivers: []`.
  2. Render `MultimodalHero`.
- **Expected**: Genomics slot displays `No somatic driver mutations detected` alongside the patient's molecular subtype, without crashing.
- **Evidence**: `specs/tickets/008-imaging-hero/evidence/E-9.png`

## Regression checks
- The `/patients` cohort list loads and filters correctly.
- Patient header summary bar (`diseaseLine`, `personLine`, `outcomeText`) remains visible on the multimodal tab.
- Tumour board notes counter and anchor links continue to function.

## Traceability
| Requirement | Evals |
|-------------|-------|
| FR-1        | E-1 |
| FR-2        | E-1, E-3 |
| FR-3        | E-2 |
| FR-4        | E-4 |
| FR-5        | E-1, E-4 |
| FR-6        | A-1, A-2 |
| NFR-1       | E-3 |
| NFR-2       | E-7 |
| NFR-3       | E-1 |

## Definition of done
- [ ] All automated checks pass (A-1, A-2)
- [ ] All acceptance checks E-1…E-7 pass
- [ ] All edge case checks E-8…E-9 pass
- [ ] No items from "Out of scope" were built

## Not covered
- Long-session token expiration: Rayfin local mode does not run an identity token refresh loop; authenticated tokens are supplied by Fabric app iframe hosting in production.
- Bulk batch download of raw DICOM/WSI datasets: The app is designed for interactive streaming, not bulk dataset export.

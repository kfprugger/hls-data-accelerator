# 008: Multimodal Imaging Hero View

**Status:** ready
| **Risk** | Medium: Multimodal imaging hero crashes when DICOM or SVS files are missing or stalls browser on large asset streaming |

## Summary
Introduce a unified side-by-side multimodal hero view for an oncology patient that simultaneously displays their 3D CT volume (via Niivue), H&E whole-slide pathology image (via OpenSeadragon), and top genomic driver mutations, with prominent on-screen labels showing "Streamed from OneLake, never copied: <size>" derived from catalog metadata, and graceful empty-state degradation when local pixel files are not present.

## Why
Oncology multidisciplinary tumor boards require correlating 3D anatomical scans, cellular-level histopathology, and molecular mutations side-by-side. Demonstrating this capability within a single responsive view in Rayfin proves to healthcare IT leaders that Microsoft Fabric can stream gigabyte-scale medical imaging directly to the client alongside structured genomics without copying bulk data into application caches.

## User stories
- As a clinical reviewer or tumor board participant, I want to inspect a patient's 3D CT volume, microscopic pathology slide, and genomic driver mutations on a single unified screen, so that I can assess radiographic findings, histopathology, and targeted therapy biomarkers without tab switching.
- As an enterprise healthcare architect evaluating Fabric, I want to see explicit on-screen badges showing "Streamed from OneLake, never copied: <size>" with real file and volume sizes, so that I can confirm that bulk imaging data is streamed on demand via secure SAS/OneLake URLs rather than replicated into the application tier.
- As a software engineer running in local development mode without multi-gigabyte slide or DICOM downloads, I want the multimodal view to gracefully display designed fallback cards rather than failing to render, so that local development and CI testing remain stable.

## Functional requirements
- **FR-1**: Add a `multimodal` tab to `TABS` in `rayfin-imaging/src/lib/record.ts` (`{ id: 'multimodal', label: 'Multimodal hero', group: 'overview', kinds: [], noun: 'modality', plural: 'modalities', hint: 'Side-by-side 3D CT scan, digital pathology, and genomic drivers' }`), making the view directly selectable in `PatientView.tsx`.
- **FR-2**: Provide a dedicated component `rayfin-imaging/src/components/patient/MultimodalHero.tsx` rendering a responsive three-pane layout:
  1. **Radiology Pane**: 3D CT volume rendering using `Niivue` with windowing and colormap controls.
  2. **Pathology Pane**: Whole-slide deep-zoom pyramid viewer using `OpenSeadragon`.
  3. **Genomics Pane**: Somatic driver alterations list detailing gene symbols, protein alterations, variant allele frequencies (VAF), mutation types, and tumor mutational burden (TMB).
- **FR-3**: Display on-screen badges and header labels for each modality:
  - **Radiology**: `Streamed from OneLake, never copied: <size>` showing formatted volume and raw DICOM sizes (e.g. `6.2 MB volume (72.0 MB raw DICOM)`), derived from `radiologySeries.volume_bytes` and `radiologySeries.raw_bytes`.
  - **Pathology**: `Streamed from OneLake, never copied: <size>` showing formatted slide file size (e.g. `1.4 GB slide`), derived from `slide.raw_bytes`.
  - **Genomics**: `Streamed from OneLake, never copied: <size>` showing formatted Delta table storage (e.g. `48.2 KB Delta`), derived from table inventory metadata.
- **FR-4**: Graceful local mode degradation: If image files (`.nii.gz` volumes, DICOM files, or `.dzi`/JPEG deep-zoom tiles) are absent from local storage (`work/lakehouse/imaging/`) or return HTTP 404, the viewers must NOT throw uncaught errors or crash the React application. Instead, the respective pane must render a designed fallback state indicating:
  - Clear message: `Local mode: pixel files not downloaded (run pipeline/download_data.py or pipeline/download_slides.py to view pixels)`.
  - Structured metadata pills showing series UID, modality, image dimensions, and cataloged file size.
- **FR-5**: The Genomic Drivers pane must remain completely interactive, fully styled, and accessible even when radiology or pathology pixel files are missing.
- **FR-6** (Fresh deployments): The feature must be implemented entirely within frontend React components and existing patient bundle data shapes, requiring no additional database migrations or live Azure setup scripts.

## Non-functional requirements
- **NFR-1**: Responsiveness: On viewports ≥ 1200 px, render a three-column side-by-side layout. On viewports below 1200 px down to 360 px, stack the panes vertically with zero horizontal scroll.
- **NFR-2**: Lifecycle & Cleanup: On component unmount or when switching between patients/tabs, active `Niivue` instances and `OpenSeadragon` viewers must be cleanly disposed of, terminating WebGL animation loops and aborting pending tile fetches.
- **NFR-3**: Initial Render: The metadata headers, streaming size badges, and genomic driver cards must render within 250 ms of tab selection.

## Edge cases & error handling
- Missing radiology series: If a patient record has no associated radiology scans, the radiology slot must display a clear empty state: `No radiology series available for this patient`.
- Missing pathology slides: If a patient record has no diagnostic slide, the pathology slot must display: `No whole-slide imaging available for this patient`.
- Zero driver mutations: If a patient has no identified protein-altering mutations, the genomics slot must display: `No somatic driver mutations detected` alongside their molecular subtype and TMB.
- WebGL unsupported: If client browser WebGL context initialization fails, Niivue must degrade to displaying series metadata and an alert indicating WebGL is unavailable.

## Out of scope
- Cross-patient multimodal comparison (the view is dedicated to single-patient assessment).
- Annotating or saving tumor board notes from inside the multimodal hero view (notes are managed in the Tumour Board tab).
- Modifying backend endpoints in `function_app.ts` or `local/api.ts` (existing `getPatient` API already provides all necessary series, slides, and drivers).

## Affected areas
- `rayfin-imaging/src/pages/PatientView.tsx`: Integration of `multimodal` tab route and rendering of `MultimodalHero`.
- `rayfin-imaging/src/components/patient/MultimodalHero.tsx`: New multimodal side-by-side component.
- `rayfin-imaging/src/components/patient/Imaging.tsx`: Exported fallback state helpers or error boundary support for viewers.
- `rayfin-imaging/src/lib/record.ts`: Updated `TABS` list and `TabId` union to include `multimodal`.
- `rayfin-imaging/src/components/patient/tests/MultimodalHero.test.tsx`: Unit tests for rendering, size formatting, and missing asset handling.

## Do not touch
- `orchestrator/activities/addons.py`
- `Deploy-All.ps1`
- `rayfin-imaging/rayfin/functions/src/function_app.ts`
- `rayfin-imaging/local/api.ts`
- `rayfin-imaging/src/pages/DataMap.tsx`
- `azure-databricks/*`

## Dependencies
- Depends on `001-local-demo-dataset` for local mode TCGA patient metadata and profiles.

## Decisions made
- **Agreed with the user**: Add a side-by-side view for one patient: 3D CT volume, H&E slide, and top genomic drivers, with on-screen labels "Streamed from OneLake, never copied: <size>" using real byte sizes from the catalogs. Must degrade cleanly in local mode when image files are missing.
- **Decided by the ticket writer**: Added as a new tab `multimodal` with label "Multimodal hero" under the `overview` tab group in `src/lib/record.ts`, positioned directly next to "Summary".
- **Decided by the ticket writer**: Sizes are formatted using the existing `fmtBytes` utility in `@/lib/format`, extracting `volume_bytes`/`raw_bytes` from `radiologySeries[0]` and `raw_bytes` from `slide`.
- **Decided by the ticket writer**: Designed empty state in local mode displays an informative callout box pointing developers to the download scripts while keeping all metadata pills intact.

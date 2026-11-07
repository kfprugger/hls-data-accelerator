# 009: Plain-Language Healthcare Copy & Fabric Glossary Tooltips

**Status:** ready

| **Risk** | Low: A copy label or glossary tooltip is misspelled or misaligned, confusing clinical viewers without impacting underlying data queries. |

## Summary
Executes a comprehensive terminology and copy transformation pass across the entire Rayfin web application (`rayfin-imaging/src/`). Replaces technical database identifiers, raw API/UDF function names, and IDs-as-headlines with intuitive, clinical outcome language. Integrates accessible, interactive glossary tooltips for seven foundational Microsoft Fabric architectural terms (OneLake, shortcut, Direct Lake, Eventhouse, Activator, Data Agent, Ontology) so hospital clinical and business stakeholders immediately comprehend how Microsoft Fabric powers each clinical view.

## Why
When healthcare IT executives, CMIOs, and clinical department chairs view a demonstration, seeing raw database artifact names like `dbo.molecular_profile`, `patient360_silos`, or uncontextualized strings like `TCGA-G6-A8L6` as main headlines distracts from clinical value and creates the impression of an unfinished engineering prototype. Translating these technical artifacts into clinical outcomes (such as "Genomic Biomarkers & Targeted Therapies") while providing educational, contextual tooltips for Fabric platform terms bridges the gap between infrastructure modernization and healthcare delivery.

## User stories
- As a Chief Medical Information Officer (CMIO), I want patient records and data summaries headlined by patient names, cancer stages, and clinical findings rather than internal database keys, so that I can evaluate the software as a real clinical decision platform.
- As a Healthcare Enterprise Architect, I want hoverable glossary tooltips on platform terms (OneLake, Direct Lake, Activator, etc.), so that visiting IT leaders quickly understand how Microsoft Fabric solves data replication and latency problems.
- As a Hospital CIO, I want clear descriptions of data sources and automated workflows that highlight patient safety and clinician-in-the-loop governance rather than internal pipeline step names.

## Functional requirements
- **FR-1**: Glossary Terminology Dictionary. The builder must create `rayfin-imaging/src/lib/glossary.ts` declaring concise, non-slop clinical and architectural definitions for the 7 required Fabric terms:
  1. `OneLake`: "Single, unified SaaS data lake for the entire organization — all data stored once in open Delta-Parquet format without data duplication."
  2. `shortcut`: "Zero-copy virtualization link connecting data across lakes and external storage without moving or duplicating a single byte."
  3. `Direct Lake`: "Ultra-fast Power BI query mode that reads Delta Parquet files directly from OneLake storage in memory without importing or duplicating data."
  4. `Eventhouse`: "Real-Time Intelligence database engine optimized for fast streaming telemetry, high-throughput append, and millisecond KQL queries."
  5. `Activator`: "Action engine that monitors real-time streaming data for specific clinical patterns or threshold breaches and triggers automated alerts."
  6. `Data Agent`: "Fabric AI agent combining domain ontology, ground truth schemas, and LLM reasoning to answer natural-language healthcare queries."
  7. `Ontology`: "Healthcare semantic graph (Ontology v2 / TMDL) defining clinical relationships, entities, and business definitions across disparate silos."
- **FR-2**: Reusable Glossary Tooltip Component. The builder must create `rayfin-imaging/src/components/GlossaryTooltip.tsx`.
  - Accessible via mouse hover (150 ms debounce) and keyboard focus (`focus-visible`).
  - Renders a subtle dotted underline or info indicator around the target term.
  - Provides proper ARIA attributes (`aria-describedby` or `role="tooltip"`).
  - Automatically flips or clamps position to avoid viewport clipping on small displays.
- **FR-3**: Clinical Outcome Copy Transformation Pass across `rayfin-imaging/src/`:
  - **Patient Views** (`Patients.tsx`, `Clinical.tsx`, `Genomics.tsx`, `Imaging.tsx`):
    - Replace raw patient ID headlines (e.g. `TCGA-G6-A8L6`) with primary patient name and condition headline: "Marcus Vance · Stage IV Clear Cell Renal Carcinoma", placing the TCGA identifier in subtle secondary metadata typography.
    - Transform raw table names in headers (`dbo.patient`, `dbo.molecular_profile`) to outcome titles ("Clinical Registry & Demographics", "Somatic Mutations & Molecular Drivers").
  - **Data Map** (`DataMap.tsx`):
    - Re-title technical silo badges to outcome-oriented domains: "Clinical Registry (OneLake)", "Sequencing Core (OneLake)", and "Digital Pathology & Radiology (OneLake)".
    - Surface glossary tooltips on `OneLake`, `shortcut`, and `Direct Lake` badges.
  - **Cardiology Workbench** (`WardFlow.tsx`):
    - Embed tooltips for `Eventhouse` and `Activator` in the Masimo telemetry monitoring bar.
    - Ensure triage beat status strings emphasize clinician governance (e.g., "Awaiting Clinician Sign-Off" instead of raw status strings).
  - **Overview and Navigation** (`Overview.tsx`, `AppShell.tsx`):
    - Replace engineering phrases with outcome language highlighting zero data duplication, multi-modal care coordination, and rapid clinical insights.
- **FR-4**: Zero Behavioral Change. The copy transformation must not modify any API endpoints, query parameter keys, component state, prop interfaces, or event handling. The application must function identically before and after the copy pass.
- **FR-5**: Fresh Deployments CLI Audit Script. The builder must create a standalone CLI script `rayfin-imaging/scripts/audit_ui_copy.py`.
  - Scans `rayfin-imaging/src/` to verify that no forbidden raw jargon strings remain unmapped in headlines, and checks that all 7 glossary terms are present and referenced via `GlossaryTooltip`.
  - Supports `--dry-run` (default) and exits with code 0 on clean validation.
  - Idempotent and runnable without live Azure credentials.

## Non-functional requirements
- **NFR-1**: Glossary tooltip hover response time under 150 ms; dismisses cleanly on mouse leave or Escape key press.
- **NFR-2**: Zero Cumulative Layout Shift (CLS 0): Tooltip overlay does not cause layout jitter or reflow of surrounding text.
- **NFR-3**: Responsive typography: Headings and patient titles wrap cleanly on mobile (360 px) and desktop (1280 px) with zero horizontal scrollbar.
- **NFR-4**: Full WCAG 2.1 AA accessibility compliance: Contrast ratio >= 4.5:1 for body copy and 7:1 for headings; screen-reader accessible tooltip descriptions.

## Edge cases & error handling
- Extremely long patient name or condition title: CSS `text-overflow: ellipsis` and responsive flex wrapping ensure layout does not break on smaller screens.
- Screen edge tooltips: The tooltip detects boundary overflow and flips orientation from top/bottom or left/right automatically.
- Rapid hover sequence: Tooltip timers are cleanly cancelled on unmount or blur, preventing orphaned tooltip DOM elements.

## Out of scope
- Renaming backend database columns, SQL views, or parquet table names in `work/tables/`.
- Changing route paths or URL structure.
- Altering core visual themes or brand identity.
- Editing `orchestrator/activities/addons.py` or `Deploy-All.ps1`.

## Affected areas
- `rayfin-imaging/src/lib/glossary.ts`: new glossary definitions dictionary.
- `rayfin-imaging/src/components/GlossaryTooltip.tsx`: new glossary tooltip component.
- `rayfin-imaging/src/components/AppShell.tsx`: shell navigation and header copy refinement.
- `rayfin-imaging/src/pages/Patients.tsx`: patient header, search, and tab copy.
- `rayfin-imaging/src/pages/Overview.tsx`: landing page copy pass.
- `rayfin-imaging/src/pages/DataMap.tsx`: data map silo and table card copy.
- `rayfin-imaging/src/pages/WardFlow.tsx`: cardiology workbench terminology and tooltips.
- `rayfin-imaging/src/pages/Volumes.tsx`: 3D/4D imaging copy.
- `rayfin-imaging/src/pages/Pathology.tsx`: digital pathology copy.
- `rayfin-imaging/src/components/patient/Clinical.tsx`: clinical tab copy.
- `rayfin-imaging/src/components/patient/Genomics.tsx`: genomics tab copy.
- `rayfin-imaging/src/components/patient/Imaging.tsx`: imaging tab copy.
- `rayfin-imaging/scripts/audit_ui_copy.py`: standalone CLI copy audit script.

## Do not touch
- `rayfin-imaging/rayfin/functions/*`
- `rayfin-imaging/local/api.ts`
- `orchestrator/*`
- `Deploy-All.ps1`

## Dependencies
- Waits for UI tickets: `003-zero-copy-proof`, `005-data-agent-qa`, `006-phi-persona-views`, `007-standards-view`, `008-imaging-hero`, `010-databricks-interop`. Must run after these tickets so all newly added UI elements receive the copy pass and glossary tooltips.

## Decisions made
- **Agreed with the user**: Replace raw API names, IDs-as-headlines, and engineering jargon with outcome language; provide glossary tooltips for the 7 Fabric terms (OneLake, shortcut, Direct Lake, Eventhouse, Activator, Data Agent, Ontology); runs after UI tickets; does not change behavior.
- **Decided by the ticket writer**:
  - Technical identifiers (e.g. `TCGA-G6-A8L6`, Delta table names) are retained as secondary mono metadata labels or within technical detail drawers rather than being deleted entirely, ensuring technical credibility for IT architects.
  - Centralized definitions in `src/lib/glossary.ts` prevent copy drift across different pages.
  - Script `rayfin-imaging/scripts/audit_ui_copy.py` is established as the automated verification check for CI and fresh deployments.

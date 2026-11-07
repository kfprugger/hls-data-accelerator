# HLS Data Accelerator — 60-Second Demo Film Voiceover

**Speaker:** Joey Brakefield  
**Voice Profile:** Kokoro `0.80 * am_michael + 0.20 * am_liam` (`speed=1.00`), mastered to -16 LUFS  
**Storyline:** Storyline A ("Bed 04 at 02:14 AM — One Patient Across Five Worlds")  
**Target Duration:** 63.48 s (NFR-1 target: 55.0–65.0 s)  

---

## Technical Pronunciation Guide
- **FHIR:** "fire" (`/ˈfaɪ.ər/`)
- **SQL:** "sequel" (`/ˈsiː.kwəl/`)
- **HIPAA:** "hippa" (`/ˈhɪp.ə/`)
- **DICOM:** "die-com" (`/ˈdaɪ.kɒm/`)
- **OneLake:** "one lake" (`/wʌn leɪk/`)
- **ICU:** "I-C-U"
- **EHR:** "E-H-R"
- **VHL:** "V-H-L"
- **CT:** "C-T"

---

## Evidence Sources for Every Claim
- **Patient & Bed:** Marcus Vance (`TCGA-G6-A8L6`, 55M, clear cell renal carcinoma) — Source: `specs/tickets/001-local-demo-dataset/results.md` & `/patients`
- **Device & Acute Vitals:** Device `MASIMO-RADIUS7-0101`, SpO2 `84.0%` (CRITICAL), Pulse Rate `115 bpm` — Source: `specs/tickets/004-realtime-alert-stopwatch/results.md` (E-1) & `AlertStopwatchCard` component
- **Measured Stopwatch:** `20.5 s` end-to-end latency (Eventhouse KQL `TelemetryRaw` to `fn_ClinicalAlerts` to Activator dispatch, budget 60.0 s) — Source: `specs/tickets/004-realtime-alert-stopwatch/results.md` (E-12) & `AlertStopwatchCard`
- **Multimodal Oncology:** Somatic `VHL` mutation, 3D TotalSegmentator CT volume, pathology whole-slide biopsy — Source: `/p/TCGA-G6-A8L6` & `MultimodalHero`
- **Cardiology Triage & Human Gate:** WardFlow acute hemodynamic monitoring, Stevenson 2×2 grid, SCAI Stage C shock, Beat 4 human approval gate blocking autonomous execution — Source: `/wardflow`
- **Zero-Copy Shortcuts:** 32 OneLake shortcuts conforming `clinical_lakehouse`, `genomics_lakehouse`, and `imaging_lakehouse` into `patient360` with zero duplicate bytes copied — Source: `specs/tickets/003-zero-copy-proof/results.md` (E-4, R-3) & `/data`
- **Databricks Interop:** 15 TCGA patients verified matching between Azure Databricks Unity Catalog and Microsoft Fabric (`15 = 15`) with zero data duplication — Source: `specs/tickets/010-databricks-interop/results.md` (E-2)

---

## Timecoded Script & Beat Mapping

### Beat 1 (0:00–12.66): Bed 04 Acute Vital Deterioration
**On Screen:** Focused Masimo Radius-7 bedside monitor crop for Bed 04, Marcus Vance (`TCGA-G6-A8L6`), SpO2 84.0%, Pulse Rate 115 bpm.  
**Say:**  
> It is two fourteen AM in the cardiac ICU. Bed four alarms: Marcus Vance, device Masimo Radius-7, drops to eighty-four percent oxygen at one fifteen bpm.

### Beat 2 (12.66–23.34): Silo Convergence into OneLake
**On Screen:** Animated convergence scene: six legacy hospital silos (EHR, cBioPortal, PACS, CD, Labs, Registry) collapsing into a single central OneLake `patient360` shortcut view.  
**Say:**  
> In legacy systems, that alert triggers six disconnected logins and stalled viewers. Here, OneLake shortcuts collapse those silos into one unified patient record.

### Beat 3 (23.34–30.78): Measured 20.5-Second Alert Stopwatch
**On Screen:** Focused crop of `AlertStopwatchCard`: Real-Time Intelligence pipeline, Eventhouse KQL TelemetryRaw, 20.5s measured end-to-end latency.  
**Say:**  
> Our measured alert stopwatch clocked the pipeline at twenty point five seconds from bedside telemetry to alert dispatch.

### Beat 4 (30.78–39.80): Multi-Modal Oncology 360
**On Screen:** Focused crop of Marcus Vance's Multimodal Hero: `VHL` somatic mutation, 3D NiiVue CT volume, OpenSeadragon pathology slide streaming via OneLake SAS.  
**Say:**  
> Open Marcus Vance’s Patient three-sixty: his VHL mutation, 3D CT, and pathology stream live from OneLake.

### Beat 5 (39.80–51.42): WardFlow Governed Cardiology Triage
**On Screen:** Focused crop of WardFlow cardiology cohort: Stevenson 2×2 grid, SCAI Stage C shock, 7-beat triage agent halting at Beat 4 (Awaiting Clinician Approval).  
**Say:**  
> In WardFlow cardiology, the acute cohort tracks hemodynamic stability. The seven-beat triage escalates guideline care, halting at beat four for clinician approval.

### Beat 6 (51.42–58.88): Clinician Governance & Fabric Audit Trail
**On Screen:** Clinician gate enforced: Attending clinician sign-off commits directly to Fabric conformed Delta tables with complete audit provenance and zero duplicate copies.  
**Say:**  
> The attending clinician approves the order, maintaining a complete Fabric audit trail with zero duplicate copies.

### Beat 7 (58.88–63.48): Architecture Payoff & End Card
**On Screen:** Focused crop of Zero-Copy Data Map: "Three silos, one patient, no copies · 2,545 rows · 0 B copied", 15 TCGA patients verified across Fabric and Databricks (`15 = 15`), final hold on `hls.jbatl.dev`.  
**Say:**  
> From bedside waveform to boardroom confidence, on Microsoft Fabric.

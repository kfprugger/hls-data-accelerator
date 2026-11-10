# Rayfin App Screenshots (Marcus Vance Story & WardFlow)

Captured on 2026-11-09 for the HLS Data Accelerator marketing deck and film.
The patient narrative follows synthetic patient Marcus Vance (`TCGA-G6-A8L6`) and the WardFlow Cardiology bedside deterioration loop.

| File | Pixel Size | URL / Route | Source | Verbatim Numbers / Clinical Metrics Visible | Notes |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `01-patient-header.png` | 3112 × 735 | `https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net/p/TCGA-G6-A8L6` | live | Stage IV, 55 M, Died 10 months after diagnosis, Apr 2011, 44 mutations · 1.4 per Mb, 2 diagnoses · 3 treatments · 1 follow-ups, 10 visits · 110 results, 44 mutations · 5 CN segments, 1.1 gigapixels · 210.4 MB SVS, 1 study · 72 MB DICOM, 28 queries · 3 silos · 1.5 s · 0 bytes copied | Patient 360 header with Marcus Vance, TCGA-G6-A8L6, diagnosis, and full 6-modality source summary row |
| `02-alert-stopwatch.png` | 2992 × 881 | `http://localhost:5177/p/TCGA-G6-A8L6` | local fallback | End-to-End Latency: 20.5s, SpO₂: 84.0%, PR: 115 bpm, Beat 1: +0.0s, Beat 2: +3.5s, Beat 3: +10.2s, Beat 4: +20.5s, Latency Budget: 18.4s of 60.0s, Allowlist Recipient: joey@jbatl.dev (10-min dedupe cooldown) | Real-time bedside alert stopwatch card (Fabric RTI, Eventhouse, Activator; zero 'local mode' text) |
| `03-genomics-vhl.png` | 933 × 797 | `https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net/p/TCGA-G6-A8L6?tab=genomics` | live | 44%, 39%, 36% | Driver gene alterations table showing VHL (p.R82Afs*50 Frameshift Del 44%, Deep deletion, Positive IHC) |
| `04-ct-volume.png` | 2864 × 1657 | `https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net/p/TCGA-G6-A8L6?tab=radiology` | live | Primary organ: 484 mL, Lesion / Mass: 38.5 mL, 6.2 MB in 10.2 s, 31 Mar 2011 · day −7, 140 images, 1.5 mm slices, Original 72 MB DICOM (140 files) | 3D CT volume viewer rendered via WebGL from OneLake with TotalSegmentator v2 AI segmentation |
| `05-pathology-slide.png` | 2864 × 1402 | `https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net/p/TCGA-G6-A8L6?tab=pathology` | live | 1.25×, 5×, 10×, 20×, 40×, 0.62×, 2 mm, 31,948 × 35,887 px (1.1 gigapixels), 1,492 tiles in 17 levels; 3 loaded, first in 603 ms, Original 210.4 MB Aperio SVS, 13% lymphocyte-rich tiles | Whole-slide pathology viewer with diagnostic H&E tissue rendered via OpenSeadragon |
| `06-wardflow-cohort.png` | 2504 × 1062 | `https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net/wardflow?view=cohort` | live | Monitored cohort: 24 (+76 enrollable in Gold), Critical / SCAI D–E: 0, Concerning / At-risk: 4, MCS & device support: 0, Linked 3D CT volumes: 1, Pending human approvals: 4, 120.9 bpm, 3 mmol/L, 72 mmHg, 96%, 58.1 SCAI C, 92.7 bpm, 3 mmol/L, 71 mmHg, 98%, 50.1 SCAI C, 116.2 bpm, 2.1 mmol/L, 79 mmHg, 90%, 43.2 SCAI B | WardFlow cohort KPIs, Masimo continuous SpO2 telemetry stream bar, and live cohort rows (M.F., G.H., A.Z.) |
| `07-wardflow-beat4.png` | 1311 × 1238 | `https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net/wardflow?view=agent&subject=649702aa-07ab-042a-5c1f-06db4c7f9006` | live | Beat 1: lactate 2.99 → 5.59 mmol/L · MAP 72.4 → 54.4 mmHg · PR 120.9 → 155 /min; Beat 2: at-risk (58.1) → critical (98.6, SCAI D); Beat 3: confidence 0.82 · 640 tokens, 6 observed measures; Beat 4: Awaiting Clinician Sign-Off | Agent loop paused at Beat 4 awaiting clinician sign-off in Rayfin Fabric SQL before dispatch |
| `08-data-map.png` | 2608 × 500 | `https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net/data` | live | 459.1 MB stored in the silos · 1,499 files · 2,530 table rows · 0 B copied into the app · this page read live in 2.2 s | Data Map hero 'Three silos, one patient, no copies' with live OneLake storage and read metrics |
| `09-synthetic-badge.png` | 507 × 62 | `https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net/p/TCGA-G6-A8L6` | live | 100% | '100% synthetic / public de-identified data' compliance badge in the app shell |

## Shot Coverage Summary

- **Total shots requested**: 9
- **Total shots captured**: 9
- **Unobtainable shots**: 0 (all 9 successfully captured with high fidelity)
- **Viewport & Device Scale**: 1600 × 900 CSS px, deviceScaleFactor 2
- **Framing Guarantee**: Whole self-contained component with clean borders and zero truncated text on any edge.
- **Data Source Fidelity**:
  - 8 shots captured directly from the live deployed Microsoft Fabric Rayfin app for med-1103a (`https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net`).
  - 1 shot (`02-alert-stopwatch.png`) comes from local mode (`http://localhost:5177`) because the med-1103a backend did not expose the `getAlertStopwatch` UDF when the shots were captured. The card shows no "local mode" or "this computer" text.

# HLS Data Accelerator — Five-Minute Executive Walkthrough Script

**Presenter:** Joey Brakefield (Technical Specialist / Solution Architect)  
**Target Audience:** Healthcare CIO, CMIO, Chief Medical Officer, Tumor Board & Cardiology Leadership  
**Total Duration:** 5 minutes (0:00 – 5:00)  
**Environment:** Local Rayfin app (`http://localhost:3111`) or Fabric Live (`https://elfin-field-43838dcb1c-westus2.webapp.fabricapps.net`)  
**Data Governance:** 100% Synthetic & De-identified Open Research Data (TCGA-KIRC + Synthea under HIPAA Safe Harbor §164.514)  

---

## Phase 1 (Minute 0:00–1:00): Executive Context & Bedside Alarm

- **Route:** `/wardflow`
- **Visual Focus:** Bed 04 Marcus Vance (`TCGA-G6-A8L6`), Alert Stopwatch Card, SpO2 Trigger (`84.0%`), Pulse Rate (`115 bpm`), Device `MASIMO-RADIUS7-0101`.
- **Click Target:** Bed 04 Alert Banner in WardFlow Active Cohort or Patient 360 Header.
- **Visual Proof Point:** Stopwatch card displaying `20.5s` pipeline latency from Masimo device telemetry to clinician alert dispatch.
- **Spoken Narrative (Joey Voice):**
  > "Good morning. We’ve all seen what happens when acute bedside telemetry lives in a separate silo from the oncology EHR and PACS archive. It is 02:14 in the morning. Bed 4 alarms: Marcus Vance, a 55-year-old with stage IV clear-cell renal carcinoma, has dropped his oxygen saturation to eighty-four percent and spiked a sinus tachycardia of 115 on his Masimo Radius-7 device.
  > In a traditional healthcare estate, a critical event like this takes minutes just to pull the prior oncology regimen and cardiology consults across four separate logins.
  > Here on Microsoft Fabric, Real-Time Intelligence ingested that Masimo telemetry, evaluated the clinical threshold in Eventhouse KQL, and dispatched the notification in exactly 20.5 seconds. Let’s click Marcus Vance and see his complete multi-modal clinical record."

---

## Phase 2 (Minute 1:00–2:00): Multi-Modal Oncology 360

- **Route:** `/patients` → `/p/TCGA-G6-A8L6`
- **Visual Focus:** Patient 360 Header (Marcus Vance, 55M, Stage IV), Genomics Tab (`VHL R82Afs*50` lollipop plot), 3D CT Volume (NiiVue renderer), Digital Pathology (OpenSeadragon kidney biopsy).
- **Click Target:** Switch between `Genomics`, `Imaging (3D CT)`, and `Pathology` sub-tabs.
- **Visual Proof Point:** High-resolution 3D CT volume and gigapixel whole-slide pyramid streaming via direct 55-minute OneLake SAS URLs without moving files or making copies.
- **Spoken Narrative (Joey Voice):**
  > "Notice what just happened. We didn’t copy this patient’s data into a proprietary web application database. Every tab you see here is querying OneLake shortcuts directly.
  > Under the Genomics tab, you see his clear-cell renal carcinoma 3p loss, anchored by a somatic `VHL` frameshift mutation.
  > When I switch to 3D Imaging, our NiiVue viewport streams his abdominal CT angiogram, segmented with TotalSegmentator, directly from the ADLS Gen2 imaging lakehouse.
  > And under Pathology, OpenSeadragon pulls the deep-zoom H&E histology slide. One patient, three clinical domains, zero duplicate data silos."

---

## Phase 3 (Minute 2:00–3:00): Standards Transparency (FHIR & DICOM Lineage)

- **Route:** `/standards`
- **Visual Focus:** Standards lineage diagram, FHIR R4 Patient/Observation resources, DICOM metadata tag mapping (`(0010,0020)` Patient ID, `(0008,1030)` Study Description) into conformed Delta tables.
- **Click Target:** Filter toggle for `FHIR R4 Resources` and `DICOM Tag Lineage`.
- **Visual Proof Point:** Transparent transformation contract proving every clinical data element conforms to open HL7 FHIR and DICOM part 10 standards before landing in Delta Parquet.
- **Spoken Narrative (Joey Voice):**
  > "Enterprise health systems can’t afford black-box transformations. When your compliance and interoperability teams ask how this data got into Fabric, you click Standards.
  > Here is the exact HL7 FHIR R4 schema mapping: Observation resources from bedside telemetry, Condition resources from the EHR, and DICOM tag attributes from the PACS archive.
  > Every study preserves its standard DICOM tags—patient ID, series UID, slice thickness—retained cleanly inside Delta lakehouse tables. This means you maintain full CMS-0057 compliance and FHIR bulk export readiness while running advanced analytics."

---

## Phase 4 (Minute 3:00–4:00): Governed Cardiology Triage (WardFlow)

- **Route:** `/wardflow`
- **Visual Focus:** Stevenson 2×2 Hemodynamic Grid, acute shock cohort, 7-Beat Cardiology Triage Agent loop paused at **Beat 4 (Awaiting Clinician Approval)**.
- **Click Target:** "Review & Sign" button on Beat 4 card.
- **Visual Proof Point:** The AI agent does not self-execute therapy. Beat 4 enforces an ironclad human-in-the-loop clinical approval gate. Upon clicking "Approve & Sign", the transaction commits directly to conformed Delta tables with complete audit provenance.
- **Spoken Narrative (Joey Voice):**
  > "Now we look at acute cardiac triage in WardFlow. The AI triage agent evaluated hemodynamic risk and plotted the cohort across the Stevenson 2×2 grid.
  > Notice that Beats 1 through 3 drafted the guideline-directed therapy escalation, but the system halts completely at Beat 4. In regulated healthcare, an AI agent must never order inotropic support or diuretic changes autonomously.
  > As the attending clinician, I review the recommendation, verify clinical context, and click 'Approve & Sign'.
  > That signed order commits an immutable audit record to Fabric with zero duplicate copies, ensuring full regulatory adherence while the patient receives verified, guideline-guided care."
---

## Phase 5 (Minute 4:00–5:00): Zero-Copy Fabric Architecture & Conclusion

- **Route:** `/data`
- **Visual Focus:** Fabric OneLake Data Map, Delta Lakehouses (`clinical_lakehouse`, `genomics_lakehouse`, `imaging_lakehouse`), Databricks Unity Catalog interop shortcut, Orchestrator Deployment History.
- **Click Target:** Hover over `patient360` conformed shortcut layer; click Databricks Unity Catalog external location icon.
- **Visual Proof Point:** Zero data duplication across lakehouses; bi-directional interop between Microsoft Fabric and Azure Databricks.
- **Spoken Narrative (Joey Voice):**
  > "To wrap up: look at where this data actually lives.
  > We did not build another clinical data warehouse with expensive nightly ETL pipelines.
  > Through Fabric OneLake shortcuts, our clinical lakehouse, genomics lakehouse, and DICOM imaging lakehouse are conformed into a single zero-copy logical view.
  > Even better, your data science team can query this exact same Delta table from Azure Databricks Unity Catalog without moving a single gigabyte.
  > From bedside telemetry at 20.5 seconds, to 3D multimodal oncology, to governed clinician-in-the-loop cardiology triage—this is the modern healthcare data estate on Microsoft Fabric. Thank you."

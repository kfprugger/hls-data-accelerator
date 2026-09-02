# HDS Explainer — B-Roll Recording Script

## Recording standard

- Record at **2560×1440, 30 fps** or higher; deliver at 1280×720, 30 fps.
- Use **Microsoft Edge — Work / BrakeKat** for authenticated Fabric footage.
- Hide bookmarks, downloads, notifications, personal tabs, tenant alerts, and unrelated browser chrome.
- Set browser zoom to **100%**. Keep the pointer still before and after every action.
- Record each shot for 3 seconds before moving and 3 seconds after the final action.
- Move deliberately. Do not whip-scroll, circle the pointer, or repeatedly open and close panels.
- Do not apply a whole-frame zoom, crop, or Ken Burns effect. Preserve the recorded frame exactly. Emphasis can be added later with callouts or animated highlights.
- Do not show secrets, access tokens, connection strings, patient identifiers, email addresses, or resource credentials.
- Use only synthetic patients and demonstration data.
- Record without narration; the existing A-roll provides the audio bed.

## Required recordings

### BR01 — Microsoft delivery-model announcement

**Target length:** 18–22 seconds  
**Filename:** `BR01-microsoft-transition-notice.mov`

**Open:** [Microsoft Learn — Get started with healthcare data solutions](https://learn.microsoft.com/en-us/industry/healthcare/healthcare-data-solutions/get-started)

**Actions:**

1. Begin on the page title and the complete **Important** notice.
2. Pause on **August 3, 2026**.
3. Move the pointer to **October 1, 2026** and pause.
4. Move to **December 31, 2027** and pause.
5. Finish on the **Microsoft Download Center** link without clicking it.

**Correlates with:** Microsoft moved HDS to a downloadable, customer-managed source package.

---

### BR02 — Microsoft Download Center package

**Target length:** 15–20 seconds  
**Filename:** `BR02-hds-download-center.mov`

**Open:** Microsoft Download Center entry linked from the Learn notice.

**Actions:**

1. Establish the product title: **Healthcare data solutions in Microsoft Fabric**.
2. Show the version and published information.
3. Scroll once to the package/download details.
4. Pause on the Download control and package description.
5. Do not start a download during the recording.

**Correlates with:** This is a real software and documentation package, not another portal checklist.

---

### BR03 — HDS 1.4.0 package contents

**Target length:** 25–30 seconds  
**Filename:** `BR03-hds-package-contents.mov`

**Open:** Repository explorer at `vendor/microsoft-hds/1.4.0/`.

**Actions:**

1. Start with the `1.4.0` folder collapsed.
2. Expand it once.
3. Highlight `HDS.SourceCode/` and `DTT.SourceCode/`.
4. Highlight `Deployment Guide.docx`, `Transition Guide.docx`, and `Microsoft License Terms.txt`.
5. Expand `HDS.SourceCode/src/tools/sampleData/`.
6. End on `HDS.SourceCode/src/config/` and its reference/configuration content.

**On-screen accuracy:** Call it **source-available**, not open source.

---

### BR04 — Old portal-managed workflow

**Target length:** 25–30 seconds  
**Filename:** `BR04-old-portal-workflow.mov`

**Open:** Legacy `med-device-fabric-emulator` repository.

**Actions:**

1. Show `fabric-rti/HDS-SETUP-GUIDE.md` and the two-phase flow.
2. Scroll to the point where automation stops for portal work.
3. Show `docs/phase-1-infrastructure-and-ingestion.md`, Step 4.
4. Pause on the manual environment/package configuration.
5. End on the instruction to return to the scripts for the next phase.

**Correlates with:** Automate, stop, configure HDS manually, then restart automation.

---

### BR05 — New source-driven deployment code

**Target length:** 30–35 seconds  
**Filename:** `BR05-new-source-deployment.mov`

**Open:** `hls-data-accelerator` repository.

**Actions:**

1. Show `hds-source/Deploy-HdsSource.ps1` at the deployment entry point.
2. Search within the file for payload validation and pause on the matching block.
3. Show the HDS/DTT wheel build and OneLake upload steps.
4. Open `orchestrator/activities/deploy_hds_source.py`.
5. Pause on the dependency-stage execution and validation logic.
6. End on the expected artifact validation contract in `fabric-rti/HDS-SETUP-GUIDE.md`.

**Correlates with:** Validate, build, upload, deploy, and verify as one engineered flow.

---

### BR06 — Live HDS workspace inventory

**Target length:** 18–22 seconds  
**Filename:** `BR06-live-hds-workspace.mov`

**Open:** Fabric workspace `med-0803`.

**Actions:**

1. Begin at the workspace root in list view.
2. Show the folders for deployment notebooks, pipelines, Real-Time, reports/semantic models, and validation notebooks.
3. Scroll slowly enough to reveal the deployed lakehouses and ontology artifacts.
4. End with the workspace name visible.

**Correlates with:** The deployment creates a complete, inspectable Fabric artifact contract.

---

### BR07 — Deployed HDS pipelines

**Target length:** 22–28 seconds  
**Filename:** `BR07-live-hds-pipelines.mov`

**Open:** `med-0803` → `Pipelines`.

**Actions:**

1. Establish the breadcrumb `med-0803 > Pipelines`.
2. Slowly scroll through:
   - clinical FHIR export and ingestion
   - claims ingestion
   - imaging ingestion
   - CMA transformation
   - OMOP analytics
   - SDoH ingestion
3. Pause briefly on each group; do not open or run a pipeline.

**Correlates with:** Clinical, imaging, claims, CMA, OMOP, and SDoH are deployed together.

---

### BR08 — End-to-end architecture walkthrough

**Target length:** 25–30 seconds  
**Filename:** `BR08-architecture-walkthrough.mov`

**Open:** `Project_Architecture_Blueprint.md` and `docs/images/Simple Diagram.png`.

**Actions:**

1. Start with the whole architecture visible.
2. Point to Synthea/FHIR inputs.
3. Move to TCIA/DICOM.
4. Move to Masimo device telemetry and Event Hub/Eventstream.
5. Trace into OneLake/Eventhouse and Bronze–Silver–Gold.
6. Finish on Power BI, Data Agents, ontology, Activator, and operational actions.

**Correlates with:** One connected MedTech, provider, and payer data journey.

---

### BR09 — Patient 360 Data Agent

**Target length:** 18–22 seconds  
**Filename:** `BR09-patient-360-agent.mov`

**Open:** `Patient 360` in Fabric.

**Actions:**

1. Establish the `Patient 360` title.
2. Show the Explorer pane with the connected lakehouses.
3. Pause on a visible example query such as average patient age.
4. Show the generated-answer and code areas without submitting a new query.
5. End with the data-source list visible.

**Correlates with:** HDS data supports governed, conversational patient analytics.

---

### BR10 — Imaging report and OHIF path

**Target length:** 20–25 seconds  
**Filename:** `BR10-imaging-report-ohif.mov`

**Open:** `ImagingReport`, then the OHIF viewer if it is healthy.

**Actions:**

1. Show the imaging overview page and study/file counts.
2. Pause on modality distribution and the studies table.
3. Select one synthetic study only if it is safe and responsive.
4. Cut to the OHIF study viewer and show image-series navigation.
5. Do not reveal real patient data.

**Correlates with:** DICOM ingestion leads to cohorting, reporting, and image review.

---

### BR11 — Claims and quality report inventory

**Target length:** 18–22 seconds  
**Filename:** `BR11-claims-report-inventory.mov`

**Open:** `med-0803` → `Reports and Semantic Models`.

**Actions:**

1. Establish the breadcrumb and workspace.
2. Pause on **Population Health & Quality Dashboard**.
3. Show its semantic model beside the report.
4. Show the CMA and imaging reports for platform breadth.
5. Do not open a report if Fabric displays a capacity-unavailable error.

**Correlates with:** Claims and quality are deployed as first-class reporting artifacts.

---

### BR12 — Population Health and Quality report

**Target length:** 35–45 seconds  
**Filename:** `BR12-population-health-quality-report.mov`

**Record only if the report opens without an error.**

**Actions:**

1. Establish the report title and Quality Overview page.
2. Advance through the report using single, deliberate page changes:
   - Claims Analytics
   - Medication Adherence
   - Care Gap Closure
   - Payer Performance
   - Star Rating
   - Risk Adjustment
   - Readmission Risk
   - Utilization Overview
3. Pause 2–3 seconds on each page.
4. Do not scroll rapidly or hover long enough to trigger distracting tooltips.

**Correlates with:** Claims, quality, adherence, risk, cost, and utilization in one model.

---

### BR20 — Claims materialization and Gold tables

**Target length:** 30–35 seconds  
**Filename:** `BR20-claims-materialization-gold.mov`

**Open:** `docs/phase-5-cms-quality-and-claims.md`, `phase-5/materialize_claims_quality.py`, then the reporting Gold lakehouse in Fabric.

**Actions:**

1. Show the claims-and-quality architecture and expected outputs in the phase document.
2. Open `materialize_claims_quality.py` and pause on the Gold-table definitions/materialization flow.
3. In Fabric, show the Gold table inventory, including claims, diagnosis, quality, adherence, care-gap, HCC/RAF, readmission, and utilization outputs.
4. Keep the table list readable; do not expose row-level patient identifiers.

**Correlates with:** The accelerator materializes a 23-table reporting model before Power BI turns it into ten analytical pages.


---

### BR13 — SDoH seed and CMA context

**Target length:** 25–30 seconds  
**Filename:** `BR13-sdoh-cma.mov`

**Open:** `phase-2/seed_cma_sdoh.py`, then Fabric CMA tables.

**Actions:**

1. Pause on the Atlanta ZIP-to-FIPS mapping.
2. Show the deterministic seed logic.
3. Highlight the source banner stating the values are synthetic.
4. Show the category and measure definitions.
5. In Fabric, show the CMA Gold lakehouse tables created by the seed.

**Required disclaimer:** These are deterministic synthetic demonstration indicators—not live epidemiology or real patient risk scores.

---

### BR14 — Claims Eventstream

**Target length:** 20–25 seconds  
**Filename:** `BR14-claims-eventstream.mov`

**Open:** `med-0803` → `Real-Time` → `ClaimsRTIStream`.

**Actions:**

1. Establish the Eventstream title.
2. Show the claim Event Hub source.
3. Trace the connection through `ClaimsRTIStream`.
4. Finish on the Eventhouse destination.
5. If data preview is available, show it briefly; do not imply that an inactive source is currently streaming.

**Correlates with:** Claims use a dedicated real-time stream separate from device telemetry.

---

### BR15 — Payer real-time artifact inventory

**Target length:** 18–22 seconds  
**Filename:** `BR15-payer-realtime-artifacts.mov`

**Open:** `med-0803` → `Real-Time`.

**Actions:**

1. Slowly show `ClaimsRTIStream`.
2. Show `PayerOpsActivator`.
3. Show the clinical alert artifacts and Masimo telemetry artifacts for contrast.
4. Keep the workspace and folder names visible.

**Correlates with:** Clinical telemetry and payer operations coexist while retaining separate streams.

---

### BR16 — Payer Ops Activator

**Target length:** 18–22 seconds  
**Filename:** `BR16-payer-ops-activator.mov`

**Open:** `PayerOpsActivator`.

**Actions:**

1. Establish the artifact title.
2. Show the connected Eventhouse source.
3. Show the three event types:
   - fraud alert
   - high-cost alert
   - care-gap alert
4. Pause on the state/activation status.
5. Do not activate rules or send test email during recording.

**Correlates with:** Scored payer signals become prioritized operational actions.

---

### BR21 — Payer scoring, worklist, and agents

**Target length:** 35–45 seconds  
**Filename:** `BR21-payer-scoring-worklist-agents.mov`

**Open:** `docs/phase-7-payer-rti-ops.md`, `phase-7/deploy-payer-rti.ps1`, the claim emulator, then Fabric/Eventhouse and payer-agent surfaces.

**Actions:**

1. Show the documented payer RTI flow and the claim-emulator entry point.
2. Pause on KQL/function deployment for fraud, high-cost, and care-gap scoring.
3. In Eventhouse, show `claims_events`, `fraud_scores`, `highcost_alerts`, and `care_gap_alerts` without exposing sensitive rows.
4. Show the unified Payer Ops worklist.
5. Show the payer triage/Operations Agent and healthcare graph-agent shell if available.
6. Do not submit agent prompts or trigger alerts during recording.

**Correlates with:** Real-time claim events become explainable, prioritized operational work across fraud, cost, and quality.


---

### BR17 — Repository scope tour

**Target length:** 35–45 seconds  
**Filename:** `BR17-repository-tour.mov`

**Open:** Repository explorer at the root.

**Actions:**

1. Begin with the root collapsed enough to be readable.
2. Reveal, in order:
   - `vendor/microsoft-hds/1.4.0/`
   - `hds-source/`
   - `Deploy-All.ps1`
   - `orchestrator/` and `orchestrator-ui/`
   - `phase-1/` and the FHIR/DICOM/Synthea loaders
   - `deploy-fabric-rti.ps1` and `fabric-rti/`
   - `phase-2/`
   - `docs/phase-3-imaging-and-cohorting.md`
   - `phase-4/`, `phase-5/`, and `phase-7/`
   - `state-tracking/`, `Teardown-All.ps1`, and `cleanup/`
3. Do not open every file. The goal is an architectural map, not a directory recital.

**Correlates with:** The accelerator covers deployment, ingestion, intelligence, operations, validation, and lifecycle.

---

### BR18 — Orchestrator preflight and plan

**Target length:** 30–40 seconds  
**Filename:** `BR18-orchestrator-preflight-plan.mov`

**Open:** Local HLS Data Accelerator Orchestrator.

**Actions:**

1. Show the Preflight tab with readiness checks.
2. Move to Deploy and choose **Full platform** only for visual configuration; do not start a deployment.
3. Scroll through the phase selections.
4. Show **Preview resources** and the deployment graph if available.
5. End with the complete ordered deployment plan visible.

**Correlates with:** The demo begins with preflight and executes each dependency in a deliberate order.

---

### BR19 — Orchestrator monitor and validation

**Target length:** 25–30 seconds  
**Filename:** `BR19-orchestrator-monitor.mov`

**Open:** A completed deployment run in the Orchestrator History/Monitor page.

**Actions:**

1. Open a completed run.
2. Show phase progression and elapsed durations.
3. Pause on HDS deployment, pipeline gates, reporting, and payer RTI.
4. Show resource verification/results.
5. End on the completed status without starting, retrying, canceling, or deleting anything.

**Correlates with:** A green check is backed by validation of the deployed artifacts and data contract.

## Optional pickup recordings

### PU01 — Local payload validation

Record a terminal running the non-cloud payload-validation command. Show successful package, wheel, and required-file checks. Avoid tokens and environment variables.

### PU02 — State tracking and resume

Show a deployment-state JSON file, then the Orchestrator resume/repair controls. Do not launch a repair.

### PU03 — Teardown preview

Show the resource scanner, matched Azure/Fabric resources, and locks. Do not execute teardown.

### PU04 — Ontology

Show `ClinicalDeviceOntology` or `DevicePayerOntology`, the entity graph, and relationships. Do not edit or publish.

## Recording order

Record in this order to minimize context switching:

1. BR01–BR02 — public Microsoft pages
2. BR03–BR05, BR08, BR13, BR17, BR20, and BR21 — repository/code
3. BR06–BR07, BR09–BR12, and BR14–BR16, plus the Fabric portions of BR20–BR21 — Fabric
4. BR18–BR19 — local Orchestrator
5. PU01–PU04 — pickups only if the corresponding surface is healthy

## Final handoff checklist

- Every filename uses the exact name above.
- No clip begins or ends during pointer movement.
- No whole-slide zoom, crop, or Ken Burns treatment.
- Browser zoom remains 100%.
- Synthetic-data disclaimers are visible where required.
- No Fabric capacity errors, loading spinners, failed refresh banners, secrets, or real patient data appear in the selected take.
- Keep the raw recordings; do not bake titles, music, or narration into them.

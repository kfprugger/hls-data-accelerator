# HDS Explainer — Recording-Ready B-Roll Script

This is the performable visual script. The companion outline remains in `docs/b-roll-recording-script.md`.

## How to record each take

- Record silently. The existing A-roll is the spoken track.
- Record at 2560×1440, 30 fps or higher; browser zoom stays at 100%.
- Use Microsoft Edge — Work / BrakeKat for authenticated Fabric footage.
- Hide bookmarks, downloads, notifications, personal tabs, tenant alerts, and unrelated browser chrome.
- Never show access tokens, connection strings, email addresses, resource credentials, or patient identifiers.
- Use only synthetic patients and demonstration data.
- Start and end every take with a motionless three-second handle.
- Follow each timecoded direction once. Do not improvise extra scrolling or cursor circles.
- Preserve the full frame. No whole-frame zoom, crop, Ken Burns, or digital push-in.
- Stop and restart the take if a tooltip, notification, loading error, secret, or real patient identifier appears.

## Required takes

### BR01 — Microsoft delivery-model announcement

**Save as:** `BR01-microsoft-transition-notice.mov`  
**Record length:** 20 seconds  
**Open before recording:** [Microsoft Learn — Get started with healthcare data solutions](https://learn.microsoft.com/en-us/industry/healthcare/healthcare-data-solutions/get-started)  
**A-roll cue:** Microsoft moved HDS to a downloadable, customer-managed source package.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:06 | Begin on the page title and the complete **Important** notice. |
| 00:06–00:09 | Pause on **August 3, 2026**. |
| 00:09–00:11 | Move the pointer to **October 1, 2026** and pause. |
| 00:11–00:14 | Move to **December 31, 2027** and pause. |
| 00:14–00:17 | Finish on the **Microsoft Download Center** link without clicking it. |
| 00:17–00:20 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR02 — Microsoft Download Center package

**Save as:** `BR02-hds-download-center.mov`  
**Record length:** 18 seconds  
**Open before recording:** Microsoft Download Center entry linked from the Learn notice.  
**A-roll cue:** This is a real software and documentation package, not another portal checklist.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:06 | Establish the product title: **Healthcare data solutions in Microsoft Fabric**. |
| 00:06–00:09 | Show the version and published information. |
| 00:09–00:12 | Scroll once to the package/download details. |
| 00:12–00:15 | Pause on the Download control and package description. |
| 00:15–00:18 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Do not start a download during the recording.

---

### BR03 — HDS 1.4.0 package contents

**Save as:** `BR03-hds-package-contents.mov`  
**Record length:** 28 seconds  
**Open before recording:** Repository explorer at `vendor/microsoft-hds/1.4.0/`.  
**A-roll cue:** The package contains HDS source, DTT source, deployment and transition guidance, samples, configuration, and Microsoft license terms.  
**Spoken track:** None.

**Accuracy line:** Call it **source-available**, not open source.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Start with the `1.4.0` folder collapsed. |
| 00:07–00:10 | Expand it once. |
| 00:10–00:14 | Highlight `HDS.SourceCode/` and `DTT.SourceCode/`. |
| 00:14–00:18 | Highlight `Deployment Guide.docx`, `Transition Guide.docx`, and `Microsoft License Terms.txt`. |
| 00:18–00:21 | Expand `HDS.SourceCode/src/tools/sampleData/`. |
| 00:21–00:25 | End on `HDS.SourceCode/src/config/` and its reference/configuration content. |
| 00:25–00:28 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Call it **source-available**, not open source.

---

### BR04 — Old portal-managed workflow

**Save as:** `BR04-old-portal-workflow.mov`  
**Record length:** 28 seconds  
**Open before recording:** Legacy `med-device-fabric-emulator` repository.  
**A-roll cue:** Automate, stop, configure HDS manually, then restart automation.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Show `fabric-rti/HDS-SETUP-GUIDE.md` and the two-phase flow. |
| 00:07–00:12 | Scroll to the point where automation stops for portal work. |
| 00:12–00:16 | Show `docs/phase-1-infrastructure-and-ingestion.md`, Step 4. |
| 00:16–00:21 | Pause on the manual environment/package configuration. |
| 00:21–00:25 | End on the instruction to return to the scripts for the next phase. |
| 00:25–00:28 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR05 — New source-driven deployment code

**Save as:** `BR05-new-source-deployment.mov`  
**Record length:** 32 seconds  
**Open before recording:** `hls-data-accelerator` repository.  
**A-roll cue:** Validate, build, upload, deploy, and verify as one engineered flow.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Show `hds-source/Deploy-HdsSource.ps1` at the deployment entry point. |
| 00:07–00:12 | Search within the file for payload validation and pause on the matching block. |
| 00:12–00:16 | Show the HDS/DTT wheel build and OneLake upload steps. |
| 00:16–00:20 | Open `orchestrator/activities/deploy_hds_source.py`. |
| 00:20–00:25 | Pause on the dependency-stage execution and validation logic. |
| 00:25–00:29 | End on the expected artifact validation contract in `fabric-rti/HDS-SETUP-GUIDE.md`. |
| 00:29–00:32 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR06 — Live HDS workspace inventory

**Save as:** `BR06-live-hds-workspace.mov`  
**Record length:** 20 seconds  
**Open before recording:** Fabric workspace `med-0803`.  
**A-roll cue:** The deployment creates a complete, inspectable Fabric artifact contract.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Begin at the workspace root in list view. |
| 00:07–00:10 | Show the folders for deployment notebooks, pipelines, Real-Time, reports/semantic models, and validation notebooks. |
| 00:10–00:13 | Scroll slowly enough to reveal the deployed lakehouses and ontology artifacts. |
| 00:13–00:17 | End with the workspace name visible. |
| 00:17–00:20 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR07 — Deployed HDS pipelines

**Save as:** `BR07-live-hds-pipelines.mov`  
**Record length:** 25 seconds  
**Open before recording:** `med-0803` → `Pipelines`.  
**A-roll cue:** Clinical, imaging, claims, CMA, OMOP, and SDoH are deployed together.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:09 | Establish the breadcrumb `med-0803 > Pipelines`. |
| 00:09–00:16 | Slowly scroll through: clinical FHIR export and ingestion; claims ingestion; imaging ingestion; CMA transformation; OMOP analytics; SDoH ingestion; |
| 00:16–00:22 | Pause briefly on each group; do not open or run a pipeline. |
| 00:22–00:25 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR08 — End-to-end architecture walkthrough

**Save as:** `BR08-architecture-walkthrough.mov`  
**Record length:** 28 seconds  
**Open before recording:** `Project_Architecture_Blueprint.md` and `docs/images/Simple Diagram.png`.  
**A-roll cue:** One connected MedTech, provider, and payer data journey.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Start with the whole architecture visible. |
| 00:07–00:10 | Point to Synthea/FHIR inputs. |
| 00:10–00:14 | Move to TCIA/DICOM. |
| 00:14–00:18 | Move to Masimo device telemetry and Event Hub/Eventstream. |
| 00:18–00:21 | Trace into OneLake/Eventhouse and Bronze–Silver–Gold. |
| 00:21–00:25 | Finish on Power BI, Data Agents, ontology, Activator, and operational actions. |
| 00:25–00:28 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR09 — Patient 360 Data Agent

**Save as:** `BR09-patient-360-agent.mov`  
**Record length:** 20 seconds  
**Open before recording:** `Patient 360` in Fabric.  
**A-roll cue:** HDS data supports governed, conversational patient analytics.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:06 | Establish the `Patient 360` title. |
| 00:06–00:09 | Show the Explorer pane with the connected lakehouses. |
| 00:09–00:11 | Pause on a visible example query such as average patient age. |
| 00:11–00:14 | Show the generated-answer and code areas without submitting a new query. |
| 00:14–00:17 | End with the data-source list visible. |
| 00:17–00:20 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR10 — Imaging report and OHIF path

**Save as:** `BR10-imaging-report-ohif.mov`  
**Record length:** 22 seconds  
**Open before recording:** `ImagingReport`, then the OHIF viewer if it is healthy.  
**A-roll cue:** DICOM ingestion leads to cohorting, reporting, and image review.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Show the imaging overview page and study/file counts. |
| 00:07–00:11 | Pause on modality distribution and the studies table. |
| 00:11–00:15 | Select one synthetic study only if it is safe and responsive. |
| 00:15–00:19 | Cut to the OHIF study viewer and show image-series navigation. |
| 00:19–00:22 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Do not reveal real patient data.

---

### BR11 — Claims and quality report inventory

**Save as:** `BR11-claims-report-inventory.mov`  
**Record length:** 20 seconds  
**Open before recording:** `med-0803` → `Reports and Semantic Models`.  
**A-roll cue:** Claims and quality are deployed as first-class reporting artifacts.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Establish the breadcrumb and workspace. |
| 00:07–00:10 | Pause on **Population Health & Quality Dashboard**. |
| 00:10–00:13 | Show its semantic model beside the report. |
| 00:13–00:17 | Show the CMA and imaging reports for platform breadth. |
| 00:17–00:20 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Do not open a report if Fabric displays a capacity-unavailable error.

---

### BR12 — Population Health and Quality report

**Save as:** `BR12-population-health-quality-report.mov`  
**Record length:** 40 seconds  
**Open before recording:** `med-0803` → `Reports and Semantic Models` → `Population Health & Quality Dashboard`.  
**A-roll cue:** Claims, quality, adherence, risk, cost, and utilization in one model.  
**Spoken track:** None.

**Gate:** Record only if the report opens without an error.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:06 | Establish the report title and hold on Quality Overview. |
| 00:06–00:10 | Switch to Claims Analytics, then hold the completed page. |
| 00:10–00:14 | Switch to Medication Adherence, then hold the completed page. |
| 00:14–00:18 | Switch to Care Gap Closure, then hold the completed page. |
| 00:18–00:22 | Switch to Payer Performance, then hold the completed page. |
| 00:22–00:25 | Switch to Star Rating, then hold the completed page. |
| 00:25–00:28 | Switch to Risk Adjustment, then hold the completed page. |
| 00:28–00:31 | Switch to Readmission Risk, then hold the completed page. |
| 00:31–00:37 | Switch to Utilization Overview and hold it long enough to read. |
| 00:37–00:40 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Do not scroll rapidly or hover long enough to trigger distracting tooltips.

---

### BR20 — Claims materialization and Gold tables

**Save as:** `BR20-claims-materialization-gold.mov`  
**Record length:** 32 seconds  
**Open before recording:** `docs/phase-5-cms-quality-and-claims.md`, `phase-5/materialize_claims_quality.py`, then the reporting Gold lakehouse in Fabric.  
**A-roll cue:** The accelerator materializes a 23-table reporting model before Power BI turns it into ten analytical pages.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:09 | Show the claims-and-quality architecture and expected outputs in the phase document. |
| 00:09–00:16 | Open `materialize_claims_quality.py` and pause on the Gold-table definitions/materialization flow. |
| 00:16–00:23 | In Fabric, show the Gold table inventory, including claims, diagnosis, quality, adherence, care-gap, HCC/RAF, readmission, and utilization outputs. |
| 00:23–00:29 | Keep the table list readable; do not expose row-level patient identifiers. |
| 00:29–00:32 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR13 — SDoH seed and CMA context

**Save as:** `BR13-sdoh-cma.mov`  
**Record length:** 28 seconds  
**Open before recording:** `phase-2/seed_cma_sdoh.py`, then Fabric CMA tables.  
**A-roll cue:** The deterministic synthetic SDoH seed enriches Care Management Analytics without presenting demonstration values as real epidemiology.  
**Spoken track:** None.

**Accuracy line:** These are deterministic synthetic demonstration indicators—not live epidemiology or real patient risk scores.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Pause on the Atlanta ZIP-to-FIPS mapping. |
| 00:07–00:12 | Show the deterministic seed logic. |
| 00:12–00:16 | Highlight the source banner stating the values are synthetic. |
| 00:16–00:21 | Show the category and measure definitions. |
| 00:21–00:25 | In Fabric, show the CMA Gold lakehouse tables created by the seed. |
| 00:25–00:28 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- These are deterministic synthetic demonstration indicators—not live epidemiology or real patient risk scores.

---

### BR14 — Claims Eventstream

**Save as:** `BR14-claims-eventstream.mov`  
**Record length:** 22 seconds  
**Open before recording:** `med-0803` → `Real-Time` → `ClaimsRTIStream`.  
**A-roll cue:** Claims use a dedicated real-time stream separate from device telemetry.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:06 | Establish the Eventstream title. |
| 00:06–00:09 | Show the claim Event Hub source. |
| 00:09–00:13 | Trace the connection through `ClaimsRTIStream`. |
| 00:13–00:17 | Finish on the Eventhouse destination. |
| 00:17–00:19 | If a safe data preview is available, show it briefly. Otherwise, keep holding the destination. Never imply that an inactive source is streaming. |
| 00:19–00:22 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- If data preview is available, show it briefly; do not imply that an inactive source is currently streaming.

---

### BR15 — Payer real-time artifact inventory

**Save as:** `BR15-payer-realtime-artifacts.mov`  
**Record length:** 20 seconds  
**Open before recording:** `med-0803` → `Real-Time`.  
**A-roll cue:** Clinical telemetry and payer operations coexist while retaining separate streams.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Slowly show `ClaimsRTIStream`. |
| 00:07–00:10 | Show `PayerOpsActivator`. |
| 00:10–00:13 | Show the clinical alert artifacts and Masimo telemetry artifacts for contrast. |
| 00:13–00:17 | Keep the workspace and folder names visible. |
| 00:17–00:20 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR16 — Payer Ops Activator

**Save as:** `BR16-payer-ops-activator.mov`  
**Record length:** 20 seconds  
**Open before recording:** `PayerOpsActivator`.  
**A-roll cue:** Scored payer signals become prioritized operational actions.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Establish the artifact title. |
| 00:07–00:10 | Show the connected Eventhouse source. |
| 00:10–00:13 | Show the three event types: fraud alert; high-cost alert; care-gap alert; |
| 00:13–00:17 | Pause on the state/activation status. |
| 00:17–00:20 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Do not activate rules or send test email during recording.

---

### BR21 — Payer scoring, worklist, and agents

**Save as:** `BR21-payer-scoring-worklist-agents.mov`  
**Record length:** 40 seconds  
**Open before recording:** `docs/phase-7-payer-rti-ops.md`, `phase-7/deploy-payer-rti.ps1`, the claim emulator, then Fabric/Eventhouse and payer-agent surfaces.  
**A-roll cue:** Real-time claim events become explainable, prioritized operational work across fraud, cost, and quality.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:10 | Show the documented payer RTI flow and the claim-emulator entry point. |
| 00:10–00:17 | Pause on KQL/function deployment for fraud, high-cost, and care-gap scoring. |
| 00:17–00:23 | In Eventhouse, show `claims_events`, `fraud_scores`, `highcost_alerts`, and `care_gap_alerts` without exposing sensitive rows. |
| 00:23–00:30 | Show the unified Payer Ops worklist. |
| 00:30–00:37 | Show the payer triage/Operations Agent and healthcare graph-agent shell if available. |
| 00:37–00:40 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Do not submit agent prompts or trigger alerts during recording.

---

### BR17 — Repository scope tour

**Save as:** `BR17-repository-tour.mov`  
**Record length:** 40 seconds  
**Open before recording:** Repository explorer at the root.  
**A-roll cue:** The accelerator covers deployment, ingestion, intelligence, operations, validation, and lifecycle.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:20 | Begin with the root collapsed enough to be readable. |
| 00:20–00:37 | Reveal, in order: `vendor/microsoft-hds/1.4.0/`; `hds-source/`; `Deploy-All.ps1`; `orchestrator/` and `orchestrator-ui/`; `phase-1/` and the FHIR/DICOM/Synthea loaders; `deploy-fabric-rti.ps1` and `fabric-rti/`; `phase-2/`; `docs/phase-3-imaging-and-cohorting.md`; `phase-4/`, `phase-5/`, and `phase-7/`; `state-tracking/`, `Teardown-All.ps1`, and `cleanup/`; |
| 00:37–00:40 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Do not open every file. The goal is an architectural map, not a directory recital.

---

### BR18 — Orchestrator preflight and plan

**Save as:** `BR18-orchestrator-preflight-plan.mov`  
**Record length:** 35 seconds  
**Open before recording:** Local HLS Data Accelerator Orchestrator.  
**A-roll cue:** The demo begins with preflight and executes each dependency in a deliberate order.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:09 | Show the Preflight tab with readiness checks. |
| 00:09–00:15 | Move to Deploy and choose **Full platform** only for visual configuration; do not start a deployment. |
| 00:15–00:20 | Scroll through the phase selections. |
| 00:20–00:26 | Show **Preview resources** and the deployment graph if available. |
| 00:26–00:32 | End with the complete ordered deployment plan visible. |
| 00:32–00:35 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

### BR19 — Orchestrator monitor and validation

**Save as:** `BR19-orchestrator-monitor.mov`  
**Record length:** 28 seconds  
**Open before recording:** A completed deployment run in the Orchestrator History/Monitor page.  
**A-roll cue:** A green check is backed by validation of the deployed artifacts and data contract.  
**Spoken track:** None.

| Time | Perform exactly this action |
|---|---|
| 00:00–00:03 | Hold the opening composition. Cursor parked. No movement. |
| 00:03–00:07 | Open a completed run. |
| 00:07–00:12 | Show phase progression and elapsed durations. |
| 00:12–00:16 | Pause on HDS deployment, pipeline gates, reporting, and payer RTI. |
| 00:16–00:21 | Show resource verification/results. |
| 00:21–00:25 | End on the completed status without starting, retrying, canceling, or deleting anything. |
| 00:25–00:28 | Hold the final composition. Cursor parked. No movement. |

**Take notes:**
- Keep every label readable and avoid opening, running, publishing, or modifying anything.

---

## Optional pickups

- **PU01 — Local payload validation:** Record one clean successful validation run with secrets and environment variables hidden.
- **PU02 — State tracking and resume:** Show a state JSON file, then the resume/repair controls without launching a repair.
- **PU03 — Teardown preview:** Show the resource scanner, matched resources, and locks without executing teardown.
- **PU04 — Ontology:** Show an ontology graph and relationships without editing or publishing.

## Final check before handing off footage

- Filenames match this script exactly.
- Every take includes clean three-second handles.
- No narration is baked into B-roll.
- No whole-frame zoom or crop is applied.
- No errors, secrets, notifications, or real patient information are visible.
- Keep the raw recordings.

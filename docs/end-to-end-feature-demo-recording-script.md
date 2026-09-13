# HLS Data Accelerator — End-to-End Feature Demo Script

**Target runtime:** 18:10; hard stop at 20:00  
**Reference deployment:** Fabric workspace `med-0906`; Azure resource group `rg-med-0906`; completed run `P1234567-20260906-120121`  
**Audience:** healthcare data, analytics, clinical, payer, and platform stakeholders  
**Recording style:** live narration while clicking; short holds after each navigation

## What is new versus core HDS

Use these labels only as your mental map; do not repeat the label before every sentence.

- **NEW — deployment and operations:** the browser orchestrator, preflight, HDS 1.4 source validation/build/deployment, dependency-aware monitoring, runtime validation, continuation, and teardown.
- **CORE HDS:** Admin, Bronze, Silver, Gold OMOP, Gold CMA, POA Gold, Customer Insights, the Microsoft HDS pipelines, and the CMA/POA semantic models and reports.
- **ACCELERATOR EXTENSIONS:** Azure synthetic FHIR/DICOM/device inputs, clinical RTI, imaging cohorting and OHIF, ontologies, Data Agents, and clinical Activator.
- **NEW — population and payer:** the reporting Gold model, Population Health & Quality Dashboard, CMS/HEDIS/Star/HCC/readmission/utilization analytics, claims RTI, payer scoring, payer agents, and payer Activator.

## Current recording gates — not spoken

Before recording `med-0906`, verify the actual report and live-data surfaces, not only item presence:

1. **Population Health & Quality report:** the canonical report now has five integrated pages and 46 visuals. Use the original `Population Health & Quality Dashboard` entry; its report ID is preserved. Confirm every page renders, not just its KPI cards.
2. **Telemetry and Claims:** start both emulator producers and use the test harness's **Resume from Now** policy to skip queued telemetry history. Require all source/stream/destination nodes to be Running **and** recent events in both destination tables before evaluating or recording reports. A historical row count or Running topology alone does not prove live data.

The environment is not a full pass while these evaluation gaps remain:

- POA appointment, journey, and marketing-event rows are empty and its appointment-date visual needs refresh; patient and encounter dimensions are populated, but the outreach report does not pass.
- The Healthcare Graph Agent's ontology query path fails. An error explanation is not a successful answer.
- HealthcareOpsAgent conversational behavior has not been verified through a supported external API.
- Other report and Data Agent checks must use meaningful data-backed results; do not promote a sparse or nonexistent-patient response into a blanket pass.

Before recording:

- Use **Edge — Work — Brakekat**.
- Set browser zoom to 100%; use the report’s **Fit to page** control where needed.
- Pre-open the local orchestrator, Fabric workspace `med-0906`, the report folder, Real-Time folder, Agents folder, and one synthetic OHIF study.
- Run the evaluation harness readiness gate for both telemetry producers and Eventstreams; confirm fresh destination events before describing dashboards as live.
- Open every report and agent response once before recording. Never troubleshoot on camera.
- Keep synthetic summary views on screen. Do not expose patient identifiers, secrets, connection strings, tenant IDs, subscription IDs, or environment variables.
- Do not start a deployment, pipeline, refresh, alert, or teardown during the recording.

---

## 0:00–0:35 — Open: from deployment to outcomes

**Screen**

1. Start on the orchestrator **Preflight** page.
2. Keep the product title and **Ready for Deployment** status visible.

**Say**

> This is the HLS Data Accelerator, an end-to-end deployment and demonstration environment for Microsoft Healthcare Data Solutions in Fabric.
>
> I’m going to start with the deployment experience, then follow the data through the core HDS lakehouses and pipelines, and finish with the newer clinical, imaging, population-health, and payer features built on top. The important part is that this is one connected solution—not a collection of screenshots assembled after the fact.

**Transition:** click **Deploy**.

---

## 0:35–1:55 — NEW: deployment portal and full-platform plan

**Screen**

1. On **Deploy**, click **Full platform**. Do not enter or submit a deployment name.
2. Hold on the profile buttons: Demo, Full platform, Scaffolding, Infra only, Resume/repair, and Data pipeline only.
3. Scroll through the enabled components. Pause on:
   - Azure Synthetic Data Foundation
   - FHIR Service + Data Loading
   - DICOM Download + Upload
   - Fabric RTI
   - HDS Bridge + Row Gates
   - Imaging Toolkit
   - Ontology + Agent Binding
   - Population Health & Quality Dashboard
   - Payer RTI & Ops

**Say**

> The orchestrator turns the whole platform into an explicit deployment plan. Preflight checks Azure CLI, Az PowerShell, tenant and subscription alignment, Fabric capacity discovery, and local prerequisites before anything changes in the cloud.
>
> From here I can choose a fast demo, the full platform, infrastructure only, a zero-data scaffold, a data-only run, or a targeted resume and repair. The full plan exposes each major capability as a deliberate component: synthetic clinical data, FHIR, DICOM, real-time telemetry, HDS, imaging, ontology, agents, alerts, population health, and payer operations.
>
> That makes the deployment repeatable and reviewable. It also makes failures recoverable instead of forcing a complete rebuild.

**Transition:** click **History**, search for `med-0906`, and open the completed run.

---

## 1:55–3:20 — NEW: completed run, HDS source deployment, and validation

**Screen**

1. Show **7/7 phases complete**, the 87-minute timeline, zero errors, and the completed cloud state.
2. Pause on **Live validation passed: 44 checks**.
3. Expand **HDS Source Deployment** and show:
   - HDS 1.4 and DTT payload validation
   - deployment lakehouse and OneLake upload
   - environment publication
   - bootstrap and validation notebooks
   - managed lakehouses and deployment stages
   - final artifact contract

**Say**

> This is the completed `med-0906` run. The monitor maps the work into seven customer-facing phases, preserves the individual substeps, and shows where the time was actually spent. This run completed all seven phases in about eighty-seven minutes and then passed forty-four live validation checks.
>
> The biggest change from the older HDS experience is here. HDS version 1.4 is now deployed from Microsoft’s source-available package as part of the run. The accelerator validates the HDS and Data Transformation Toolkit payloads, builds and uploads the artifacts, publishes the Fabric environment, imports the deployment and validation notebooks, runs the Microsoft deployment stages, and verifies the resulting contract.
>
> The result is not “the API call returned green.” The result is a checked inventory of lakehouses, notebooks, pipelines, semantic models, reports, and runtime data.

**Transition:** switch to the root of Fabric workspace `med-0906`.

---

## 3:20–4:10 — Fabric workspace: the complete solution surface

**Screen**

1. Show the workspace name and description.
2. Scan the folders: **Agents**, **Notebooks**, **Pipelines**, **Real-Time**, and **Reports and Semantic Models**.
3. Pause on the two ontologies and `deployment_lakehouse`.

**Say**

> Here is the deployed workspace. It contains the Microsoft HDS estate and the accelerator extensions in one Fabric boundary: lakehouses, pipelines, notebooks, Eventhouse, Eventstreams, KQL dashboards, reports, semantic models, Data Agents, ontologies, Operations Agent, and Activator items.
>
> The deployment lakehouse is the staging and build surface for the HDS source package. The `healthcare1` items are the operational HDS data products. The named folders keep the demo surfaces easy to navigate without hiding the underlying Fabric artifacts.

**Transition:** filter or navigate to **Lakehouse** items.

---

## 4:10–5:40 — CORE HDS: Bronze, Silver, and Gold data products

**Screen**

1. Open `healthcare1_msft_bronze` and show the FHIR export and DICOM shortcut areas at folder level only.
2. Open `healthcare1_msft_silver` and show the table inventory: Patient, Encounter, Condition, Observation, MedicationRequest, Device, DeviceAssociation or Basic, and ImagingStudy.
3. Return to the workspace and point to:
   - `healthcare1_msft_admin`
   - `healthcare1_msft_gold_omop`
   - `healthcare1_msft_gold_cma`
   - `healthcare1_msft_poa_gold`
   - `healthcare1_msft_customer_insights`
   - `healthcare1_reporting_gold`

**Say**

> This is the core HDS medallion architecture.
>
> Bronze is the landing layer. OneLake shortcuts expose the FHIR export and DICOM files from Azure storage without making another unnecessary copy of the source data.
>
> Silver is the governed healthcare layer. FHIR resources and imaging metadata are normalized into Delta tables such as Patient, Encounter, Condition, Observation, MedicationRequest, Device, DeviceAssociation, and ImagingStudy.
>
> From there, HDS provides purpose-built Gold layers. OMOP supports research and portable cohort analytics. CMA supports care management. POA supports patient outreach. Customer Insights supports downstream engagement scenarios.
>
> The accelerator adds `healthcare1_reporting_gold`, which organizes HDS outputs for imaging, claims, quality, risk, and utilization analytics.

**Transition:** open the **Pipelines** folder.

---

## 5:40–6:35 — CORE HDS: dependency-aware pipelines

**Screen**

Scroll through the twelve deployed pipelines. Pause on:

- `healthcare1_msft_clinical_data_foundation_ingestion`
- `healthcare1_msft_cma`
- `healthcare1_msft_imaging_with_clinical_foundation_ingestion`
- `healthcare1_msft_omop_analytics`
- `healthcare1_msft_poa_ingestion`
- `healthcare1_msft_claims_data_ingestion`
- `healthcare1_msft_sdoh_ingestion`

Do not run a pipeline.

**Say**

> These pipelines turn the lakehouses into an operating data platform. Clinical ingestion creates the Silver foundation. Imaging follows clinical so studies can join back to patients and conditions. CMA and POA create their focused analytical products, and OMOP creates the common research model.
>
> Claims and SDoH are sidecars when those inputs are present. The orchestrator runs the dependencies in a safe order and checks row-level readiness between stages. An item existing in the workspace is not the same thing as a usable data product, so those data gates matter.

**Transition:** open the **Real-Time** folder.

---

## 6:35–7:40 — ACCELERATOR: clinical real-time intelligence

**Screen**

1. Open `MasimoTelemetryStream`.
2. If both nodes are Running, trace Event Hub source → Eventstream → Eventhouse destination and show a recent preview.
3. Open `Masimo Patient Monitoring`, then `Clinical Alerts Map`.
4. Show summary visuals only.

**Say when both nodes are Running and recent data is visible**

> The batch HDS path is paired with a live clinical telemetry path. Simulated Masimo Radius-7 devices send oxygen saturation, pulse rate, perfusion, and signal data through Event Hubs. `MasimoTelemetryStream` routes those events into the Fabric Eventhouse with low latency.
>
> KQL turns the raw readings into current-device views, alert history, and enriched clinical alerts. The monitoring dashboard shows the operational state, while the alert map resolves a device back to its synthetic patient and location using the governed HDS context.

**Say instead if either node is Paused**

> This is the configured clinical telemetry path from Event Hubs through the Fabric Eventstream into the Eventhouse. The source or destination is currently paused, so I’m showing the deployed topology and historical analytical state rather than calling it a live feed.

**Transition:** open the **Agents** folder.

---

## 7:40–8:50 — ACCELERATOR: patient and clinical Data Agents

**Screen**

1. Open **Patient 360** and show a pre-validated response to: `Show a full Patient 360 for a respiratory patient with active telemetry.`
2. Open **Clinical Triage** and show a pre-validated response to: `Run a clinical triage and identify the highest-priority devices and their patients.`
3. Keep the generated query and connected sources visible.

**Say**

> Patient 360 and Clinical Triage combine the HDS Silver lakehouse with real-time KQL data.
>
> Patient 360 starts with one synthetic person or device and assembles demographics, conditions, medications, encounters, device assignment, and the latest telemetry into a longitudinal view.
>
> Clinical Triage starts from the operational side. It scans current alerts, ranks the highest-priority devices, and resolves each device back to the patient and clinical history.
>
> The generated query and governed data source remain visible. The value is not a free-form chatbot answer; it is a conversational layer over the same authoritative lakehouse and Eventhouse data.

**Transition:** open **HDS Multi-Layer Imaging Cohort Agent**.

---

## 8:50–10:05 — ACCELERATOR: imaging cohorting, reporting, and OHIF

**Screen**

1. Show a pre-validated Cohort Agent response to: `Find patients with COPD who also have chest CT imaging.`
2. Open **ImagingReport** and show modality, body-part, patient-condition linkage, and the study table.
3. Select one synthetic study and open its OHIF deep link.
4. Scroll through a few CT slices, then return to Fabric.

**Say**

> Imaging adds another clinical modality to the same patient journey.
>
> The Cohort Agent can combine Silver FHIR and Gold OMOP to find a population that meets clinical and imaging criteria without requiring the user to hand-author a multi-table join.
>
> ImagingReport uses the reporting Gold layer to summarize studies by modality and body part and link them back to patients and conditions. Each synthetic study includes a deep link into OHIF.
>
> The viewer retrieves the selected DICOM series through a managed-identity DICOMweb proxy from the Bronze OneLake shortcut. The same study is available for cohort discovery, analytics, and image review without maintaining a second image estate.

**Transition:** return to the workspace root and open `ClinicalDeviceOntology`.

---

## 10:05–11:05 — ACCELERATOR: ontology and clinical activation

**Screen**

1. In `ClinicalDeviceOntology`, show Patient, Device, Encounter, Condition, `MedRequest`, Observation, ImagingStudy, `DeviceAssoc`, and DeviceTelemetry.
2. Briefly open `DevicePayerOntology` and show the separate payer entities.
3. Open `ClinicalAlertActivator`; show configuration only. Do not trigger it.

**Say**

> Fabric IQ adds a governed semantic map over the physical data stores.
>
> `ClinicalDeviceOntology` connects patients, encounters, conditions, medications, imaging studies, devices, device associations, and time-series telemetry. `DevicePayerOntology` keeps claims, payer, diagnosis, adherence, care-gap, risk, and high-cost semantics in a separate governed domain.
>
> The ontologies do not replace the lakehouses or Eventhouse. They give agents explicit entities and relationships grounded in those systems.
>
> `ClinicalAlertActivator` completes the action path. It reads the enriched urgent and critical alert function, keys events by device, and can route a governed notification to the configured care team without embedding alert logic in the dashboard.

**Transition:** open `healthcare1_reporting_gold`.

---

## 11:05–12:20 — NEW: claims, quality, risk, and utilization model

**Screen**

Show the table inventory in logical groups:

- claims: `dim_payer`, `dim_diagnosis`, `fact_claim`, `fact_diagnosis`
- quality and adherence: `agg_quality_measures`, `agg_quality_summary`, `agg_medication_adherence`, `care_gaps`
- Star Ratings: `star_rating_detail`, `star_rating_simulation`
- HCC/RAF: `dim_hcc`, `fact_patient_hcc`, `agg_risk_scores`, `revenue_opportunity`
- readmission: `readmission_risk_scores`, `readmission_risk_summary`, `readmission_model_performance`
- utilization: `agg_utilization_summary`, `agg_utilization_by_payer`, `agg_cost_by_category`, `agg_high_cost_claimants`, `agg_condition_pmpm`

**Say**

> Claims are now first-class data in both the longitudinal and real-time sides of the solution.
>
> Synthea generates Coverage, Claim, and Explanation of Benefit resources. Those resources follow the same FHIR export, Bronze, and Silver path as the clinical data. A materialization notebook then creates this twenty-three-table reporting model in Gold.
>
> The model includes claim facts, payer and diagnosis dimensions, seven CMS electronic clinical quality measures, three HEDIS medication-adherence classes, open care gaps, Star Rating simulations, CMS-HCC version 28 risk adjustment, thirty-day readmission risk, and cost and utilization analytics.
>
> Payer category stays in the analytical grain so Medicare, Medicaid, Commercial, and Uninsured populations can be compared consistently.

**Transition:** open **Reports and Semantic Models → Population Health & Quality Dashboard**.

---

## 12:20–15:05 — NEW: Population Health & Quality Dashboard

**Gate:** record this chapter only after all five pages render their analytical visuals with meaningful data. A page shell, single count card, or successful model metadata query is not sufficient.

**Screen**

Advance one page at a time, pausing six to eight seconds on each:

1. Executive Overview
2. Quality & Care Gaps
3. Claims & Payer Performance
4. Stars & Risk Adjustment
5. Readmission & Utilization

Finish on `ReadmissionRiskAlert` configuration. Do not trigger the alert.

**Say**

> This is the new Population Health and Quality experience, delivered through a Direct Lake semantic model.
>
> Executive Overview brings quality, population, claims, care gaps, RAF, and readmission indicators together with payer comparisons and risk distribution.
>
> Quality and Care Gaps combines measure performance, an adherence indicator, gap breakdowns, and an actionable patient-level detail table. Claims and Payer Performance places billed, paid, and denial indicators alongside claim-status and claim-type charts and a claim-detail table.
>
> Stars and Risk Adjustment brings together per-measure ratings, RAF scores, risk distribution, demographic comparisons, and revenue opportunity. Readmission and Utilization combines encounter risk, PMPM, inpatient utilization, emergency visits, and a monthly cost trend.
>
> The demo readmission-rate and revenue-opportunity indicators can include explicitly labeled synthetic markers in sparse cohorts. They demonstrate the workflow; they are not observed clinical outcomes.
>
> `ReadmissionRiskAlert` can turn the High-risk population into a scheduled daily digest that directs a care team back to the governed report. One model now connects quality, claims, adherence, risk, revenue, and utilization.

**Fallback if the report is still blank**

- Show the five-page rail briefly without presenting unloaded visuals as working.
- Return to `healthcare1_reporting_gold` and the Population Health & Quality semantic model.
- Say: `The integrated report is deployed, but its live data or rendering gate is failing in this session. I’ll show the governed source tables instead of presenting an empty canvas as a functioning report.`
- Skip directly to the next chapter.

**Transition:** return to **Reports and Semantic Models**.

---

## 15:05–15:55 — CORE HDS plus extension: CMA, POA, and SDoH

**Screen**

1. Show `healthcare1_msft_cma_report` and its semantic model.
2. Show `healthcare1_msft_poa_report` and its semantic model.
3. Open `healthcare1_msft_gold_cma` and show the SDoH table names. Keep the synthetic-data context visible.

**Say**

> The new population-health report does not replace the existing HDS analytical products.
>
> Care Management Analytics combines patient, location, care-plan, utilization, and cost context. The accelerator adds deterministic synthetic SDoH data—ZIP-to-FIPS mapping, categories, measures, and source metadata—so the care-management path can demonstrate non-clinical context without presenting synthetic values as real epidemiology.
>
> Patient Outreach Analytics remains a separate Gold model and report for segmentation and outreach prioritization. These are core HDS capabilities operating beside the newer claims and quality model.

**Transition:** open `ClaimsRTIStream`.

---

## 15:55–17:25 — NEW: payer RTI, scoring, agents, and Activator

**Screen**

1. If both nodes are Running, trace claim Event Hub → `ClaimsRTIStream` → Eventhouse and show recent `claims_events`.
2. Show `fraud_scores`, `highcost_alerts`, `care_gap_alerts`, and `fn_PayerOpsWorklist`.
3. Open **Payer Ops Triage** and show a pre-validated summary.
4. Briefly show `HealthcareOpsAgent`, `Healthcare Graph Agent`, and `PayerOpsActivator` configuration.

**Say when both nodes are Running and recent data is visible**

> The longitudinal claims model explains population performance. This separate real-time path looks for payer events while they are developing.
>
> `ClaimsRTIStream` sends claim events into the Eventhouse. KQL-native scoring evaluates provider velocity, amount outliers, denial patterns, and upcoding indicators for fraud risk. A second path looks for accelerating thirty- and ninety-day cost trajectories and recent emergency utilization. A third brings open Gold care gaps into the same operational worklist.
>
> Payer Ops Triage gives the analyst a conversational view over that worklist and the Gold claims context. HealthcareOpsAgent provides the broader operational shell, while Healthcare Graph Agent can reason across the payer ontology and current KQL context.
>
> `PayerOpsActivator` turns high-priority fraud, high-cost, and care-gap events into governed triggers. The report explains performance, KQL detects emerging conditions, the agents help investigate, and Activator moves the finding toward action.

**Say instead if either node is Paused**

> This is the deployed payer topology and its historical scored worklist. The Eventstream source or destination is paused, so I’m not describing the current view as live. The scoring functions, agents, and Activator remain deployed, but a live demonstration starts only after both topology nodes are Running and recent claim events are verified.

**Transition:** return to the orchestrator completed run.

---

## 17:25–18:10 — Close: one governed lifecycle

**Screen**

1. Hold on the seven completed phases and **Live validation passed: 44 checks**.
2. Briefly show the deployed-resource panel or History.
3. End on the workspace link or full architecture view. Do not open Teardown controls during the final sentence.

**Say**

> The end-to-end story is the lifecycle connecting all of these features.
>
> Azure provides the FHIR, DICOM, telemetry, and claims ingestion edge. HDS standardizes the longitudinal healthcare data in Fabric. OneLake and Eventhouse support batch and real-time analysis without unnecessary copies. Reports, agents, ontologies, OHIF, and Activator turn that governed foundation into clinical, care-management, population-health, and payer workflows.
>
> The orchestrator makes the platform deployable, observable, recoverable, and removable as one solution. That is the difference between a feature demo and an environment a platform team can actually operate.

**End:** hold for three seconds.

---

## Hard-stop cut list

If navigation or Fabric rendering pushes the recording past 18:30, cut in this order:

1. Shorten the pipeline chapter by 20 seconds; show names without opening a pipeline.
2. Combine the two ontology items into one 25-second scan.
3. Mention POA while the CMA report folder is visible; do not open POA.
4. In the CMS report, show Executive Overview, Claims & Payer Performance, and Readmission & Utilization; summarize Quality & Care Gaps and Stars & Risk Adjustment while the five-page rail is visible.
5. Never cut the orchestrator, core HDS lakehouses, CMS model, or payer end state. Those are the backbone of the story.

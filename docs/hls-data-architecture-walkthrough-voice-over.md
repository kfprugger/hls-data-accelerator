# HLS Data Architecture — Screen-Recording Walkthrough and Voice-Over Script

## Purpose

A guided walkthrough of the deployed HLS Data Accelerator: Azure infrastructure first, then the Microsoft Healthcare Data Solutions data foundation in Fabric, followed by real-time intelligence, agents, imaging, ontology, reports, claims, SDoH, quality, and payer operations.

**Target length:** 18–22 minutes  
**Reference deployment:** `med-0903` in Fabric and `rg-med-0903` in Azure. Replace those names if recording a newer deployment.  
**Audience:** healthcare data, analytics, clinical, payer, and platform stakeholders.

## Recording rules

- Use Microsoft Edge with the **Work — BrakeKat** profile for authenticated Azure and Fabric footage.
- Record at 2560×1440, 30 fps or higher. Keep browser zoom at 100%.
- Use only synthetic demonstration data. Never expose real patient data, email addresses, access tokens, connection strings, secrets, tenant identifiers, or subscription identifiers.
- Collapse or crop portal fields that reveal IDs. Keep resource names and architecture labels visible.
- Begin and end each chapter with a two- to three-second still frame.
- Move the pointer deliberately. Avoid rapid scrolling, unnecessary hover tooltips, and opening edit experiences.
- Do not start deployments, pipelines, alerts, refreshes, or teardown actions during the recording.
- Before recording, confirm the Fabric capacity is active, both Eventstreams are running, the reports render, the OHIF viewer opens, and any agent response you plan to show completes successfully.
- Never describe a feed as “live” unless its Fabric preview or Eventhouse query shows recent events.
- Pronunciation: use **A-H-D-S** for Azure Health Data Services and **H-D-S** for Healthcare Data Solutions in Microsoft Fabric.

## Recommended recording order

| Chapter | Surface | Approx. time |
|---|---|---:|
| 1 | Azure resource group overview | 1:15 |
| 2 | Azure clinical, imaging, and streaming data plane | 1:45 |
| 3 | Fabric workspace and HDS deployment contract | 1:15 |
| 4 | Core HDS data stores | 1:45 |
| 5 | HDS ingestion and transformation pipelines | 1:15 |
| 6 | Clinical real-time intelligence | 1:20 |
| 7 | Patient and clinical Data Agents | 1:30 |
| 8 | Imaging, cohorting, and OHIF | 1:30 |
| 9 | Fabric IQ ontologies | 1:15 |
| 10 | Clinical Data Activator | 0:50 |
| 11 | Claims and quality data model | 1:30 |
| 12 | Population Health & Quality report | 2:00 |
| 13 | SDoH and Care Management Analytics | 1:20 |
| 14 | Patient Outreach Analytics | 0:45 |
| 15 | Payer real-time intelligence | 1:45 |
| 16 | Payer agents and operational activation | 1:15 |
| 17 | Orchestrator, validation, and lifecycle | 1:15 |
| 18 | Closing architecture view | 0:40 |

---

## Chapter 1 — Azure resource group overview

### Screen recording

- Open **Azure portal → Resource groups → `rg-med-0903`**.
- Use the resource list view, grouped or sorted by type.
- Slowly reveal the Event Hubs namespace, Azure Container Registry, Key Vault, storage account, Azure Health Data Services workspace, FHIR service, managed identity, and container groups.
- Do not open Key Vault secrets or show endpoint keys.

### Voice-over

> We’ll start with the Azure foundation. The accelerator deploys the solution into a single resource group so the data plane, identities, emulators, and lifecycle are easy to discover and manage together.
>
> At the center are Azure Event Hubs for streaming, Azure Container Registry for the solution images, Key Vault for protected configuration, an ADLS Gen2 storage account, an Azure Health Data Services workspace with a FHIR R4 service, and managed identities for service-to-service access.
>
> The containerized workloads generate and load synthetic healthcare data, simulate Masimo device telemetry, prepare DICOM imaging, and generate the payer claim stream. The important architectural point is that these workloads authenticate with managed identity and role-based access rather than credentials embedded in code.

### Transition

- Select the Event Hubs namespace.
- Let the page settle before continuing.

---

## Chapter 2 — Azure clinical, imaging, and streaming data plane

### Screen recording

1. In the Event Hubs namespace, show **Entities → Event Hubs** with:
   - `telemetry-stream`
   - `claim-stream`
2. Open the storage account and show only the container names:
   - `synthea-output`
   - `fhir-export`
   - `dicom-output`
3. Return to the resource group and point to:
   - the Azure Health Data Services workspace and FHIR service
   - `synthea-generator-job`
   - `fhir-loader-job`
   - `dicom-loader-job`
   - `masimo-emulator-grp`
   - `claim-emulator-grp`
4. If available in the imaging resource group, briefly show the OHIF Static Web App and DICOMweb proxy Container App. Do not open environment variables.

### Voice-over

> There are four primary data journeys entering the platform.
>
> First, Synthea produces deterministic synthetic patient histories. Those FHIR R4 bundles are staged in `synthea-output`, loaded into the FHIR service, and exported as NDJSON into `fhir-export`. The sample includes demographics, encounters, conditions, observations, medications, immunizations, procedures, coverage, claims, and explanations of benefit.
>
> Second, the DICOM loader downloads public chest-imaging studies, replaces identifying metadata with matching synthetic patient identifiers while preserving the image pixels, writes the files to `dicom-output`, and creates linked FHIR ImagingStudy resources.
>
> Third, `telemetry-stream` carries Masimo pulse-oximeter readings. Fourth, `claim-stream` carries payer claim events. Those streaming paths remain intentionally separate, with separate Fabric Eventstreams preserving each schema and keeping clinical telemetry distinct from payer operations.
>
> The imaging experience adds an OHIF Static Web App and a managed-identity DICOMweb proxy. The proxy reads images from OneLake only when a user opens a study, so the viewer does not require a second copy of the DICOM files.

### Transition

- Switch from Azure portal to the Fabric workspace `med-0903`.
- Start at the workspace root in list view.

---

## Chapter 3 — Fabric workspace and the HDS deployment contract

### Screen recording

- Show the Fabric workspace name and capacity state.
- Slowly scan the workspace folders or item list for:
  - deployment and validation notebooks
  - pipelines
  - lakehouses
  - Eventhouse and Eventstreams
  - reports and semantic models
  - Data Agents
  - ontology and Reflex items
- Pause on `deployment_lakehouse` and the published `healthcare1_msft_environment` if visible.

### Voice-over

> Azure provides the ingestion edge; Microsoft Fabric is the unified analytics and intelligence plane.
>
> This workspace is not a hand-built demo. The accelerator validates and deploys Microsoft Healthcare Data Solutions version 1.4 from the source-available Microsoft package. It builds and stages the HDS and Data Transformation Toolkit artifacts, publishes the Fabric environment, imports deployment and validation notebooks, runs the master deployer, and then verifies the expected artifact contract.
>
> That contract includes the lakehouses, pipelines, notebooks, semantic models, reports, and environment required by the rest of the architecture. The deployment lakehouse is the technical staging area; the `healthcare1` items are the operational HDS estate.

---

## Chapter 4 — Core HDS data stores

### Screen recording

- Filter the workspace to **Lakehouse** items.
- Pause on each store in this order:
  1. `healthcare1_msft_admin`
  2. `healthcare1_msft_bronze`
  3. `healthcare1_msft_silver`
  4. `healthcare1_msft_gold_omop`
  5. `healthcare1_msft_gold_cma`
  6. `healthcare1_msft_poa_gold`
  7. `healthcare1_msft_customer_insights`
  8. `healthcare1_reporting_gold`
- Open Bronze and show the `FHIR-HDS` and DICOM shortcut paths without exposing file-level patient identifiers.
- Open Silver and show the table list, including Patient, Encounter, Condition, Observation, MedicationRequest, Device, Basic or DeviceAssociation, and ImagingStudy.
- Open Gold OMOP and show only the table inventory.

### Voice-over

> The HDS data foundation follows a medallion pattern, but each store has a distinct job.
>
> The Admin lakehouse carries configuration and operational metadata. Bronze is the landing layer. Its OneLake shortcuts point to the FHIR export and DICOM files in ADLS Gen2, so Fabric can use those assets without copying them into another storage system.
>
> Silver is the normalized healthcare layer. This is where FHIR clinical resources and imaging metadata become governed Delta tables such as Patient, Encounter, Condition, Observation, MedicationRequest, Device, DeviceAssociation, and ImagingStudy.
>
> Gold OMOP transforms that clinical foundation into the OMOP common data model for research, cohorting, and portable analytics. Gold CMA supports Care Management Analytics. POA Gold supports Patient Outreach Analytics, and Customer Insights supports additional HDS solution data.
>
> `healthcare1_reporting_gold` is the accelerator’s reporting layer. It joins HDS outputs into models optimized for the Imaging report and the newer claims, quality, risk, and utilization experiences.

---

## Chapter 5 — HDS ingestion and transformation pipelines

### Screen recording

- Switch the workspace filter to **Data pipeline**.
- Scroll slowly through these pipeline groups and pause on their latest successful runs where available:
  - `healthcare1_msft_sdoh_ingestion`
  - `healthcare1_msft_claims_data_ingestion`
  - `healthcare1_msft_clinical_data_foundation_ingestion`
  - `healthcare1_msft_cma`
  - `healthcare1_msft_imaging_with_clinical_foundation_ingestion`
  - `healthcare1_msft_omop_analytics`
  - `healthcare1_msft_poa_ingestion`
- Do not start or rerun a pipeline.

### Voice-over

> These pipelines turn the storage layers into an operating healthcare data platform.
>
> Optional SDoH and claims sidecars can run first when their source data is present. The clinical foundation pipeline then transforms the FHIR export into Silver. Patient Outreach Analytics runs to completion so its semantic model has data. CMA consumes the prepared clinical layer without blocking Imaging or OMOP. Imaging follows clinical so studies can be joined to patients and conditions, and OMOP runs after the clinical and imaging foundations are ready.
>
> The deployment enforces this order and verifies row-level readiness between stages. That matters because a pipeline item existing in the workspace is not the same as a populated, queryable data product.

---

## Chapter 6 — Clinical real-time intelligence

### Screen recording

1. Open **Real-Time → `MasimoTelemetryStream`**.
2. Trace `telemetry-stream` through the Eventstream to the Eventhouse destination.
3. Open the Eventhouse/KQL database and show:
   - `TelemetryRaw`
   - `AlertHistory`
   - functions such as `fn_LatestReadings`, `fn_DeviceStatus`, `fn_ClinicalAlerts`, and `fn_AlertLocationMap`
4. Open the real-time dashboard and move through:
   - active devices
   - active alerts
   - SpO2 and pulse-rate trends
   - device status and latest readings
   - alert-location map

### Voice-over

> The clinical real-time path starts with simulated Masimo Radius-7 devices. Each reading carries SpO2, pulse rate, perfusion index, and related signal data into Event Hubs. `MasimoTelemetryStream` routes those events into the Fabric Eventhouse with low latency.
>
> `TelemetryRaw` preserves the incoming stream. KQL functions convert it into the latest reading, device status, trend, and alert views. `AlertHistory` retains detected clinical events, and the enrichment functions join the device stream back to the patient, condition, encounter, and location context in Silver.
>
> The dashboard turns that into an operational view: which devices are online, which patients are crossing warning, urgent, or critical thresholds, how their vitals are trending, and where those alerts are occurring.

---

## Chapter 7 — Patient and clinical Data Agents

### Screen recording

- Open **Patient 360**.
- Show its KQL and Silver Lakehouse data sources.
- Display a pre-validated synthetic response to: `Show a full Patient 360 for a respiratory patient with active telemetry.`
- Open **Clinical Triage**.
- Display a pre-validated response to: `Run a clinical triage and identify the highest-priority devices and their patients.`
- Keep generated SQL/KQL visible briefly to show grounding. Do not expose row-level identifiers outside the synthetic demo.

### Voice-over

> The first two Data Agents federate across real-time KQL data and the HDS Silver Lakehouse.
>
> Patient 360 starts with a person or device and assembles the synthetic patient’s demographics, conditions, medications, encounters, assigned device, latest vitals, and device status. It is designed for a focused, longitudinal view.
>
> Clinical Triage starts from the opposite direction. It scans the alert stream, ranks urgent situations, and then resolves each device back to the affected patient and clinical history. One agent answers, “Tell me about this patient.” The other answers, “What needs attention right now?”
>
> The generated query is visible alongside the answer, so users can see which governed source was used rather than receiving an ungrounded response.

---

## Chapter 8 — Imaging, cohorting, and OHIF

### Screen recording

1. Open the **HDS Multi-Layer Imaging Cohort Agent**.
2. Show a pre-validated answer to: `Find patients with COPD who also have chest CT imaging.`
3. Open **ImagingReport** and show:
   - study count
   - modality and body-part distributions
   - patient and condition linkage
   - study table with viewer links
4. Select one synthetic study and open its OHIF deep link.
5. In OHIF, scroll through a few CT slices, then return to the report.

### Voice-over

> Imaging adds a third clinical modality to the same patient journey.
>
> The Cohorting Agent queries Silver FHIR and Gold OMOP to find populations that meet clinical and imaging criteria. A user can ask for patients with COPD and chest CTs without hand-authoring a multi-table join.
>
> The Direct Lake Imaging report materializes study, patient, condition, and OMOP cross-references in `healthcare1_reporting_gold`. It shows the imaging population by modality and body part and provides a deep link for each synthetic study.
>
> That link opens the OHIF viewer. The DICOMweb proxy retrieves the selected series from the Bronze OneLake shortcut on demand. The same study is therefore available for analytics, cohort discovery, and image review without duplicating the image estate.

---

## Chapter 9 — Fabric IQ ontologies

### Screen recording

- Open `ClinicalDeviceOntology`.
- Show the deployed clinical entities: Patient, Device, Encounter, Condition, `MedRequest`, Observation, ImagingStudy, `DeviceAssoc`, and DeviceTelemetry.
- Open `DevicePayerOntology` and show its Gold entities: Claim, Payer, Diagnosis, PatientDiagnosis, `MedAdherence`, `CareGap`, `PatientRisk`, and `HighCostClaimant`.
- Use Preview/graph only if it is already materialized and healthy. Do not refresh or publish during recording.

### Voice-over

> Fabric IQ adds governed semantic maps across these physical stores while keeping clinical and payer reasoning intentionally separate.
>
> `ClinicalDeviceOntology` connects Patient, Encounter, Condition, Observation, `MedRequest`, ImagingStudy, Device, `DeviceAssoc`, and real-time DeviceTelemetry. `MedRequest` and `DeviceAssoc` are the deployed ontology labels for MedicationRequest and DeviceAssociation. Static clinical entities are bound to Silver, while telemetry is time-series data in the Eventhouse. Clinical alerts remain in the KQL and Data Activator path because the current automated ontology import excludes the AlertHistory binding.
>
> `DevicePayerOntology` adds the Gold claims and quality context through Claim, Payer, Diagnosis, PatientDiagnosis, `MedAdherence`, `CareGap`, `PatientRisk`, and `HighCostClaimant`. Clinical agents bind to the clinical-device ontology; payer and graph agents bind to the payer ontology.
>
> These ontologies do not replace the Lakehouse or Eventhouse. They give each agent a governed vocabulary and explicit relationships while keeping the underlying queries grounded in the authoritative data stores.

---

## Chapter 10 — Clinical Data Activator

### Screen recording

- Open `ClinicalAlertActivator`.
- Show the `fn_ClinicalAlerts` source, Device object, urgent/critical KQL filter, polling interval, and email action.
- Show configuration only. Do not activate a rule or send a test alert.

### Voice-over

> Analytics becomes action through Fabric Data Activator.
>
> `ClinicalAlertActivator` polls the enriched clinical-alert function on the configured interval, using that same interval as the function’s lookback window. Its KQL source keeps urgent and critical synthetic events, keys them by device, and exposes the patient name, device, SpO2, pulse rate, alert tier, and clinical message to the rule.
>
> The EventTrigger is configured for every event returned by that filtered source. The result is a governed path from telemetry to clinical context to operational notification.

---

## Chapter 11 — Claims and quality data model

### Screen recording

- Return to Silver and show `ExplanationOfBenefit`, `Coverage`, and other claim-related FHIR tables.
- Open `healthcare1_reporting_gold` and show the table inventory grouped visually into:
  - claims and diagnosis: `dim_payer`, `dim_diagnosis`, `fact_claim`, `fact_diagnosis`
  - quality and adherence: `agg_quality_measures`, `agg_quality_summary`, `agg_medication_adherence`, `care_gaps`
  - Star Ratings: `star_rating_detail`, `star_rating_simulation`
  - HCC/RAF: `dim_hcc`, `fact_patient_hcc`, `agg_risk_scores`, `agg_risk_summary`, `revenue_opportunity`
  - readmission: `readmission_risk_scores`, `readmission_risk_summary`, `readmission_model_performance`
  - utilization: `agg_utilization_summary`, `agg_utilization_by_payer`, `agg_cost_by_category`, `agg_high_cost_claimants`, `agg_condition_pmpm`
- Keep the view at schema/table level; do not show patient identifiers.

### Voice-over

> Claims are now first-class data in both the longitudinal and real-time sides of the platform.
>
> On the longitudinal side, Synthea generates Coverage, Claim, and ExplanationOfBenefit resources. They follow the same governed FHIR export, Bronze, and Silver path as the clinical data. A materialization notebook then builds a twenty-three-table reporting model in Gold.
>
> That model includes claim facts, payer and diagnosis dimensions, seven CMS electronic clinical quality measures, three HEDIS medication-adherence measures, open care gaps, Star Rating simulations, CMS-HCC version 28 risk adjustment, thirty-day readmission risk, and cost and utilization analytics.
>
> Payer category is carried into the claims and quality aggregates so Medicare, Medicaid, Commercial, and Uninsured populations can be compared consistently across the report.

---

## Chapter 12 — Population Health & Quality report

### Screen recording

- Open **Population Health & Quality Dashboard** only after confirming it renders without errors.
- Advance one page at a time and pause long enough to read:
  1. Executive Overview
  2. Quality & Care Gaps
  3. Claims & Payer Performance
  4. Stars & Risk Adjustment
  5. Readmission & Utilization
- Use synthetic summary visuals. Avoid patient-detail tables unless identifiers are masked.
- After the report, open `ReadmissionRiskAlert` and show its `readmission_risk_scores` source, High-risk filter, daily 8:00 AM Eastern schedule, and email action. Do not trigger it.

### Voice-over

> The Population Health and Quality Dashboard presents those Gold tables through a Direct Lake semantic model.
>
> Executive Overview combines quality, population, claims, care-gap, RAF, and readmission indicators with payer comparisons and risk distribution. Quality and Care Gaps adds measure performance, adherence, gap breakdowns, and an actionable detail table.
>
> Claims and Payer Performance combines billed, paid, and denial indicators with claim-type and status breakdowns. Stars and Risk Adjustment brings together measure ratings, RAF scores, risk distribution, demographic comparisons, and revenue opportunity.
>
> Readmission and Utilization combines encounter risk, PMPM, inpatient utilization, emergency visits, and a monthly cost trend. Sparse-cohort demo markers are explicitly labeled and must not be presented as observed clinical outcomes.
>
> When an alert email is configured, `ReadmissionRiskAlert` reads the High-risk rows from `readmission_risk_scores` and schedules a daily 8:00 AM Eastern digest that directs the care team back to the report.
>
> This is one governed model spanning quality, claims, adherence, risk, revenue, and utilization—not a collection of disconnected reports.

---

## Chapter 13 — SDoH and Care Management Analytics

### Screen recording

1. Open `healthcare1_msft_gold_cma` and show these tables if populated:
   - `zip_to_fips_mapping`
   - `sdoh_category`
   - `sdoh_unitofmeasure`
   - `sdoh_datasetmetadata`
   - `sdoh_fips`
   - `social_determinant`
2. Open `healthcare1_msft_cma_report` and show care-management views that use patient, location, cost, care-plan, and SDoH context.
3. Keep the synthetic-data banner or documentation statement visible when introducing the SDoH values.

### Voice-over

> Social determinants of health enrich the Care Management Analytics layer.
>
> For this demonstration, the accelerator maps synthetic Atlanta ZIP codes to county FIPS codes and creates deterministic example indicators for economic stability, healthcare access and quality, and neighborhood and built environment.
>
> The measures include synthetic household-income, poverty, food-access, non-metro, environmental-exposure, and rehospitalization indicators. These values are deterministic demonstration data. They are not live epidemiology and must not be presented as real patient or community risk scores.
>
> HDS combines that geographic context with patient location, care plans, utilization, and cost in Gold CMA. The Care Management Analytics report then gives care managers another lens for identifying where non-clinical context may affect outreach and intervention planning.

---

## Chapter 14 — Patient Outreach Analytics

### Screen recording

- Show `healthcare1_msft_poa_gold`.
- Open `healthcare1_msft_poa_report` if its latest pipeline run populated the model and the report renders.
- Show summary outreach segments or campaign/worklist views only. Do not claim populated outreach results if the model is empty.

### Voice-over

> HDS also includes Patient Outreach Analytics.
>
> POA uses the prepared clinical and analytical layers to support outreach segmentation and prioritization. It has its own Gold lakehouse, semantic model, report, and downstream ingestion pipeline, which keeps outreach workloads distinct from the core clinical transformation.
>
> This is the engagement side of the architecture: moving from what happened clinically to which synthetic populations may need targeted follow-up.

---

## Chapter 15 — Payer real-time intelligence

### Screen recording

1. Open **Real-Time → `ClaimsRTIStream`**.
2. Trace `claim-stream` to the Eventhouse destination.
3. In the Eventhouse, show:
   - `claims_events`
   - `adt_events`
   - `rx_events`
   - `fraud_scores`
   - `highcost_alerts`
   - `care_gap_alerts`
4. Show results from pre-run, read-only queries for:
   - `fn_FraudRisk(60)`
   - `fn_HighCostTrajectory(90)`
   - `fn_CareGapOnAlert(60)`
   - `fn_PayerOpsWorklist(60)`
5. Keep claim and patient identifiers masked or off-screen.

### Voice-over

> The longitudinal claims model answers retrospective and population questions. Phase Seven adds a separate real-time payer-operations path.
>
> `ClaimsRTIStream` sends claim events into the Eventhouse alongside optional admission, discharge, transfer, and pharmacy event schemas. KQL-native scoring evaluates provider velocity, amount outliers, denial patterns, and upcoding indicators for fraud risk.
>
> A second function looks for accelerating thirty- and ninety-day cost trajectories and recent emergency utilization. A third surfaces open rows from the Gold care-gap table as alert-shaped worklist items when that table is available.
>
> `fn_PayerOpsWorklist` unions the highest-priority fraud, high-cost, and care-gap signals into one operational queue. The scoring remains explainable because the contributing flags, trends, amounts, and priority are available with each synthetic event.

---

## Chapter 16 — Payer agents and operational activation

### Screen recording

- Open `PayerOpsActivator` and show its Eventhouse source and three alert domains: fraud, high cost, and care gap.
- Open **Payer Ops Triage** and show a pre-validated summary of the highest-priority worklist items.
- Show `HealthcareOpsAgent` if the tenant supports Operations Agent; otherwise show the deployed Data Agent fallback.
- Show **Healthcare Graph Agent** only if its `DevicePayerOntology` datasource is attached and its staged definition is published.
- Do not activate rules, submit untested prompts, or send email.

### Voice-over

> The payer worklist is consumed in two ways.
>
> `PayerOpsActivator` converts high-priority fraud, high-cost, and care-gap events into operational triggers. Payer Ops Triage gives an analyst a conversational view over the same worklist and the Gold claims context.
>
> When the tenant supports Fabric Operations Agent, `HealthcareOpsAgent` provides a unified operational triage experience; otherwise the deployment uses a Data Agent fallback. `DevicePayerOntology` supplies the patient, device, diagnosis, claim, payer, care-gap, risk, high-cost, and telemetry graph semantics. The agent’s separate KQL datasource supplies current clinical-alert and payer-event context.
>
> Together, the report explains population performance, real-time KQL identifies emerging events, agents help investigate them, and Activator moves the highest-priority findings toward action.

---

## Chapter 17 — Orchestrator, validation, and lifecycle

### Screen recording

1. Open the local HLS Data Accelerator Orchestrator.
2. Show **Preflight** and its readiness categories without running remediation.
3. Open **Deploy** and select **Full platform** only to reveal the plan; do not submit.
4. Show the component switches for clinical data, imaging, HDS, ontology, agents, quality, payer RTI, and Activators.
5. Open **History**, select the completed `med-0903` run, and show:
   - phase cards and elapsed time
   - HDS pipeline substeps
   - deployed-resource results
   - post-deployment validation
6. Briefly show continuation/recovery, reseed, scaffolding-only, and teardown controls without executing them.

### Voice-over

> The accelerator wraps the architecture in a repeatable deployment and operations experience.
>
> Preflight checks local tooling, Azure identity and subscription alignment, Fabric capacity discovery, permissions, and required paths before cloud mutation begins. The deployment wizard supports a full platform, smaller demo paths, infrastructure-only deployment, a zero-data scaffolding mode, component repair, patient reuse, and authoritative synthetic-data reseeding.
>
> During execution, the monitor streams logs and maps them to the Azure, HDS, imaging, ontology, agent, Activator, quality, and payer phases. State is persisted so a failed run can continue from completed work instead of rebuilding the entire platform.
>
> Completion includes artifact and runtime checks—not only green deployment calls. The same interface keeps deployment history and provides resource discovery, locking, partial teardown, and full teardown for controlled lifecycle management.

---

## Chapter 18 — Closing architecture view

### Screen recording

- Return to the full architecture diagram.
- Trace one final path with the pointer:
  - Azure FHIR, DICOM, telemetry, and claims inputs
  - OneLake Bronze, Silver, OMOP/CMA/reporting Gold, and Eventhouse
  - dashboards, reports, agents, ontology, OHIF, and Activators
- End on the entire diagram and hold for three seconds.

### Voice-over

> The HLS Data Accelerator connects four healthcare data domains in one architecture: clinical FHIR, medical imaging, device telemetry, and payer claims.
>
> Azure handles secure ingestion and source services. Healthcare Data Solutions standardizes and enriches the data in Fabric. OneLake and Eventhouse support batch and real-time analysis without unnecessary copies. Reports, Data Agents, ontology, imaging, and Activator turn that foundation into clinical, care-management, population-health, and payer workflows.
>
> The newer claims, SDoH, quality, risk, and payer real-time capabilities are not separate demos. They use the same governed patients, identifiers, storage layers, and deployment lifecycle as the core HDS platform.

---

## Pre-recording health gates

Use these gates immediately before recording. Omit a live-result sentence rather than narrating a feature as healthy when its surface is empty or unavailable.

| Surface | Required check before recording |
|---|---|
| Azure | Expected resources exist; do not expose secrets or configuration values. |
| FHIR and storage | Synthetic resources and expected container names are present. |
| `MasimoTelemetryStream` | Source and destination nodes show Running; recent events exist before saying “live.” |
| `ClaimsRTIStream` | Source and destination nodes show Running; recent events exist before saying “live.” |
| HDS lakehouses | Bronze shortcuts resolve; expected Silver and Gold tables are visible. |
| HDS pipelines | Latest relevant runs succeeded; sidecar no-op states are described accurately. |
| Data Agents | Definition is staged/published and the exact demonstration prompt succeeds. |
| Ontology | Bindings exist; show graph Preview only if materialized. |
| Imaging | ImagingReport renders; proxy health reports studies; one synthetic OHIF link opens. |
| CMA report | Semantic model connects to the current workspace’s Gold CMA endpoint and visuals render. |
| POA report | Ingestion has run and the report is not wholly blank. |
| Population Health & Quality | Direct Lake model is queryable and all ten pages render. |
| Activators | Items and rules exist; do not trigger email during recording. |
| Payer RTI | Worklist functions return current synthetic rows before showing results. |
| Orchestrator | Use a completed run for History/Monitor footage; do not deploy or tear down while recording. |

## Short version: five-minute cut

If a shorter edit is needed, keep these chapters:

1. Azure resource group and the two Event Hubs.
2. HDS Bronze, Silver, Gold OMOP, Gold CMA, and reporting Gold.
3. Clinical real-time dashboard plus Patient 360.
4. ImagingReport plus OHIF.
5. Population Health & Quality pages for Claims, Care Gaps, RAF, Readmission, and Utilization.
6. SDoH tables plus CMA.
7. ClaimsRTIStream, Payer Ops worklist, agent, and Activator.
8. Closing architecture diagram.

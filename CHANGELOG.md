# Changelog

## [Unreleased] — May 28, 2026

### Health Command Center Fabric App
- **Added** [`rayfin-health-command-center/`](rayfin-health-command-center/), a Rayfin Fabric App that serves payer, provider, and medtech operations from one surface. A controlled sync reads the Direct Lake models over `healthcare1_reporting_gold`, masks identifiers, and writes the app's own MSSQL snapshot; the dashboard renders from that database rather than querying a model on every mount.
- **Added** three lenses over the shared Gold layer: payer claims economics with collection/denial rates, PMPM, revenue at risk and the highest-cost members; provider quality with open care gaps, RAF, readmission risk tiers and a CMS Stars gauge; and medtech imaging throughput with modality mix and DICOM instance volume.
- **Fixed** the line-of-business split to use the per-segment measures instead of grouping by `dim_payer[payer_category]`, which returns the grand total for every category because the claim-to-payer relationship is unusable in that model and would have shown identical numbers per segment.
- **Added** an explicit disconnected state: Fabric SSO is required for the protected app database and Gold sync, so a standalone browser names the reason and blanks every figure rather than rendering zeroes that read as real business results.
- **Added** the app's own Rayfin MSSQL database as the serving layer: `KpiSnapshot`, `SeriesPoint`, `WorklistRow` and `SyncRun` entities, all `@authenticated('*')`, applied to the deployed item through `rayfin up db apply`. The dashboard reads those tables; `src/lib/sync-gold.ts` is the only module that touches a semantic model, and it masks identifiers before they are written.
- **Added** an automatic first-run sync so a fresh database fills itself from Gold, plus a Sync from Gold control and a `SyncRun` provenance record that reports when the snapshot was captured and what a failure was.
- **Fixed** the template's `rayfin-client.ts`, which read `VITE_RAYFIN_BASE_URL` while `rayfin env` emits `VITE_RAYFIN_API_URL`, and typed the client against `AppSchema` so entity access is checked; also fixed `rayfin/tsconfig.json`, whose inherited `allowImportingTsExtensions` blocked `rayfin up db apply` from compiling the entities.
- **Fixed** the startup authentication race that broke the deployed app: `useSnapshot` queried the authenticated DAB endpoint before Fabric SSO completed, cached the anonymous 401, and never retried when the session arrived. Database reads and the first Gold sync are now gated on `isAuthenticated`, authentication transitions trigger the initial read, and standalone mode never calls the protected database. Two regression tests cover the pre-auth and false-to-true paths.
- **Deployed** to workspace `med-0906` as AppBackend `db1f3f55-4e7e-4b35-9c28-16a79410b64a`, live at `https://oaken-cove-7a1eb21ad7-westus2.webapp.fabricapps.net`, with all ten shipped DAX queries verified against the live models before release.

### Azure Databricks Destination Blueprint
- **Added** a dedicated [`azure-databricks/`](azure-databricks/) architecture and deployment package that preserves the Azure FHIR, ADLS, Event Hubs, ACR, ACI, Key Vault, managed-identity, and OHIF source estate while replacing Fabric as the governed destination.
- **Documented** the clean replacement boundary for Unity Catalog, Lakeflow, Delta medallion tables, Databricks SQL, AI/BI dashboards, Genie Agents, SQL alerts, validation, recovery, cost control, and teardown; explicitly marked Microsoft HDS/DTT deployment artifacts as Fabric-specific rather than falsely portable.
- **Added** three interactive Archify diagrams for the target system architecture, source-to-action data flow, and fail-closed deployment workflow, including showcase validation and browser evidence in light and dark themes.
- **Fixed** the Azure Databricks architecture, data-flow, and deployment-workflow diagrams so every relationship has a distinct source, target, arrowhead, and non-overlapping route.
- **Added** `azure-databricks/implementation/` migration artifacts: a Bicep foundation for the workspace, Access Connector, managed container, and least-privilege RBAC; API-assisted Unity Catalog bootstrap replacing OneLake shortcuts; a bootstrap serverless SQL warehouse; a Declarative Automation Bundle with five schema-scoped Lakeflow pipelines, ordered batch and scheduled stream-to-Gold jobs, and a cooldown-aware clinical alert; fail-closed Silver, Gold, and stream-freshness gate notebooks; and numbered preflight, deploy, run, validate, and ownership-aware teardown scripts.
- **Deployed** the package into the Brakekat `Azure-brakekat` subscription in West US 2 against the live `rg-med-0906` FHIR, ADLS, DICOM manifest, and Event Hubs sources. The live serverless workflow passed Bronze, Silver, stream freshness, Gold, and all 17 post-deployment checks after repairing fresh-workspace warehouse bootstrapping, Unity Catalog read-only location creation, managed Auto Loader state, DICOM-manifest joins, live telemetry/claims schemas, development-name validation, and the stream-before-Gold DAG.
- **Added and deployed** five Azure Databricks Genie Agents matching the Fabric Data Agent domains: Patient 360, Clinical Triage, HDS Multi-Layer Imaging Cohort, Payer Ops Triage, and Healthcare Graph. Each agent is bundle-managed, binds only curated Unity Catalog sources, and carries five reviewed sample questions plus five verified SQL examples.
- **Added** ten governed `agent_*` Gold products for patient/device summaries, current clinical triage, imaging cohorts, FHIR-derived care gaps, streaming fraud risk, high-cost trajectories, payer worklists, cross-domain context, and typed healthcare relationships; expanded Silver claim parsing to retain provider, facility, diagnosis, procedure, geospatial, event-type, and fraud-evidence fields.
- **Verified** all five live Genie conversations against direct Databricks SQL baselines: patient gender 59 female/41 male, 100 devices and 7,218,000 seven-day telemetry events, imaging CR 12/CT 88, 74,297 typed claim events with zero incomplete-schema rows, and 100 patient-device relationships. The destination validator passed 18/18 with no skips.
- **Fixed** five-minute stream scheduling so `max_concurrent_runs: 1` drops overlapping ticks instead of queueing them; the previous queue accumulated stale runs behind serverless startup. Deployment validation now fails on enabled queueing or queued runs.

### Fresh Deployment Reliability
- **Added** a mandatory evaluation-harness gate that starts both Masimo and Claims producers, resumes test Eventstreams from `Now`, and requires fresh generated-and-ingested events before any report, RTI, or agent checks. Stale backlog is reset once; partial pause transitions are awaited before resuming, and failures retain diagnostic JSON without evaluating downstream surfaces.
- **Expanded** the evaluation harness with latest deployment/preflight checks, report-specific data gates, multi-visual page validation, grounded DataAgent and Graph Agent queries, authenticated OperationsAgent evidence, and fresh Edge Work - Brakekat report/OHIF evidence for surfaces APIs cannot prove.
- **Repaired** med-0906 demo coverage with additive provenance-labeled appointments, coverage, PDC medications, SDOH indicators, and outreach events while preserving the 100 patients and ImagingStudies.
- **Fixed** POA DirectQuery date evaluation by projecting `AppointmentCreatedDay` in Power Query, preserved marketing task timestamps in staged HDS IDM configuration, and added deterministic POA demo-event materialization.
- **Populated** ontology companion GraphModels from REST definitions and verified 100 patient-device associations through the published Graph Agent MCP endpoint.
- **Repaired** OperationsAgent goals, instructions, and KQL binding and verified both agents through the dedicated authenticated conversation API without invoking actions; `HealthcareOpsAgent` remains fail-closed because the Fabric preview playbook generator has not produced a playbook.
- **Fixed** both Operations Agents against the GA schema: removed the deprecated `goals` property and the empty `playbook` object the service rejects with "No rule definitions available in the playbook.", bound exactly one `KustoDatabase` knowledge source using the KQL database item id instead of the Eventhouse item id that left `ClinicalDeteriorationMonitor` returning HTTP 500 on `getDefinition`, added a `Recipient` message destination, and replaced the silent DataAgent fallback with a definition read-back that fails closed.
- **Added** the materialized `agent_ops_stream_health` and `agent_deterioration_findings` tables plus their `agent_OperationsStreamHealth()` and `agent_DeteriorationTrend()` functions so the Operations Agent playbook generator can discover physical alert columns instead of inferring them from prose.
- **Populated** the `DeteriorationEscalation` Data Activator via the REST API during deployment, providing its required `agent_deterioration_findings` KQL data source, EventTrigger rule, and email `ActStep` instead of deploying an empty shell requiring manual portal configuration.
- **Hardened** telemetry and claims Eventstream deployment to inspect runtime topology, resume paused sources/destinations from their last checkpoints, and fail if nodes do not reach `Running` within five minutes.
- **Fixed** Microsoft HDS/DTT v1.4.0 staging so optional Azure Monitor telemetry is lazy-loaded, cached wheels are patched and validated deterministically, and offline restaging reuses verified wheel artifacts.
- **Bounded** PowerShell REST calls to prevent network interruptions from leaving deployments alive indefinitely with only quiet-heartbeat output.
- **Fixed** the UI Full preset to keep both clinical and payer Activators enabled, corrected local full-deployment progress to 16 steps and Durable progress to 12 steps, and prevented expected SQL metadata retries from terminating the blocking-error monitor.
- **Automated** Data Agent staging publication through the typed Fabric API after definition updates and ontology rebinding, including corrected payer few-shot schemas.
- **Fixed** Payer Ops Triage and Healthcare Graph Agent table selections by reconciling Fabric-hydrated datasource IDs for both MasimoEventhouse and Reporting Gold, selecting generated ancestors plus six KQL and five Lakehouse tables, republishing, and failing closed unless draft and published definitions agree.
- **Hardened** all five published Data Agents with deterministic KQL grounding for payer claims/high-cost cohorts, current device and clinical aggregates, and imaging modality/status/total counts; removed obsolete payer and stale clinical source bindings and added broad published-MCP regression coverage.
- **Fixed** empty Customer Insights deployments by provisioning the ADLS `main` shortcut, running `healthcare1_msft_customer_insights` serially after core HDS writers, patching the HDS v1.4 Goal mappings to fields present in Silver, and registering populated Delta outputs as Lakehouse tables without blocking the core deployment.
- **Completed** the full report surface by running Patient Outreach Analytics as a required post-Clinical pipeline and validating its terminal job state.
- **Replaced** the invalid readmission-alert payload with a KQL-backed Reflex over the reporting Gold Delta table.
- **Migrated** Data Agent behavioral evaluation from the retired Assistants preview API to each published agent's Fabric MCP endpoint.
- **Scoped** soft-deleted Key Vault purges to the target resource group and moved generated graph-agent instructions out of tracked source paths.
- **Fixed** ontology entity mappings by binding Patient and Device to their Silver projection tables (which do not use change data feed) and pointing all DevicePayerOntology entities at the Gold reporting lakehouse, repairing cross-lakehouse graph-edge hydration failures.
- **Updated** Data Agent bindings to use the dynamically resolved ClinicalDeviceOntology ID and explicitly select its 9 entity types, preventing empty graph queries.
- **Hardened** the Clinical Triage and Payer Ops Triage agents with instructions to correctly interpret zero-count windows and a strict priority rule enforcing raw claim volume queries.
- **Restored** multi-source reasoning in Payer Ops Triage and Healthcare Graph Agent. Gold and `DevicePayerOntology` previously had zero few-shots while both agents shared a KQL-heavy bundle, and the Graph Agent was explicitly told not to call the ontology runtime. Each source now has its own intent boundary and examples: Eventhouse for current signals, Reporting Gold for historical analytics, and ontology-first GQL for relationships and traversal. Mixed questions query sources independently, label each fact, and synthesize only at the answer layer.
- **Triggered** synchronous ontology graph hydration via `RefreshGraph` during deployment instead of requiring manual preview action.

### Canonical Synthetic Healthcare Fixture
- **Added** a deterministic 100-patient canonical FHIR fixture, manifest, checksums, explicit Masimo device assignments, and fail-closed local validator.
- **Hardened** cached loading into an authoritative FHIR replacement with exact bundle/checksum/count validation and fatal Device/Basic association failures.
- **Pinned** patient, quality, PDC, DICOM, and imaging dates to the fixture as-of contract; aligned payer RTI patient IDs to canonical FHIR UUIDs.
- **Fixed** OMOP/CMA reference gates, SDOH keys and visual names, quality semantic-model table coverage, report page visuals, clinical condition enrichment, and payer care-gap worklists.

### CMS Quality Deployment
- **Replaced** the canonical Population Health & Quality Dashboard's ten single-card pages with the five-page, 46-visual integrated layout; removed the separate executive-artifact deployment path while preserving the canonical report identity.
- **Added** a five-page Population Health & Quality Executive Dashboard with 46 KPI, chart, table, and slicer visuals consolidated across quality, claims, payer, stars, risk, readmission, and utilization workflows.
- **Added** deterministic, provenance-labeled sparse-cohort demo markers so revenue opportunity and readmission-rate visuals remain meaningful when randomized synthetic input contains no qualifying cases.
- **Fixed** invalid quality semantic-model TMDL: relationship headers, indentation, Direct Lake expression nesting, and unsupported date-part relationship behavior.
- **Fixed** the quality dashboard PBIR version metadata and Fabric long-running-operation polling so semantic model/report deployment completes reliably.
- **Hardened** completion validation to query the new quality semantic model, verify the dashboard binding, and replace stale retry failures with a successful terminal detail.
- **Fixed** quality materialization for small or sparse cohorts by allowing diagnosis and readmission tables to remain empty when the source contains no qualifying records.

### Existing Deployment Data Reseed
- **Added** an explicit **Reseed and replace data** strategy for existing completed deployments, with a permanent-replacement warning and final patient-total control.
- **Added** an authoritative `reseed_data` contract across the UI, local/Durable orchestrators, PowerShell, Bicep, and FHIR loader; reseeds now clear FHIR and stale exports before rebuilding downstream data.
- **Locked** cached canonical reseeds to their verified 100-patient fixture and kept teardown records ineligible as reseed targets.

### Zero-Data Infrastructure Scaffolding
- **Added** a locked scaffolding-only deployment preset that provisions Azure/Fabric/HDS definitions and agent shells without synthetic patients, DICOM, FHIR exports, HDS ingestion, snapshot materialization, or active data producers.
- **Hardened** local, Durable Functions, PowerShell, and UI paths to enforce the same zero-data contract, stop existing producer containers, preserve HDS source publication, and validate definitions without requiring runtime data.
- **Fixed** clinical/imaging ingest ownership and continuation behavior so explicitly disabled imaging is omitted while a completed DICOM loader can still feed imaging and OMOP on resume.
- **Fixed** scaffolding infrastructure probes leaking Azure CLI's expected “container not found” exit code, eliminating a false failure and unnecessary redeployment after successful ARM provisioning.

### Orchestrator UI, Startup, and HDS Pipeline Visibility
- **Updated** HDS pipeline monitoring/docs to show the default order: optional SDoH/claims sidecars → Clinical → required POA → optional non-blocking CMA → Imaging → OMOP → optional Customer Insights.
- **Fixed** empty Customer Insights deployments by provisioning the `customer-insights` ADLS container, a workspace-identity connection, and the required `Files/main` shortcut before the optional serialized pipeline, then registering every populated `all_entities` Delta output through a bounded repair notebook; Customer Insights failure remains a warning and cannot invalidate completed Clinical, Imaging, or OMOP paths.
- **Added** cheap `/api/live` and default `/api/health` liveness checks, with `/api/health?deep=1` reserved for auth/capacity readiness.
- **Hardened** `Start-WebUI.ps1` startup with `-SelfTest`, session-scoped backend logs, fatal backend/frontend/proxy probes, and BrakeKat Edge/Profile 2 verification guidance.
- **Fixed** successful sidecar summary parsing so continuation runs skip already completed HDS pipelines, and extended Silver imaging SQL synchronization waits to tolerate Fabric endpoint warm-up.

### Deployment Bootstrap
- **Added** automatic bootstrap for the companion `FabricDicomCohortingToolkit` repository. Deploy and UI preflight now resolve the default sibling path and clone the downstream repo when an imaging path executes the Phase 3 toolkit block.
- **Updated** Orchestrator preflight argument threading so imaging validation can pass `-Phase2`/`-Phase3`, `-DicomToolkitPath`, and imaging skip state into `Preflight-Check.ps1`.
- **Fixed** History teardown batch status hydration and replaced unreadable whole-card phase tooltips with accessible `i` popovers in the monitor UI.

### Phase 7: Payer RTI & Ops
- **Added** Phase 7 Payer RTI & Ops.
- **Added** `claim-stream`, `claim-emulator-grp`, `claims_events`, `fraud_scores`, `highcost_alerts`, `care_gap_alerts`.
- **Added** KQL functions `fn_FraudRisk`, `fn_HighCostTrajectory`, `fn_CareGapOnAlert`, `fn_PayerOpsWorklist` and agent wrappers.
- **Added** `PayerOpsActivator`, `HealthcareOpsAgent`, `Payer Ops Triage`, and `Healthcare Graph Agent` shell/manual ontology attach path.

### Phase Monitor & Gantt Matching Upgrades
- **Fixed** Gantt chart in-progress highlighting (pulsing yellow stripes) and updated slow phase threshold from `> 5m` to `> 6m` in Orchestrator UI.
- **Improved** Gantt component pattern matching logic to reliably map custom-normalized step labels and avoid name mismatches.
- **Updated** Phase Monitor complete card action button text from `"After Action Support"` to `"Post Deployment Results"`.
- **Fixed** local FastAPI server (`local_server.py`) `NameError` inside `start_teardown` endpoint by correctly handling partial vs full teardown mode evaluation.

## [Unreleased] — May 27, 2026

### Population Health & Quality Dashboard (4 New Features)
- **Renamed** "CMS Quality Scorecard" → **"Population Health & Quality Dashboard"** (10-page Power BI report)
- **Added** Star Rating Simulator (Step 8)
  - Computes weighted CMS Star Ratings from 7 eCQMs + 3 PDC measures using 2025 cut points
  - What-if simulation: "close N gaps → new star" scenarios (N=10, 25, 50, 100, 250)
  - New Gold tables: `star_rating_detail`, `star_rating_simulation`
  - New report page 7: Star Rating Simulator
- **Added** HCC Risk Adjustment / RAF Scores (Step 9)
  - CMS-HCC V28 model with ~36 SNOMED/ICD-10 → HCC condition mappings
  - Hierarchy rules (keep only most severe per disease group)
  - Demographic RAF coefficients (age/sex bands, Community Non-Dual)
  - Revenue-at-risk calculation ($1,000 PMPM benchmark)
  - New Gold tables: `dim_hcc`, `fact_patient_hcc`, `agg_risk_scores`, `agg_risk_summary`, `revenue_opportunity`
  - New report page 8: Risk Adjustment & RAF
- **Added** 30-Day Readmission Risk ML Model (Step 10)
  - Scikit-learn LogisticRegression trained on 12 features (demographics, LOS, comorbidities, prior utilization, chronic disease flags)
  - 30-day readmission labels computed from Encounter self-join
  - Risk tiers: Low (<15%), Medium (15-30%), High (≥30%)
  - Model performance transparency: AUC, accuracy, precision, recall, feature coefficients
  - New Gold tables: `readmission_risk_scores`, `readmission_risk_summary`, `readmission_model_performance`
  - New report page 9: Readmission Risk
  - **Data Activator**: Daily email alert for high-risk readmission patients
- **Added** Cost & Utilization Analytics (Step 11)
  - Standard utilization metrics: PMPM, IP/1K, ED/1K, ALOS, Bed Days/1K
  - Benchmark comparisons (PMPM $950, IP/1K 300, ED/1K 500, ALOS 5.0)
  - High-cost claimants (≥95th percentile) with condition profiles
  - Condition-specific PMPM (7 chronic conditions)
  - Payer stratification across all metrics
  - New Gold tables: `agg_utilization_summary`, `agg_utilization_by_payer`, `agg_cost_by_category`, `agg_high_cost_claimants`, `agg_condition_pmpm`
  - New report page 10: Cost & Utilization
- **Added** 31 new DAX measures (Star Rating: 4, HCC: 9, Readmission: 5, Utilization: 13) — total now 58
- **Added** 5 new semantic model relationships for cross-table analysis
- **Updated** Orchestrator UI (DeployWizard, PhaseMonitor) with new naming and expanded pattern matching
- Gold Lakehouse grows from 8 → 23 tables; PySpark notebook grows from 760 → 1,529 lines



### Phase 5: Payer-Specific Quality Stratification
- **Moved** all Phase 5 deployment artifacts under `phase-5/` to match the existing `phase-1/`, `phase-2/`, `phase-4/` convention:
  - `cms-quality-report/` → `phase-5/cms-quality-report/`
  - `fabric-rti/sql/materialize_claims_quality.py` → `phase-5/materialize_claims_quality.py`
  - Updated `Deploy-All.ps1`, `.dockerignore`, and docs to reference the new paths
- **Added** `payer_category` denormalized column on `dim_payer`, `fact_claim`, `agg_quality_measures`, `agg_quality_summary` (Medicare / Medicaid / Commercial / Uninsured / Other)
- **Added** `patient_payer` lookup in `materialize_claims_quality.py` — picks each patient's most recent active `Coverage` and propagates payer bucket to facts and quality aggregates
- **Added** `agg_quality_summary` is now computed per measure × payer_category instead of per measure only — enables side-by-side payer comparisons in Direct Lake
- **Added** 14 payer-stratified DAX measures in `_Measures` (Quality Rate / Collection Rate / Denial Rate / Total Paid / Patients Measured per payer)
- **Updated** `docs/phase-5-cms-quality-and-claims.md` with payer stratification section and suggested visuals for the Payer Performance page
- **Backwards compatible**: payer columns default to "Unknown" when Coverage data is absent; no schema-breaking changes (uses `mergeSchema` on overwrite)

## [Unreleased] — April 24, 2026

### Phase 5: CMS Quality & Claims
- **Added** Claims data generation — enabled `Claim`, `ExplanationOfBenefit`, `Coverage` FHIR resources in Synthea properties (flows through existing FHIR → HDS → Silver pipeline)
- **Added** Gold materialization notebook (`materialize_claims_quality.py`) — transforms Silver FHIR tables into star schema: `dim_payer`, `dim_diagnosis`, `fact_claim`, `fact_diagnosis`
- **Added** 7 CMS eCQM quality measures (CMS122 Diabetes HbA1c, CMS165 Blood Pressure, CMS69 BMI Screening, CMS127 Pneumococcal, CMS147 Influenza, CMS134 Diabetes Nephropathy, CMS144 Heart Failure Beta-Blocker)
- **Added** 3 HEDIS medication adherence PDC classes (PDC-DR Diabetes, PDC-RASA RAS Antagonists, PDC-STA Statins) → `agg_medication_adherence`
- **Added** Care gap identification → `care_gaps` table with recommended clinical actions
- **Added** CMS Quality Scorecard Power BI report (Direct Lake, 6 pages, 14 DAX measures)
- **Added** 5 ontology entities (Claim, Payer, Diagnosis, PatientDiagnosis, MedAdherence) + 4 relationships bound to Gold Lakehouse
- **Added** Phase 5 checkbox in Orchestrator UI (DeployWizard + mockDeployment)
- **Added** Phase 5 step in Deploy-All.ps1 (`-Phase5`, `-SkipQualityMeasures`)
- **Added** Backend orchestrator activity (`deploy_quality_measures.py`) + function_app.py wiring

## [Unreleased] — March 28, 2026

### Data Agent Lakehouse Datasource Fix
- **Fixed** `PowerBIEntityNotFound` error in Data Agent UI — lakehouse datasource `type` must be `"lakehouse_tables"` (not `"lakehouse"`), folder prefix must be `lakehouse_tables-` (not `lakehouse-`), and elements must use flat `dbo` schema → table structure without random GUIDs or wrapper grouping. Pattern now matches the working Cohorting Agent (FabricDicomCohortingToolkit).
- **Fixed** `update-agents-inline.ps1` with the same lakehouse datasource corrections

## [Unreleased] — March 26, 2026

### DICOM Loader Fixes
- **Fixed** Python 3.9 compatibility: `str | None` → `Optional[str]`, `tuple[str, str]` → `Tuple[str, str]` in `dicom_retagger.py` and `tcia_client.py`
- **Fixed** `from __future__ import annotations` position in `load_dicom.py` — must be first statement after docstring (was after imports, causing SyntaxError)
- **Fixed** `az acr build` charmap Unicode crash for DICOM loader — added `--no-logs` flag in `deploy-fhir.ps1`

### KQL Deployment
- **Fixed** KQL execution order in `deploy-fabric-rti.ps1` — TelemetryRaw table is now created **before** `fn_AlertHistoryTransform` and the AlertHistory update policy (was created after, causing `General_BadRequest` on fresh deploys)

### Phase 3: Cohorting Toolkit Integration
- **Added** Phase 3 deployment documentation for FabricDicomCohortingToolkit (imaging report, DICOM viewer, cohorting agent)
- **Added** DICOM viewer proxy RBAC requirement — Container App managed identity needs Contributor on Fabric workspace for OneLake file reads
- **Added** OHIF Viewer and TCIA to acknowledgments

### FabricDicomCohortingToolkit
- **Changed** `materialize_reporting.py` — removed all hardcoded workspace/lakehouse GUIDs; now uses `notebookutils.fabric.resolve_workspace_id()` and Fabric REST API to resolve lakehouse IDs by display name
- **Changed** `deploy-notebook.ps1` — auto-discovers OHIF Viewer URL from Azure Static Web App before uploading notebook; patches URL into notebook code at deploy time
- **Changed** Deployment order: DICOM Viewer → Notebook → Report (viewer must deploy first so its URL flows into the reporting data)

## [Unreleased] — March 14-18, 2026

### Deployment Flow
- **Added** Step 1b: Fabric workspace creation early in Phase 1 (before FHIR/DICOM)
- **Fixed** Step 2 to use `-SkipDicom` to prevent duplicate DICOM execution
- **Removed** redundant clinical pipeline trigger — imaging pipeline includes clinical data foundation
- Pipeline sequence: Imaging (includes clinical) → OMOP (was: Clinical → Imaging → OMOP)

### Data Agents
- **Fixed** invalid Observation fewshot query — changed `valueQuantity_value`/`valueQuantity_unit` to `JSON_VALUE(valueQuantity_string, '$.value')`/`JSON_VALUE(valueQuantity_string, '$.unit')`
- **Added** 2 new fewshot examples for full patient summary + demographics by device
- **Added** cross-datasource sample questions (KQL + Lakehouse + DICOM imaging) for both Patient 360 and Clinical Triage agents
- **Fixed** Data Agent portal URL format: `/dataAgents/` → `/aiskills/`

### Deployment Pipeline (Deploy-All.ps1)
- **Added** `-FabricWorkspaceName` as mandatory parameter
- **Added** `-AdminSecurityGroup` as conditionally required (not needed for `-Teardown`/`-Phase2Only`)
- **Changed** `-Location` to mandatory (no default)
- **Changed** `-ResourceGroupName` has default `rg-medtech-rti-fhir` (not mandatory)
- **Added** `-Tags` passthrough to all sub-scripts (`deploy.ps1`, `deploy-fhir.ps1`, `deploy-fabric-rti.ps1`)
- **Added** DICOM shortcut + HDS pipeline step (clinical, imaging, OMOP) in Phase2Only flow
- **Added** pre-populated Phase 2 command in HDS guidance step (auto-fills `-Location`, `-FabricWorkspaceName`, `-Tags` from Phase 1 values)
- **Added** DICOM Data Transformation modality instruction in HDS manual step
- **Fixed** Phase2Only no longer exits early — continues to DICOM shortcuts + Data Agents
- **Fixed** `DeploymentActive` error in `deploy.ps1` — waits 60s and retries
- **Fixed** `RoleAssignmentExists` error in `deploy-fhir.ps1` — treated as non-fatal, falls back to `deployment group show`
- **Fixed** Unicode encoding crash in `az acr build` — added `[Console]::OutputEncoding = UTF8`

### HDS Pipeline Integration
- **Added** OMOP pipeline (`healthcare1_msft_omop_analytics`) as Step 11 in `storage-access-trusted-workspace.ps1`
- **Added** OMOP pipeline parameter to `storage-access-trusted-workspace.ps1`
- Pipeline sequence: Clinical → Imaging → OMOP

### Fabric RTI (deploy-fabric-rti.ps1)
- **Added** `-Tags` parameter — applies tags to Event Hub namespace before enabling SAS auth
- **Added** RBAC propagation wait (60s + verification) after assigning Storage Blob Data Contributor
- **Added** storage access preflight check before shortcut creation
- **Added** 3-attempt retry with 60s wait for Bronze LH shortcut creation
- **Added** Kusto token refresh before KQL external table creation (prevents 401 after long pipeline waits)
- **Added** Workspace identity resolution via Fabric API (`provisionIdentity` → `GET /workspaces/{id}`) with `az ad sp` fallback
- **Added** detailed remediation instructions on shortcut creation failure (SP IDs, portal steps, re-run command)
- **Fixed** `/workspaces/{id}/lakehouses` → `/workspaces/{id}/items?type=Lakehouse` (deprecated endpoint)

### Cleanup (Remove-AllResources.ps1)
- **Added** `-DeleteWorkspace` parameter to delete the Fabric workspace itself
- **Added** Step 2b: deprovision workspace identity + delete Entra app registration
- **Added** `Delete Workspace:` display in teardown banner

### Documentation
- **Updated** README.md: configuration options table with Required column, pre-populated CLI examples, Deploy-All orchestrator section, cleanup section, OMOP in diagrams
- **Updated** PRD.md: OMOP pipeline in artifacts table, data flow diagram, deployment sequence, script descriptions
- **Updated** HDS-SETUP-GUIDE.md: added imaging + OMOP pipelines to artifacts table
- **Updated** all Mermaid diagrams to include OMOP pipeline flow

# Phase 6 — Population Health + Quality

Phase 6 materializes clinical and claims facts into a governed Gold analytical model for quality, care gaps, medication adherence, Star Ratings, HCC risk, readmission, cost, and utilization.

[← Phase 5](phase-5-bedside-alerting-and-action.md) · [Main README](../README.md) · [Interactive diagram](diagrams/phase-6-population-health-and-quality.html) · [Diagram source](diagrams/phase-6-population-health-and-quality.dataflow.json) · [Next: Phase 7 →](phase-7-payer-rti-and-ops.md)

<a href="diagrams/phase-6-population-health-and-quality.html">
  <img src="diagrams/phase-6-population-health-and-quality.visual-check.1440x900.light.png#gh-light-mode-only" alt="Phase 6 flow from HDS Silver clinical and claims facts through the claims and quality materialization notebook into reporting Gold, the semantic model, the five-page Power BI dashboard, and readmission alerting">
  <img src="diagrams/phase-6-population-health-and-quality.visual-check.1440x900.dark.png#gh-dark-mode-only" alt="Phase 6 flow from HDS Silver clinical and claims facts through the claims and quality materialization notebook into reporting Gold, the semantic model, the five-page Power BI dashboard, and readmission alerting">
</a>

## Exit contract

Phase 6 is complete only when:

- The materialization notebook finishes without any required table failure.
- All 23 reporting Gold fact, dimension, and aggregate tables exist with contract-valid schemas.
- Required claims, quality, adherence, risk, readmission, and utilization facts are populated for the selected demo cohort.
- `Population Health & Quality Semantic Model` is bound to the target `healthcare1_reporting_gold` lakehouse.
- The canonical dashboard renders five integrated pages with 46 visuals.
- Payer slicers and stratified measures resolve the deployed payer categories.
- `ReadmissionRiskAlert` is configured when an alert recipient is supplied.

A queryable semantic model with every business fact table empty fails this phase.

## Prerequisites

- [Phase 3](phase-3-hds-bridge-and-row-gates.md) populated HDS Silver.
- Silver includes the selected clinical and claims resources, including Patient, Encounter, Condition, Observation, MedicationRequest, Immunization, Coverage, and ExplanationOfBenefit/Claim inputs.
- The deploying identity can run Fabric notebooks and create/update semantic models, reports, KQL shortcuts, and Reflex items.
- Power BI and Data Activator are enabled when those outputs are selected.

## Materialization

[`phase-5/materialize_claims_quality.py`](../phase-5/materialize_claims_quality.py) transforms HDS Silver into a reporting Gold star schema.

### Core analytical domains

| Domain | Representative outputs |
|---|---|
| Claims and payer | `fact_claim`, `dim_payer`, `dim_diagnosis`, `fact_diagnosis` |
| Quality | `agg_quality_measures`, `agg_quality_summary`, `care_gaps` |
| Medication adherence | `agg_medication_adherence` |
| Star Ratings | `star_rating_detail`, `star_rating_simulation` |
| HCC risk | `dim_hcc`, `fact_patient_hcc`, `agg_risk_scores`, `agg_risk_summary`, `revenue_opportunity` |
| Readmission | `readmission_risk_scores`, `readmission_risk_summary`, `readmission_model_performance` |
| Cost and utilization | `agg_utilization_summary`, `agg_utilization_by_payer`, `agg_cost_by_category`, `agg_high_cost_claimants`, `agg_condition_pmpm` |

Synthetic sparse-cohort support rows are provenance-labeled. They must remain distinguishable from observed rows; they are not evidence about a real population.

## Quality measures

The materializer computes these demonstration eCQM domains:

| Measure | Focus |
|---|---|
| CMS122 | Diabetes HbA1c poor control |
| CMS165 | Controlling high blood pressure |
| CMS69 | BMI screening and follow-up |
| CMS127 | Pneumococcal vaccination status |
| CMS147 | Influenza immunization |
| CMS134 | Diabetes nephropathy attention |
| CMS144 | Heart failure beta-blocker therapy |

Medication adherence uses proportion of days covered for diabetes medications, RAS antagonists, and statins. HCC processing applies V28-oriented mappings and hierarchy rules for the synthetic demonstration.

## Readmission and utilization

The readmission path scores encounters from demographic, utilization, condition, and medication features and records model performance. Cost/utilization outputs include PMPM, inpatient admissions, ED visits, length of stay, bed days, service categories, condition PMPM, and high-cost claimant summaries.

These are accelerator analytics, not validated clinical or actuarial models.

## Power BI surface

The canonical `Population Health & Quality Dashboard` contains five integrated pages:

1. Executive Overview
2. Quality & Care Gaps
3. Claims & Payer Performance
4. Stars & Risk Adjustment
5. Readmission & Utilization

The report project is under [`phase-5/cms-quality-report/`](../phase-5/cms-quality-report/). Deployment rewrites its lakehouse binding for the target workspace before creating/updating the semantic model and report.

Some environments require the deploying user to authorize the semantic model connection in the Fabric/Power BI portal after deployment.

## Readmission Activator

When `-AlertEmail` is supplied and Activator is enabled, the deployment:

1. Creates a KQL shortcut over the Gold readmission risk scores.
2. Creates or updates `ReadmissionRiskAlert`.
3. Configures a daily digest for qualifying high-risk rows.

No recipient means alerting is intentionally skipped; dashboard and analytical materialization remain independent gates.

## Run it

Full deployment:

```powershell
./Deploy-All.ps1 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -AlertEmail "care-team@example.org"
```

Targeted quality continuation:

```powershell
./Deploy-All.ps1 `
  -Phase5 `
  -FabricWorkspaceName "<fabric-workspace>" `
  -ResourceGroupName "<resource-group>" `
  -Location "eastus" `
  -AlertEmail "care-team@example.org"
```

> [!NOTE]
> `-Phase5` is the historical CLI switch for the conceptual **Phase 6** Population Health & Quality workload.

## Verify it

- Query every required Gold table and distinguish supported sparse outputs from a wholly blank model.
- Require populated `fact_claim`, quality aggregates, care gaps, risk scores, and selected utilization/readmission facts.
- Confirm the semantic model points to the target workspace and reporting lakehouse.
- Render all five report pages and inspect the expected multi-visual layout; single-card placeholders do not pass.
- Exercise payer slicers across available categories.
- If alerting is selected, confirm the risk shortcut returns rows and the Reflex contains the intended recipient/rule.

## Common failures

| Symptom | Check |
|---|---|
| Materializer reports missing Silver input | Complete HDS clinical/claims ingestion and inspect the exact source table |
| Semantic model is queryable but visuals are blank | Query required Gold facts; do not treat schema-only state as success |
| Report points at another workspace | Inspect the rewritten Direct Lake host/item binding before refresh |
| Report requests credentials | Authorize the semantic model connection with the intended OAuth identity |
| Readmission alert is absent | Verify `-AlertEmail`, Activator enablement, KQL shortcut creation, and Reflex update result |
| Synthetic marker rows look like observed evidence | Filter and display `scenario_source` provenance explicitly |

## Source map

- [`phase-5/materialize_claims_quality.py`](../phase-5/materialize_claims_quality.py) — 23-table Gold materialization
- [`phase-5/cms-quality-report/`](../phase-5/cms-quality-report/) — semantic model and report project
- [`orchestrator/activities/deploy_quality_measures.py`](../orchestrator/activities/deploy_quality_measures.py) — orchestrator activity contract
- [`Deploy-All.ps1`](../Deploy-All.ps1) — notebook, report, model, and ReadmissionRiskAlert deployment

[← Phase 5 — Bedside Alerting + Action](phase-5-bedside-alerting-and-action.md) · [Next: Phase 7 — Payer RTI + Operations →](phase-7-payer-rti-and-ops.md)

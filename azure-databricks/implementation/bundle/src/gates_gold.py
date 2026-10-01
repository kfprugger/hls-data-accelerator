# Databricks notebook source
"""Fail-closed Gold gates.

Fabric equivalent replaced here:
  the semantic-model and report data checks that rejected a queryable but blank model.
"""

dbutils.widgets.text("catalog", "hls_dev")
CATALOG = dbutils.widgets.get("catalog")

REQUIRED = [
    "omop_person",
    "omop_visit_occurrence",
    "agent_patient_360",
    "agent_patient_device",
    "agent_cross_domain_context",
    "agent_healthcare_relationships",
]
CONDITIONAL = {
    # product -> upstream Silver table that must be non-empty for the product to matter
    "fact_claim": "claim_events",
    "agg_utilization_by_payer": "claim_events",
    "payer_worklist": "claim_events",
    "imaging_report_facts": "imaging_instance",
    "agent_imaging_cohort": "imaging_study",
    "agent_fraud_risk": "claim_events",
}
OPTIONAL = [
    "agent_clinical_triage",
    "agent_care_gaps",
    "agent_high_cost_members",
    "agent_payer_worklist",
]

failures = []
summary = {}

for table in REQUIRED:
    count = spark.table(f"{CATALOG}.gold.{table}").count()
    summary[table] = count
    if count == 0:
        failures.append(f"{CATALOG}.gold.{table} is empty")

for product, upstream in CONDITIONAL.items():
    upstream_count = spark.table(f"{CATALOG}.silver.{upstream}").count()
    product_count = spark.table(f"{CATALOG}.gold.{product}").count()
    summary[product] = {"rows": product_count, "upstream_rows": upstream_count}
    # Empty is acceptable only when the upstream cohort is genuinely empty.
    if upstream_count > 0 and product_count == 0:
        failures.append(f"{CATALOG}.gold.{product} is empty while {upstream} has {upstream_count} rows")

for table in OPTIONAL:
    # These are valid with zero rows when the current alert/risk cohort is empty,
    # but they must compile and remain queryable for their Genie Agent.
    summary[table] = spark.table(f"{CATALOG}.gold.{table}").count()

# A wholly blank Gold estate is never a pass.
if all(
    (value if isinstance(value, int) else value["rows"]) == 0
    for value in summary.values()
):
    failures.append("every Gold product is empty")

print(summary)
if failures:
    raise AssertionError("Gold gate failed: " + "; ".join(failures))
print("Gold gates passed.")

# Databricks notebook source
"""Fail-closed stream freshness gate.

Fabric equivalent replaced here:
  the Eventstream topology check that required Running nodes plus fresh destination
  events. A running pipeline with no new rows is still a failure here.
"""

dbutils.widgets.text("catalog", "hls_dev")
dbutils.widgets.text("max_age_minutes", "10")

CATALOG = dbutils.widgets.get("catalog")
MAX_AGE_MINUTES = int(dbutils.widgets.get("max_age_minutes"))

STREAMS = {
    "telemetry": ("bronze.telemetry_raw", "silver.telemetry", "observed_at"),
    "claims": ("bronze.claim_events_raw", "silver.claim_events", "submitted_at"),
}

failures = []
summary = {}

for name, (bronze_table, silver_table, event_time_column) in STREAMS.items():
    bronze = spark.sql(f"""
        SELECT count(*) AS rows,
               max(ingested_at) AS last_ingested_at,
               timestampdiff(MINUTE, max(ingested_at), current_timestamp()) AS age_minutes
        FROM {CATALOG}.{bronze_table}
    """).collect()[0]
    silver = spark.sql(f"""
        SELECT count(*) AS rows,
               count(DISTINCT event_key) AS distinct_keys,
               max({event_time_column}) AS last_event_at
        FROM {CATALOG}.{silver_table}
    """).collect()[0]

    summary[name] = {
        "bronze_rows": bronze["rows"],
        "bronze_age_minutes": bronze["age_minutes"],
        "silver_rows": silver["rows"],
        "silver_distinct_keys": silver["distinct_keys"],
        "last_event_at": str(silver["last_event_at"]),
    }

    if bronze["rows"] == 0:
        failures.append(f"{name}: no Bronze events ingested")
        continue
    if bronze["age_minutes"] is None or bronze["age_minutes"] > MAX_AGE_MINUTES:
        failures.append(f"{name}: newest Bronze event is {bronze['age_minutes']} minutes old")
    if silver["rows"] == 0:
        failures.append(f"{name}: Bronze has rows but Silver is empty")
    elif silver["rows"] != silver["distinct_keys"]:
        failures.append(f"{name}: deduplication failed ({silver['rows']} rows, {silver['distinct_keys']} keys)")

print(summary)
if failures:
    raise AssertionError("Stream freshness gate failed: " + "; ".join(failures))
print("Stream freshness gates passed.")

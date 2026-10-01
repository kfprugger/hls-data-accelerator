# Databricks notebook source
"""Fail-closed Silver gates.

Fabric equivalent replaced here:
  the HDS row gates and FHIR reference-integrity checks in Deploy-All.ps1.

A failure raises, which fails the job task and stops Gold from starting.
"""

dbutils.widgets.text("catalog", "hls_dev")
CATALOG = dbutils.widgets.get("catalog")

REQUIRED_TABLES = [
    "patient",
    "encounter",
    "condition",
    "observation",
    "medication_request",
    "coverage",
    "device",
    "device_association",
]

OPTIONAL_TABLES = ["imaging_study", "imaging_instance"]

failures = []
summary = {}

for table in REQUIRED_TABLES:
    count = spark.table(f"{CATALOG}.silver.{table}").count()
    summary[table] = count
    if count == 0:
        failures.append(f"{CATALOG}.silver.{table} is empty")

for table in OPTIONAL_TABLES:
    summary[table] = spark.table(f"{CATALOG}.silver.{table}").count()

# Imaging is optional, but a partial imaging estate is a failure, not a pass.
if summary["imaging_study"] > 0 and summary["imaging_instance"] == 0:
    failures.append("ImagingStudy rows exist but no DICOM instance joined to them")

# Encounters must resolve to a known patient.
orphan_encounters = spark.sql(f"""
    SELECT count(*) AS orphans
    FROM {CATALOG}.silver.encounter e
    LEFT ANTI JOIN {CATALOG}.silver.patient p
      ON e.subject_reference = concat('Patient/', p.resource_id)
""").collect()[0]["orphans"]
summary["orphan_encounters"] = orphan_encounters
if orphan_encounters > 0:
    failures.append(f"{orphan_encounters} encounters do not resolve to a Silver patient")

# Device associations must stay one-to-one for the canonical demo cohort.
duplicate_devices = spark.sql(f"""
    SELECT count(*) AS duplicates FROM (
      SELECT get_json_object(resource_json, '$.extension[0].valueReference.reference') AS device_id
      FROM {CATALOG}.silver.device_association
      GROUP BY 1
      HAVING count(*) > 1
    )
""").collect()[0]["duplicates"]
summary["duplicate_device_associations"] = duplicate_devices
if duplicate_devices > 0:
    failures.append(f"{duplicate_devices} device identifiers map to multiple associations")

print(summary)
if failures:
    raise AssertionError("Silver gate failed: " + "; ".join(failures))
print("Silver gates passed.")

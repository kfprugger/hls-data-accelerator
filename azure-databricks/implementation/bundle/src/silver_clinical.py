"""Silver normalization for FHIR entities and imaging metadata.

Fabric equivalent replaced here:
  HDS clinical_data_foundation and imaging_with_clinical_foundation Silver tables.

Design rules:
  - One table per FHIR resource type so downstream products bind to stable names.
  - Expectations encode the HDS reference gates instead of a separate gate notebook.
  - Streaming tables stay append-friendly; deduplication uses the resource identity.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

CATALOG = spark.conf.get("hls.catalog")

FHIR_ENTITIES = {
    "patient": "Patient",
    "encounter": "Encounter",
    "condition": "Condition",
    "observation": "Observation",
    "medication_request": "MedicationRequest",
    "procedure": "Procedure",
    "immunization": "Immunization",
    "coverage": "Coverage",
    "claim": "Claim",
    "explanation_of_benefit": "ExplanationOfBenefit",
    "device": "Device",
    "location": "Location",
    "imaging_study": "ImagingStudy",
    "device_association": "Basic",
}

SUBJECT_REQUIRED = {"encounter", "condition", "observation", "medication_request", "procedure", "imaging_study"}


def _fhir_entity_factory(table_name: str, resource_type: str):
    expectations = {"has_resource_id": "resource_id IS NOT NULL"}
    if table_name in SUBJECT_REQUIRED:
        expectations["resolves_subject"] = "subject_reference IS NOT NULL"

    @dp.materialized_view(
        name=table_name,
        comment=f"Normalized FHIR {resource_type} resources.",
        table_properties={"quality": "silver"},
    )
    @dp.expect_all_or_drop(expectations)
    def entity():
        return (
            spark.read.table(f"{CATALOG}.bronze.fhir_raw")
            .where(F.col("resource_type") == resource_type)
            .select(
                F.col("resource_id"),
                F.get_json_object("resource_json", "$.subject.reference").alias("subject_reference"),
                F.get_json_object("resource_json", "$.patient.reference").alias("patient_reference"),
                F.get_json_object("resource_json", "$.encounter.reference").alias("encounter_reference"),
                F.get_json_object("resource_json", "$.status").alias("status"),
                F.col("resource_json"),
                F.col("source_path"),
                F.col("ingested_at"),
            )
            .dropDuplicates(["resource_id"])
        )

    return entity


for _table_name, _resource_type in FHIR_ENTITIES.items():
    globals()[f"silver_{_table_name}"] = _fhir_entity_factory(_table_name, _resource_type)


@dp.materialized_view(
    name="imaging_instance",
    comment="DICOM instance metadata joined to the governed FHIR ImagingStudy.",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("joins_imaging_study", "imaging_study_resource_id IS NOT NULL")
def imaging_instance():
    inventory = spark.read.table(f"{CATALOG}.bronze.dicom_inventory_raw")
    studies = (
        spark.read.table(f"{CATALOG}.silver.imaging_study")
        .select(
            F.col("resource_id").alias("imaging_study_resource_id"),
            F.get_json_object("resource_json", "$.identifier[0].value").alias("study_uid"),
            F.col("subject_reference").alias("patient_reference"),
        )
    )
    joined = inventory.join(
        studies,
        (inventory["fhir_imaging_study_id"] == studies["imaging_study_resource_id"])
        | (inventory["study_uid"] == studies["study_uid"]),
        how="left",
    )
    return (
        joined.select(
            inventory["object_path"],
            inventory["object_bytes"],
            inventory["study_uid"],
            inventory["series_uid"],
            inventory["instance_file"],
            inventory["synthetic_patient_id"],
            studies["imaging_study_resource_id"],
            studies["patient_reference"],
            inventory["ingested_at"],
        )
        .dropDuplicates(["object_path"])
    )

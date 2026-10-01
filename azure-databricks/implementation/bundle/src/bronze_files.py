"""Bronze ingestion for FHIR $export NDJSON and re-tagged DICOM objects.

Fabric equivalent replaced here:
  OneLake shortcuts + HDS clinical/imaging Bronze ingestion notebooks.

Design rules:
  - Auto Loader reads governed Unity Catalog volumes, never a raw account key path.
  - Bronze keeps the untouched payload plus provenance so a replay is possible.
  - DICOM pixel bytes stay in ADLS; only metadata and the object path land in Delta.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

FHIR_VOLUME = spark.conf.get("hls.fhir_export_volume")
DICOM_VOLUME = spark.conf.get("hls.dicom_volume")
STATE_VOLUME = spark.conf.get("hls.state_volume")


@dp.table(
    name="fhir_raw",
    comment="Raw FHIR $export NDJSON with ingestion provenance.",
    table_properties={"quality": "bronze", "pipelines.reset.allowed": "false"},
)
@dp.expect_or_drop("has_resource_type", "resource_type IS NOT NULL")
def fhir_raw():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "text")
        .option("cloudFiles.inferColumnTypes", "false")
        .option("cloudFiles.schemaLocation", f"{STATE_VOLUME}/schema/fhir_raw")
        .load(f"{FHIR_VOLUME}/")
        .withColumnRenamed("value", "resource_json")
        .withColumn("source_path", F.col("_metadata.file_path"))
        .withColumn("source_modified_at", F.col("_metadata.file_modification_time"))
        .withColumn("resource_type", F.get_json_object("resource_json", "$.resourceType"))
        .withColumn("resource_id", F.get_json_object("resource_json", "$.id"))
        .withColumn("ingested_at", F.current_timestamp())
    )


@dp.table(
    name="dicom_inventory_raw",
    comment="DICOM study/series inventory from the loader manifests; pixel data stays outside Delta.",
    table_properties={"quality": "bronze", "pipelines.reset.allowed": "false"},
)
@dp.expect_or_drop("has_object_path", "object_path IS NOT NULL")
def dicom_inventory_raw():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("pathGlobFilter", "*.json")
        .option("cloudFiles.schemaLocation", f"{STATE_VOLUME}/schema/dicom_inventory")
        .load(f"{DICOM_VOLUME}/_manifest/studies/")
        .select(
            F.col("blobBasePath").alias("object_path"),
            F.lit(None).cast("long").alias("object_bytes"),
            F.col("studyInstanceUid").alias("study_uid"),
            F.col("seriesInstanceUid").alias("series_uid"),
            F.element_at(F.from_json("sopInstanceUids", "array<string>"), 1).alias("instance_file"),
            F.col("patientFhirId").alias("synthetic_patient_id"),
            F.col("fhirImagingStudyId").alias("fhir_imaging_study_id"),
            F.col("instanceCount").cast("long").alias("instance_count"),
            F.col("_metadata.file_path").alias("manifest_path"),
            F.col("_metadata.file_modification_time").alias("source_modified_at"),
            F.current_timestamp().alias("ingested_at"),
        )
    )

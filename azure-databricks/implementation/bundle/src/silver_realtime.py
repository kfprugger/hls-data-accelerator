"""Silver typing, deduplication, and clinical enrichment for the live feeds.

Fabric equivalent replaced here:
  Eventhouse TelemetryRaw / claims_events plus the enriched KQL alert functions.

Design rules:
  - At-least-once delivery means a deterministic business key is mandatory.
  - Watermarks bound state; the dedup key is (device/claim id, event time).
  - Clinical context is joined from governed Silver, never from the raw payload.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType, TimestampType

CATALOG = spark.conf.get("hls.catalog")

TELEMETRY_VALUES_SCHEMA = StructType([
    StructField("spo2", DoubleType()),
    StructField("pr", DoubleType()),
    StructField("pi", DoubleType()),
    StructField("signal_iq", DoubleType()),
])

TELEMETRY_SCHEMA = StructType([
    StructField("device_id", StringType()),
    StructField("timestamp", TimestampType()),
    StructField("telemetry", TELEMETRY_VALUES_SCHEMA),
])
CLAIM_SCHEMA = StructType([
    StructField("event_id", StringType()),
    StructField("event_timestamp", TimestampType()),
    StructField("event_type", StringType()),
    StructField("claim_id", StringType()),
    StructField("patient_id", StringType()),
    StructField("provider_id", StringType()),
    StructField("facility_id", StringType()),
    StructField("payer_id", StringType()),
    StructField("diagnosis_code", StringType()),
    StructField("procedure_code", StringType()),
    StructField("claim_type", StringType()),
    StructField("claim_amount", DoubleType()),
    StructField("latitude", DoubleType()),
    StructField("longitude", DoubleType()),
    StructField("injected_fraud_flags", StringType()),
])


@dp.table(
    name="telemetry",
    comment="Typed, deduplicated device telemetry with a stable event key.",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("has_device", "device_id IS NOT NULL")
@dp.expect_or_drop("has_event_time", "observed_at IS NOT NULL")
@dp.expect("plausible_spo2", "spo2 IS NULL OR (spo2 BETWEEN 50 AND 100)")
def telemetry():
    parsed = (
        spark.readStream.table(f"{CATALOG}.bronze.telemetry_raw")
        .select(F.from_json("payload_json", TELEMETRY_SCHEMA).alias("p"), "topic", "partition", "offset", "enqueued_at")
    )
    return (
        parsed.select(
            F.col("p.device_id").alias("device_id"),
            F.col("p.timestamp").alias("observed_at"),
            F.col("p.telemetry.spo2").alias("spo2"),
            F.col("p.telemetry.pr").alias("pulse_rate"),
            F.col("p.telemetry.pi").alias("perfusion_index"),
            F.col("p.telemetry.signal_iq").alias("signal_quality"),
            "topic", "partition", "offset", "enqueued_at",
        )
        .withColumn("event_key", F.sha2(F.concat_ws("|", "device_id", "observed_at"), 256))
        .withWatermark("observed_at", "30 minutes")
        .dropDuplicates(["event_key"])
    )


@dp.table(
    name="claim_events",
    comment="Typed, deduplicated payer claim events.",
    table_properties={"quality": "silver"},
)
@dp.expect_or_drop("has_claim", "claim_id IS NOT NULL")
@dp.expect_or_drop("has_event_time", "submitted_at IS NOT NULL")
def claim_events():
    parsed = (
        spark.readStream.table(f"{CATALOG}.bronze.claim_events_raw")
        .select(F.from_json("payload_json", CLAIM_SCHEMA).alias("p"), "topic", "partition", "offset", "enqueued_at")
    )
    return (
        parsed.select(
            F.col("p.event_id").alias("event_id"),
            F.col("p.event_type").alias("event_type"),
            F.col("p.claim_id").alias("claim_id"),
            F.col("p.patient_id").alias("patient_id"),
            F.col("p.provider_id").alias("provider_id"),
            F.col("p.facility_id").alias("facility_id"),
            F.col("p.payer_id").alias("payer_id"),
            F.col("p.diagnosis_code").alias("diagnosis_code"),
            F.col("p.procedure_code").alias("procedure_code"),
            F.col("p.claim_type").alias("claim_type"),
            F.col("p.event_timestamp").alias("submitted_at"),
            F.col("p.claim_amount").alias("billed_amount"),
            F.lit(None).cast("double").alias("allowed_amount"),
            F.col("p.latitude").alias("latitude"),
            F.col("p.longitude").alias("longitude"),
            F.col("p.injected_fraud_flags").alias("injected_fraud_flags"),
            "topic", "partition", "offset", "enqueued_at",
        )
        .withColumn("event_key", F.sha2(F.concat_ws("|", "claim_id", "submitted_at"), 256))
        .withWatermark("submitted_at", "2 hours")
        .dropDuplicates(["event_key"])
    )


@dp.materialized_view(
    name="clinical_alert_candidates",
    comment="Tiered alert candidates with per-device cooldown state already applied.",
    table_properties={"quality": "ops"},
)
def clinical_alert_candidates():
    telemetry_rows = spark.read.table(f"{CATALOG}.silver.telemetry")
    devices = (
        spark.read.table(f"{CATALOG}.silver.device_association")
        .select(
            F.get_json_object("resource_json", "$.code.coding[0].code").alias("association_code"),
            F.get_json_object("resource_json", "$.subject.reference").alias("patient_reference"),
            F.regexp_replace(
                F.get_json_object("resource_json", "$.extension[0].valueReference.reference"),
                "^Device/",
                "",
            ).alias("device_id"),
        )
        .where(F.col("association_code") == "device-assoc")
        .select("device_id", "patient_reference")
    )

    tiered = (
        telemetry_rows.join(devices, on="device_id", how="left")
        .withColumn(
            "alert_tier",
            F.when(F.col("spo2") < 85, F.lit("CRITICAL"))
            .when(F.col("spo2") < 90, F.lit("URGENT"))
            .when(F.col("spo2") < 92, F.lit("WARNING")),
        )
        .where(F.col("alert_tier").isNotNull())
    )

    # Cooldown is computed here so the SQL alert cannot page twice for one device.
    window = F.window("observed_at", "15 minutes")
    first_per_window = (
        tiered.groupBy("device_id", window)
        .agg(F.min("observed_at").alias("observed_at"))
        .select("device_id", "observed_at")
        .withColumn("is_first_in_cooldown", F.lit(True))
    )

    return (
        tiered.join(first_per_window, on=["device_id", "observed_at"], how="left")
        .withColumn("suppressed_by_cooldown", F.coalesce(~F.col("is_first_in_cooldown"), F.lit(True)))
        .select(
            "device_id",
            "patient_reference",
            "observed_at",
            "spo2",
            "pulse_rate",
            "perfusion_index",
            "alert_tier",
            "suppressed_by_cooldown",
        )
    )

"""Bronze ingestion for the existing telemetry and claim Event Hubs.

Fabric equivalent replaced here:
  MasimoTelemetryStream and ClaimsRTIStream Eventstreams into Eventhouse.

Design rules:
  - Azure Event Hubs is read through its Kafka-compatible endpoint on port 9093.
    The JVM azure-event-hubs-spark connector is not available to pipelines.
  - Each hub gets its own consumer group so the two feeds never share offsets.
  - The listen-only key comes from a secret scope. No connection string in code.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

NAMESPACE = spark.conf.get("hls.eventhub.namespace")
SECRET_SCOPE = spark.conf.get("hls.eventhub.secret_scope")
SECRET_KEY = spark.conf.get("hls.eventhub.secret_key")
STARTING_OFFSETS = spark.conf.get("hls.stream.starting_offsets")
MAX_OFFSETS = spark.conf.get("hls.stream.max_offsets_per_trigger")

BOOTSTRAP = f"{NAMESPACE}.servicebus.windows.net:9093"
LISTEN_KEY = dbutils.secrets.get(scope=SECRET_SCOPE, key=SECRET_KEY)
CONNECTION_STRING = (
    f"Endpoint=sb://{NAMESPACE}.servicebus.windows.net/;"
    f"SharedAccessKeyName=hls-databricks-listen;SharedAccessKey={LISTEN_KEY}"
)
JAAS = (
    "kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required "
    f'username="$ConnectionString" password="{CONNECTION_STRING}";'
)


def kafka_options(hub: str, consumer_group: str) -> dict:
    return {
        "kafka.bootstrap.servers": BOOTSTRAP,
        "subscribe": hub,
        "kafka.sasl.mechanism": "PLAIN",
        "kafka.security.protocol": "SASL_SSL",
        "kafka.sasl.jaas.config": JAAS,
        "kafka.group.id": consumer_group,
        "startingOffsets": STARTING_OFFSETS,
        "maxOffsetsPerTrigger": MAX_OFFSETS,
        "failOnDataLoss": "false",
    }


def read_hub(hub: str, consumer_group: str):
    return (
        spark.readStream.format("kafka")
        .options(**kafka_options(hub, consumer_group))
        .load()
        .select(
            F.col("topic"),
            F.col("partition"),
            F.col("offset"),
            F.col("timestamp").alias("enqueued_at"),
            F.col("value").cast("string").alias("payload_json"),
            F.current_timestamp().alias("ingested_at"),
        )
    )


@dp.table(
    name="telemetry_raw",
    comment="Raw Masimo device telemetry with Event Hubs offsets retained.",
    table_properties={"quality": "bronze", "pipelines.reset.allowed": "false"},
)
@dp.expect_or_drop("has_payload", "payload_json IS NOT NULL")
def telemetry_raw():
    return read_hub(
        spark.conf.get("hls.eventhub.telemetry_hub"),
        spark.conf.get("hls.eventhub.telemetry_consumer_group"),
    )


@dp.table(
    name="claim_events_raw",
    comment="Raw payer claim events with Event Hubs offsets retained.",
    table_properties={"quality": "bronze", "pipelines.reset.allowed": "false"},
)
@dp.expect_or_drop("has_payload", "payload_json IS NOT NULL")
def claim_events_raw():
    return read_hub(
        spark.conf.get("hls.eventhub.claims_hub"),
        spark.conf.get("hls.eventhub.claims_consumer_group"),
    )

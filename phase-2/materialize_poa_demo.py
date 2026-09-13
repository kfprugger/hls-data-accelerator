"""Materialize labeled POA demo events from approved synthetic appointments."""
from pyspark.sql import functions as F
from pyspark.sql.window import Window

GOLD_LAKEHOUSE = "healthcare1_msft_poa_gold"
SOURCE = "synthetic-demo-enrichment"
appointments = spark.table(f"{GOLD_LAKEHOUSE}.AppointmentDim")
journey = spark.table(f"{GOLD_LAKEHOUSE}.JourneyDim").orderBy("JourneyKey").limit(1)
asset = spark.table(f"{GOLD_LAKEHOUSE}.MarketingAssetDim").orderBy("AssetKey").limit(1)
channel = spark.table(f"{GOLD_LAKEHOUSE}.MarketingChannelDim").filter(F.col("ChannelName") == "Email").orderBy("ChannelKey").limit(1)
if not all(frame.count() for frame in (appointments, journey, asset, channel)):
    raise RuntimeError("POA dimensions must be populated before demo event materialization")
events = (appointments.crossJoin(journey.select("JourneyKey")).crossJoin(asset.select("AssetKey"))
          .crossJoin(channel.select("ChannelKey"))
          .withColumn("MarketingEventKey", F.row_number().over(Window.orderBy("AppointmentKey")))
          .withColumn("EventDate", F.col("AppointmentScheduledDate"))
          .withColumn("EventMonthYear", F.date_format("AppointmentScheduledDate", "MMM-yyyy"))
          .withColumn("SourceModifiedOn", F.current_timestamp()).withColumn("SourceTable", F.lit(SOURCE))
          .select("SourceModifiedOn", "PatientKey", "JourneyKey", "MarketingEventKey", "AppointmentKey",
                  "EventMonthYear", "SourceTable", "ChannelKey", "EventDate", "AssetKey"))
events.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{GOLD_LAKEHOUSE}.MarketingEventFact")
print(f"Materialized {events.count()} labeled POA demo events")

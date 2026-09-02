# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

from pyspark.sql.types import StructType, StructField, StringType, DoubleType, MapType, LongType, TimestampType

class ExecutionMetricsConstants:
    DEFAULT_EXECUTION_SUMMARY_TABLE = "ExecutionSummary"
    DEFAULT_EXECUTION_SUMMARY_UNIQUE_COLUMNS = ["id"]
    DEFAULT_SOURCE_MODIFIED_DATETIME_COL = "msftModifiedDatetime"
    DEFAULT_METRICS_POLLING_INTERVAL_IN_MIN = 120
    DEFAULT_MINIMUM_METRICS_POLLING_INTERVAL_IN_MIN = 1
    DEFAULT_INITIAL_STATE = {
        "numSourceRecords": 0,
        "numTargetRecords": 0,
        "sourceDataSizeBytes": 0,
        "targetDataSizeBytes": 0,
        "numSourceFiles": 0,
        "numTargetFiles": 0,
        "batchesProcessed": 0,
        "numTargetRecordsGranular": {},
        "numSourceRecordsGranular": {},
        "activityAttributes": {}
    }

    GRANULAR_METRICS_KEYS = ["numTargetRecordsGranular", "numSourceRecordsGranular"]
    
    DEFAULT_EXECUTION_SUMMARY_TABLE_SCHEMA = StructType([
        StructField("id", StringType(), False),
        StructField("activityName", StringType(), False),
        StructField("runId", StringType(), False),
        StructField("pipelineRunId", StringType(), True),
        StructField("pipelineName", StringType(), True),
        StructField("executionStatus", StringType(), False),
        StructField("executionStatusDetails", StringType(), False),
        StructField("targetType", StringType(), True),
        StructField("targetPath", StringType(), True),
        StructField("targetLakehouseName", StringType(), True),
        StructField("targetLakehouseIdentifier", StringType(), True),
        StructField("numTargetRecords", LongType(), True),
        StructField("numTargetRecordsGranular", MapType(StringType(), LongType()), True),
        StructField("numTargetFiles", LongType(), True),
        StructField("targetDataSizeBytes", LongType(), True),
        StructField("sourceType", StringType(), True),
        StructField("sourcePath", StringType(), True),
        StructField("sourceLakehouseName", StringType(), True),
        StructField("sourceLakehouseIdentifier", StringType(), True),
        StructField("numSourceRecords", LongType(), True),
        StructField("numSourceRecordsGranular", MapType(StringType(), LongType()), True),
        StructField("numSourceFiles", LongType(), True),
        StructField("sourceDataSizeBytes", LongType(), True),
        StructField("batchesProcessed", LongType(), True),
        StructField("elapsedTime", DoubleType(), True),
        StructField("activityAttributes", MapType(StringType(), StringType()), True),
        StructField("msftModifiedDatetime", TimestampType(), True),
        StructField("msftCreatedDatetime", TimestampType(), True)
    ])
    
    
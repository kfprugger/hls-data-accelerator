from pyspark.sql.types import StringType, StructField, StructType


class SourceValuesSchema:
    MAPPING_FIELD_NAME_SOURCE_VALUE = "source_value"
    MAPPING_FIELD_NAME_TARGET_TABLE = "target_table"
    MAPPING_FIELD_NAME_TARGET_FIELD = "target_field"

    schema = StructType(
        [
            StructField(MAPPING_FIELD_NAME_SOURCE_VALUE, StringType(), False),
            StructField(MAPPING_FIELD_NAME_TARGET_TABLE, StringType(), False),
            StructField(MAPPING_FIELD_NAME_TARGET_FIELD, StringType(), False),
        ]
    )

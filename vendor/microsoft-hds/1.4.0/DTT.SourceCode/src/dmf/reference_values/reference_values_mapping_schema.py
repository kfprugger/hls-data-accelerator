from pyspark.sql.types import IntegerType, StringType, StructField, StructType


class ReferenceValuesMappingSchema:
    MAPPING_FIELD_NAME_SOURCE_DOMAIN = "source_domain"
    MAPPING_FIELD_NAME_SOURCE_VALUE = "source_value"
    MAPPING_FIELD_NAME_TARGET_TABLE = "target_table"
    MAPPING_FIELD_NAME_TARGET_FIELD = "target_field"
    MAPPING_FIELD_NAME_TARGET_VALUE = "target_value"

    SCHEMA = StructType([
        StructField(MAPPING_FIELD_NAME_SOURCE_DOMAIN, StringType(), False),
        StructField(MAPPING_FIELD_NAME_SOURCE_VALUE, StringType(), False),
        StructField(MAPPING_FIELD_NAME_TARGET_TABLE, StringType(), False),
        StructField(MAPPING_FIELD_NAME_TARGET_FIELD, StringType(), False),
        StructField(MAPPING_FIELD_NAME_TARGET_VALUE, IntegerType(), False),
    ])

from typing import List

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import IntegerType, StringType, StructField, StructType


class MappingSchema:
    MAPPING_FIELD_NAME_SOURCE_DOMAIN = "source_domain"
    MAPPING_FIELD_NAME_SOURCE_VALUE = "source_value"
    MAPPING_FIELD_NAME_TARGET_TABLE = "target_table"
    MAPPING_FIELD_NAME_TARGET_FIELD = "target_field"
    MAPPING_FIELD_NAME_TARGET_VALUE = "target_value"

    partitions: List[str] = [
        MAPPING_FIELD_NAME_SOURCE_DOMAIN,
        MAPPING_FIELD_NAME_TARGET_TABLE,
    ]
    schema = StructType(
        [
            StructField(MAPPING_FIELD_NAME_SOURCE_DOMAIN, StringType(), False),
            StructField(MAPPING_FIELD_NAME_SOURCE_VALUE, StringType(), False),
            StructField(MAPPING_FIELD_NAME_TARGET_TABLE, StringType(), False),
            StructField(MAPPING_FIELD_NAME_TARGET_FIELD, StringType(), False),
            StructField(MAPPING_FIELD_NAME_TARGET_VALUE, IntegerType(), False),
        ]
    )

    @staticmethod
    def check_dataframe_schema(mapping_df: DataFrame):
        for field in MappingSchema.schema:
            if field.name not in mapping_df.schema.names:
                raise Exception(f"Mapping dataframe schema is invalid, missing column '{field.name}'")
        for field in mapping_df.schema:
            if field.name not in MappingSchema.schema.names:
                raise Exception(f"Mapping dataframe schema is invalid, extra column '{field.name}'")
            if field.dataType != MappingSchema.schema[field.name].dataType:
                raise Exception(f"Mapping dataframe schema is invalid, column '{field.name}' has wrong schema type")
            if field.nullable != MappingSchema.schema[field.name].nullable:
                raise Exception(f"Mapping dataframe schema is invalid, column '{field.name}' has wrong nullable schema property")

    @staticmethod
    def adjust_to_schema(spark: SparkSession, mapping_df: DataFrame) -> DataFrame:
        expressions = []
        for field in MappingSchema.schema:
            expressions.append(f"CAST({field.name} AS {field.dataType.simpleString()})")
        mapping_df = mapping_df.selectExpr(*expressions)
        return spark.createDataFrame(mapping_df.rdd, MappingSchema.schema)

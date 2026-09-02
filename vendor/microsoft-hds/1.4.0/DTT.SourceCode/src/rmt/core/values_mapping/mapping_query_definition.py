from dataclasses import dataclass
from typing import List

import pyspark.sql.functions as F
from pyspark.sql import DataFrame, SparkSession

from rmt.core.values_mapping.mapping_definition import MappingDefinition
from rmt.core.values_mapping.mapping_schema import MappingSchema


@dataclass
class SourceMappingFile:
    file_path: str
    file_name: str

    def load(self, spark: SparkSession):
        df = spark.read.format("delta").load(self.file_path)
        df.createOrReplaceTempView(self.file_name)

    def __init__(self, file_path: str, file_name: str) -> None:
        self.file_path = file_path
        self.file_name = file_name

    def __str__(self) -> str:
        return f"SourceMappingFile(file_path={self.file_path}, " f"file_name={self.file_name})"


class MappingQueryDefinition(MappingDefinition):

    def __init__(self, target_table_name, target_field_name, sql: str, source_mapping_files: List[SourceMappingFile]) -> None:
        super().__init__(target_table_name, target_field_name)
        self.source_mapping_files = source_mapping_files
        self.sql = sql

    def to_mapping_dataframe(self, spark: SparkSession, source_domain: str) -> DataFrame:
        try:
            for source_mapping_file in self.source_mapping_files:
                source_mapping_file.load(spark)

            query_df = spark.sql(self.sql)

            mapping_df = (
                query_df.withColumn(MappingSchema.MAPPING_FIELD_NAME_SOURCE_DOMAIN, F.lit(source_domain))
                .withColumn(MappingSchema.MAPPING_FIELD_NAME_TARGET_TABLE, F.lit(self.target_table_name))
                .withColumn(MappingSchema.MAPPING_FIELD_NAME_TARGET_FIELD, F.lit(self.target_field_name))
            )

            mapping_df = MappingQueryDefinition.remove_null_target_values(mapping_df)
            mapping_df = MappingSchema.adjust_to_schema(spark, mapping_df)

            return mapping_df
        except Exception as e:
            raise Exception(f"Error converting reference data mapping definition to dataframe.{self}") from e

    def __str__(self):
        mapping_files_str = "".join(f"{self.source_mapping_files}")
        return (
            f"MappingDefinition(source_mapping_files={mapping_files_str}, "
            f"sql={self.sql}, "
            f"target_table_name={self.target_table_name}, "
            f"target_field_name={self.target_field_name}, "
            f"source_mapping_files={self.source_mapping_files})"
        )

    @staticmethod
    def remove_null_target_values(mapping_df: DataFrame) -> DataFrame:
        return mapping_df.where(f"{MappingSchema.MAPPING_FIELD_NAME_TARGET_VALUE} is not null")

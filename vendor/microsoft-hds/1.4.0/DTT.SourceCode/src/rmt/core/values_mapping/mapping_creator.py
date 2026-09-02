from typing import List

from pyspark.sql import DataFrame, SparkSession

from rmt.core.values_mapping.mapping_adder import MappingAdder
from rmt.core.values_mapping.mapping_definition import MappingDefinition
from rmt.core.values_mapping.mapping_schema import MappingSchema


class MappingCreator:

    @staticmethod
    def create(
        spark: SparkSession,
        source_domain: str,
        mapping_definitions: List[MappingDefinition],
    ) -> DataFrame:
        try:

            mapping_dataframe = spark.createDataFrame([], MappingSchema.schema)

            for mapping_definition in mapping_definitions:
                mapping_definition_dataframe = mapping_definition.to_mapping_dataframe(spark, source_domain)
                mapping_dataframe = MappingAdder.add(mapping_dataframe, mapping_definition_dataframe)

            return mapping_dataframe

        except Exception as e:
            raise Exception(f"Failed to create reference data mapping dataframe for Domain: '{source_domain}'") from e

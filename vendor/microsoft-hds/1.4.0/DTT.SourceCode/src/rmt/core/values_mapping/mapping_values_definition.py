from typing import List

from pyspark.sql import DataFrame, SparkSession

from rmt.core.values_mapping.mapping_definition import MappingDefinition
from rmt.core.values_mapping.mapping_schema import MappingSchema


class TargetMapping:
    target_key_value: int
    source_values: List[str]

    def __init__(self, target_key_value: int, source_values: List[str]) -> None:
        self.target_key_value = target_key_value
        self.source_values = source_values

    def __str__(self):
        return f"TargetMapping(target_key_value={self.target_key_value}, " f"source_values={self.source_values})"


class MappingValuesDefinition(MappingDefinition):

    def __init__(self, target_table_name: str, target_field_name: str, values: List[TargetMapping]) -> None:
        super().__init__(target_table_name, target_field_name)
        self.values = values

    def to_mapping_dataframe(self, spark: SparkSession, source_domain: str) -> DataFrame:
        try:

            if not self.values:
                return spark.createDataFrame([], MappingSchema.schema)

            flat_values = []
            for target_mapping in self.values:
                for source_value in target_mapping.source_values:
                    flat_values.append((target_mapping.target_key_value, source_value))
            all_values = [(source_domain, value[1], self.target_table_name, self.target_field_name, value[0]) for value in flat_values]

            mapping_df = spark.createDataFrame(all_values, MappingSchema.schema)

            MappingSchema.check_dataframe_schema(mapping_df)
            return mapping_df
        except Exception as e:
            raise Exception(f"Error converting values mapping definition to dataframe.{self}") from e

    def __str__(self):
        return (
            f"ValuesMappingDefinition(values={self.values})"
            f"target_table_name={self.target_table_name}, "
            f"target_field_name={self.target_field_name}) "
            f"values={self.values})"
        )

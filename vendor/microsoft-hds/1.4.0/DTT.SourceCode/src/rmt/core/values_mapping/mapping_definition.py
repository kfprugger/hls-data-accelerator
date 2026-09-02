from abc import ABC, abstractmethod

from pyspark.sql import DataFrame, SparkSession


class MappingDefinition(ABC):

    target_table_name: str
    target_field_name: str

    def __init__(self, target_table_name: str, target_field_name: str):
        self.target_table_name = target_table_name
        self.target_field_name = target_field_name

    @abstractmethod
    def to_mapping_dataframe(self, spark: SparkSession, source_domain: str) -> DataFrame:
        pass

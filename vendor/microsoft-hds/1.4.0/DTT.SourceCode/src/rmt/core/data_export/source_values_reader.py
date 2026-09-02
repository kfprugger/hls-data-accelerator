from abc import ABC, abstractmethod

from pyspark.sql import DataFrame


class SourceValuesReader(ABC):
    @abstractmethod
    def read_source_distinct_values(self) -> DataFrame:
        pass

    @abstractmethod
    def get_empty_distinct_values_df(self) -> DataFrame:
        pass

from abc import ABC, abstractmethod
from typing import Optional

from pyspark.sql import DataFrame, SparkSession

from common.model.data_access_definition import DataAccessDefinition
from common.utils.logging import Logger


class Reader(ABC):

    @abstractmethod
    def read(self, spark: SparkSession) -> Optional[DataFrame]:
        raise NotImplementedError(
            "Reader.read abstract method does not provide a default implementation"
        )

    @staticmethod
    def validate(df: DataFrame, data_access_definition: DataAccessDefinition) -> bool:
        if not df:
            Logger.warn(f"Could not access source data on {data_access_definition.data_source_id}")
            return False
        return True

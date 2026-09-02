from abc import ABC, abstractmethod

from pyspark.sql import DataFrame


class BaseProcessor(ABC):
    @abstractmethod
    def process(self) -> DataFrame:
        pass

    @abstractmethod
    def read(self, spark) -> bool:
        pass

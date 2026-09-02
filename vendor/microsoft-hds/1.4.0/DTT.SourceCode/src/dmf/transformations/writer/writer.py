from abc import ABC, abstractmethod
from typing import Optional

from pyspark.sql import DataFrame


class Writer(ABC):
    def __init__(self, id):
        if not id:
            raise ValueError("id must be provided")
        self.id = id

    @abstractmethod
    def write(self,
              df: DataFrame,
              partition_column: Optional[str] = None) -> None:
        raise NotImplementedError("Writer.write abstract method does not provide a default implementation")

from typing import Optional

from common.utils.logging import Logger
from pyspark.sql import DataFrame
from pyspark.sql.readwriter import DataFrameWriter

from dmf.transformations.writer.writer import Writer
from dmf.utils.logging_utils import Timed


class FirstTimeDeltaStorageWriter(Writer):

    def __init__(self, location: str, id):
        super().__init__(id)
        self.location: str = location
        self.data_format: str = "delta"

    def __str__(self) -> str:
        return f"FirstTimeStorageWriter[{self.id}]"

    @Timed(Logger)
    def write(self,
              df: DataFrame,
              partition_column: Optional[str] = None) -> None:

        # Fail if the table exists
        mode = "error"
        Logger.info(f"{self} Writing data to storage. path: '{self.location}', format: '{self.data_format}', mode: '{mode}'")

        df_writer: DataFrameWriter = df \
            .write \
            .mode(mode) \
            .format(self.data_format)

        if partition_column:
            df_writer = df_writer.partitionBy(partition_column)

        try:
            df_writer.save(self.location)
        except Exception as e:
            Logger.error(f"Error while writing data to {self.location} for first time. "
                         f"Context: {self}: {e}")
            raise

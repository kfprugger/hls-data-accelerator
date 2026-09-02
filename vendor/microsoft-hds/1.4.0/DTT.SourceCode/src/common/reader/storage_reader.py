from typing import Optional

from pyspark.sql import DataFrame, SparkSession

from common.reader.reader import Reader
from common.utils.logging import Logger


class StorageReader(Reader):

    def __init__(self, location: str, data_format: str):
        self.location = location
        self.format = data_format

    def read(self, spark: SparkSession) -> Optional[DataFrame]:
        df = None
        try:
            df = spark.read.format(self.format).load(self.location)
        except Exception as e:
            Logger.warn(
                f"Could not read data from '{self.location}', "
                f"Exception: {e}"
            )
        finally:
            return df

    def __str__(self):
        return f"StorageReader{{location={self.location}, format={self.format}}}"

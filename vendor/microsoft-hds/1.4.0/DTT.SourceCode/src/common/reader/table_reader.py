from pyspark.sql import DataFrame, SparkSession
from typing_extensions import Optional

from common.reader.reader import Reader
from common.utils.logging import Logger


class TableReader(Reader):
    def __init__(self, db: str, table: str):
        self._db = db
        self._table = table

    def read(self, spark: SparkSession) -> Optional[DataFrame]:
        table_expression = f"{self._db}.{self._table}"
        df = None
        try:
            df = spark.read.table(table_expression)
        except Exception as e:
            Logger.warn(f"Could not read data from '{self._db}.{self._table}', "
                        f"Exception: {e}")
        finally:
            return df

    def __str__(self):
        return f"TableReader{{db={self._db}, table={self._table}}}"

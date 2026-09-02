from typing import Optional

from pyspark.sql import DataFrame, SparkSession

from common.reader.reader import Reader
from common.utils.logging import Logger


class QueryReader(Reader):

    def __init__(self, db: str, query: str):
        self._db = db
        self._query = query

    def read(self, spark: SparkSession) -> Optional[DataFrame]:
        df = None
        try:
            if self._db:
                spark.sql(f"USE {self._db}")  # TODO: change the context to be only for this query
            df = spark.sql(self._query)
        except Exception as e:
            Logger.warn(f"QueryReader failed to read query '{self._query}' from db '{self._db}', "
                        f"Exception: {e}")
        finally:
            return df

    def __str__(self):
        return f"QueryReader{{db={self._db}, query={self._query}}}"

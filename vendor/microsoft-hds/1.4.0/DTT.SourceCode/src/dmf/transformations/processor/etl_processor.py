import time
import traceback
from abc import abstractmethod

from pyspark.sql import DataFrame, SparkSession

from common.utils.logging import Logger
from dmf.transformations.processor.base_processor import BaseProcessor
from dmf.utils.logging_utils import SyntheticId


@SyntheticId
class ETLProcessor(BaseProcessor):

    def __init__(self, spark: SparkSession):
        self.spark = spark

    @abstractmethod
    def read(self) -> DataFrame:
        raise NotImplementedError()

    @abstractmethod
    def _transform(self, df: DataFrame) -> DataFrame:
        raise NotImplementedError()

    @abstractmethod
    def _write(self, df: DataFrame):
        raise NotImplementedError()

    def process(self):
        try:
            start = time.time()
            Logger.info(f"Starting ETL process. {self}")

            raw_data = self.read()
            transformed_data = self._transform(raw_data)
            self._write(transformed_data)

            elapsed_time = time.time() - start
            Logger.info(f"Completed ETL processing {self}. Duration: {elapsed_time:.2f} sec")

        except Exception as e:
            Logger.error(f"Error while processing {self}. {e}")
            Logger.error(traceback.format_exc())
            raise

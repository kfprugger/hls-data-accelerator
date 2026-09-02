from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from pyspark.sql import DataFrame, SparkSession

from common.model.data_access_definition import DataAccessDefinition
from dmf.model.source_configuration import SourceConfiguration
from common.utils.logging import Logger
from common.reader.reader_factory import ReaderFactory
from dmf.utils.global_constants import GlobalConstants
from dmf.utils.logging_utils import SyntheticId, Timed
from dmf.utils.utils import parallel_process


@SyntheticId
class LastProcessedLineCalculator:
    def __init__(self, spark: SparkSession):
        self.spark = spark

    @staticmethod
    def _compute_last_processed_line(unique_source_config_id: str, df: DataFrame, source_table_column_name: str) -> datetime:
        if unique_source_config_id is None:
            raise ValueError("LastProcessedLineCalculator._compute_last_processed_line: unique_source_config_id is None")

        last_source_modified_on = df.filter(f"{source_table_column_name}='{unique_source_config_id}'").selectExpr("MAX(SourceModifiedOn) as max").collect()[0].max
        return last_source_modified_on or GlobalConstants.MIN_DATE

    def _read_table(self, data_access_definitions: DataAccessDefinition) -> DataFrame:
        reader = ReaderFactory.get_instance(data_access_definitions)
        return reader.read(spark=self.spark)

    def _get_last_source_modified_on(self,
                                     source_config: SourceConfiguration,
                                     data_access_definition: DataAccessDefinition,
                                     source_table_column_name: str):
        table_df = self._read_table(data_access_definition)
        if table_df:
            return LastProcessedLineCalculator._compute_last_processed_line(source_config.unique_id, table_df, source_table_column_name)

        return GlobalConstants.MIN_DATE

    @Timed(Logger)
    def compute_last_processed_line_in_source_table(self,
                                                    executor: Optional[Executor],
                                                    source_config: SourceConfiguration) -> datetime:
        if not source_config.target_configurations:
            raise ValueError(f"no target configurations found in {source_config}")
        data_access_definitions: list[DataAccessDefinition] = [tc.data_access_definition for tc in source_config.target_configurations]

        if not executor:
            executor = ThreadPoolExecutor(max_workers=len(data_access_definitions), thread_name_prefix="last_processed_line_computer")

        def _get_last_source_modified_on(data_access_definition):
            return self._get_last_source_modified_on(source_config, data_access_definition, source_config.source_table_column_name)
        return parallel_process(executor, _get_last_source_modified_on, data_access_definitions, aggregator=max)

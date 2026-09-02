from pyspark.sql import DataFrame, SparkSession

from common.model.base_source_configuration import BaseSourceConfiguration
from common.processor.base_processor import BaseProcessor
from common.processor.steps.column_expression_builder import ColumnExpressionBuilder
from common.processor.steps.column_selector import ColumnSelector


class BaseSourceProcessor(BaseProcessor):

    def __init__(self, spark: SparkSession, source_config: BaseSourceConfiguration):
        self.source_config: BaseSourceConfiguration = source_config
        self._spark: SparkSession = spark
        self.df: DataFrame = None
        self.is_empty: bool = False

    def _build_column_expressions(self) -> DataFrame:
        return ColumnExpressionBuilder.build_column_expressions(self.df, list(self.source_config.table_schema.columns))

    def _select_specific_columns(self) -> DataFrame:
        return ColumnSelector.select_specific_columns(self.df, list(self.source_config.table_schema.columns))

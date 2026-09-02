from typing import List

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from common.exceptions.processor.steps.column_expression_builder_exceptions import ColumnAlreadyExistsException, SourceFieldNameMustBeNonEmptyException
from common.model.base_source_configuration import BaseTableColumn
from common.utils.data_frame_utils import DataFrameUtils


class ColumnExpressionBuilder:

    @staticmethod
    def build_column_expressions(df: DataFrame, columns: List[BaseTableColumn]) -> DataFrame:
        if df is None:
            raise ValueError("Error in building source column expressions. df is None")
        for source_field in columns:
            if source_field.expression is not None:
                if source_field.name is None:
                    raise SourceFieldNameMustBeNonEmptyException(f"Error in building source column expressions. source field name must be non empty: {source_field}")
                if source_field.name in df.columns:
                    raise ColumnAlreadyExistsException(f"Error in building source column expressions. Column {source_field.name} already exists in df: {df.columns}")
                df = DataFrameUtils.with_column_fast(df, source_field.name, F.expr(source_field.expression))
        return df

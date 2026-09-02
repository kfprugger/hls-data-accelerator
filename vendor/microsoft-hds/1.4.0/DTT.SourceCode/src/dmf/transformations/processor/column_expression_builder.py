from typing import List

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from dmf.model.target_configuration.target_table_schema import TableColumn
from dmf.utils.dataframe_utils import DataFrameUtils


class ColumnExpressionBuilder:

    @staticmethod
    def build_column_expressions(df: DataFrame, columns: List[TableColumn]) -> List[str]:
        for source_field in columns:
            if source_field.expression is not None:
                if source_field.name is None:
                    raise ValueError(f"Error in buidling source column expressions. source field name must be non empty: {source_field}")
                if source_field.name in df.columns:
                    raise ValueError(f"Error in buidling source column expressions. Column {source_field.name} already exists in df: {df.columns}")
                df = DataFrameUtils.with_column_fast(df, source_field.name, F.expr(source_field.expression))
        return df

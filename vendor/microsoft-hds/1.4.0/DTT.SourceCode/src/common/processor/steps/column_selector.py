from typing import List

from pyspark.sql import DataFrame

from common.exceptions.processor.steps.column_selector_exceptions import SourceFieldNameMustBeNonEmptyException
from common.model.base_source_configuration import BaseTableColumn


class ColumnSelector:
    @staticmethod
    def select_specific_columns(df: DataFrame, columns: List[BaseTableColumn]) -> DataFrame:
        if df is None:
            raise ValueError("Error in selecting specific columns. df is None")
        if not columns:
            raise ValueError("Error in selecting specific columns. columns list is empty")
        select_expressions = ColumnSelector._build_column_casting(columns)
        return df.selectExpr(*select_expressions)

    @staticmethod
    def _build_column_casting(columns: List[BaseTableColumn]) -> List[str]:
        expressions = []
        for source_field in columns:
            if source_field.name is None:
                raise SourceFieldNameMustBeNonEmptyException(f"name must be non empty: {source_field}")
            spark_sql_type = source_field.type.simpleString()
            expression = f"CAST({source_field.name} AS {spark_sql_type}) AS {source_field.name}"
            expressions.append(expression)
        return expressions

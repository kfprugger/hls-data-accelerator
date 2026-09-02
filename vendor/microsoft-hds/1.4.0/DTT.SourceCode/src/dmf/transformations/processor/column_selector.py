from typing import List
from pyspark.sql import DataFrame
from dmf.model.target_configuration.target_table_schema import TableColumn


class ColumnSelector:
    @staticmethod
    def select_specific_columns(df: DataFrame, columns: List[TableColumn]) -> DataFrame:
        select_expressions = ColumnSelector._build_column_casting(columns)
        return df.selectExpr(*select_expressions)

    @staticmethod
    def _build_column_casting(columns: List[TableColumn]) -> List[str]:
        expressions = []
        for source_field in columns:
            if source_field.name is None:
                raise ValueError(f"name must be non empty: {source_field}")
            spark_sql_type = source_field.type.simpleString()
            expression = f"CAST({source_field.name} AS {spark_sql_type}) AS {source_field.name}"
            expressions.append(expression)
        return expressions

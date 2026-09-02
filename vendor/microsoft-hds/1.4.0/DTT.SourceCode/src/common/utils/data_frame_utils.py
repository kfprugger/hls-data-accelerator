from pyspark.sql import Column, DataFrame


class DataFrameUtils:
    @staticmethod
    def with_column_fast(df: DataFrame, column_name: str, column: Column) -> DataFrame:
        return df.select("*", column.alias(column_name))

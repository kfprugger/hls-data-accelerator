from typing import List

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F


class LatestChangeFilter:
    @staticmethod
    def filter(df: DataFrame, key_col_names: List[str], modified_col_name: str) -> DataFrame:
        """reduce that for latest change per day"""
        partitioning_cols = [F.col(col_name)
                             for col_name in key_col_names]
        spec = Window.partitionBy(
            *partitioning_cols).orderBy(F.col(modified_col_name).desc())
        df_with_row_num = df.select(
            '*', F.row_number().over(spec).alias('row'))
        return df_with_row_num.filter(F.col("row") == 1).drop("row")

from typing import List

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F


class IntraDayLatestChangeFilter:
    @staticmethod
    def filter(df: DataFrame, key_col_names: List[str], modified_col_name: str) -> DataFrame:
        """reduce that for one change a day (last one) to get less noise"""
        df_with_mod_date = df.select('*', F.to_date(F.col(modified_col_name)).alias('mod_date'))
        partitioning_cols = [F.col(col_name) for col_name in key_col_names + ["mod_date"]]
        spec = Window.partitionBy(*partitioning_cols).orderBy(F.col(modified_col_name).desc())
        df_with_row_num = df_with_mod_date.select('*', F.row_number().over(spec).alias('row'))
        return df_with_row_num.filter(F.col("row") == 1).drop("row", "mod_date")

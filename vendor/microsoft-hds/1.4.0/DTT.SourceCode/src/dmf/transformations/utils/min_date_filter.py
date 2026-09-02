from datetime import datetime

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


class MinDateFilter:
    @staticmethod
    def filter(df: DataFrame, min_date: datetime, date_col_name: str) -> DataFrame:
        timestamp_column = F.to_timestamp(F.lit(str(min_date)))
        return df.where(timestamp_column < F.col(date_col_name))

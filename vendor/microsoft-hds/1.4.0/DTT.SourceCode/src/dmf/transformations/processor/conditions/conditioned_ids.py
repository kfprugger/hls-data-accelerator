from functools import reduce
from typing import List

from pyspark.sql import DataFrame


class ConditionedNullIdsFilter:
    @staticmethod
    def filter(source_df: DataFrame, source_ids_with_conditions: List[str]) -> DataFrame:
        for column_name in source_ids_with_conditions:
            if column_name not in source_df.columns:
                raise ValueError(f"Column '{column_name}' not in source_df")

        return reduce(
            lambda df, column_name: df.filter(df[column_name].isNotNull()),
            source_ids_with_conditions,
            source_df)

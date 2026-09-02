from pyspark.sql import DataFrame


class TargetUnifier:

    @staticmethod
    def union(target_unchanged_df: DataFrame, target_and_source_in_range_df: DataFrame) -> DataFrame:
        common_columns = set(target_unchanged_df.columns) & set(target_and_source_in_range_df.columns)
        formatted_target_and_source_df = target_and_source_in_range_df.select(*common_columns)
        result_df = target_unchanged_df.unionByName(formatted_target_and_source_df, allowMissingColumns=True)
        return result_df

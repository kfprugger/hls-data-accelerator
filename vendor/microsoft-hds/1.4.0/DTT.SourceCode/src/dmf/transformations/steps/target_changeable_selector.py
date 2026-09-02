from typing import List

import pyspark.sql.functions as F
from pyspark.sql import DataFrame, Window

ROW_NUM_COLUMN_NAME: str = "rownum"


class TargetChangeableSelector:
    @staticmethod
    def get_changeable(source_partitioned_df: DataFrame, target_filtered_df: DataFrame, key_col_names: List[str], ordering_col_name: str) -> DataFrame:
        """
        This method receives source dataframe (with partitions), target dataframe (filtered by those partitions)
        source to target key mapping and ordering col name
        The method returns target dataframe rows which are changeable:
        from target rows related to source return the last rows (by ordering col name desc)
        """
        target_related_to_source_df = TargetChangeableSelector.get_related_to_source(source_partitioned_df, target_filtered_df, key_col_names)
        target_changeable_df = TargetChangeableSelector._get_last_records(target_related_to_source_df, key_col_names, ordering_col_name)
        return target_changeable_df

    @staticmethod
    def get_related_to_source(source_partitioned_df: DataFrame, target_filtered_df: DataFrame, key_col_names: List[str]) -> DataFrame:
        """
        This method receives source dataframe (with partitions),
        target dataframe (filtered by those partitions) and source to target key mapping.
        The method returns all target dataframe rows which are related to source - same key/s values
        """
        return target_filtered_df.join(source_partitioned_df, on=key_col_names, how="leftsemi")

    @staticmethod
    def get_unrelated_to_source(source_partitioned_df: DataFrame, target_filtered_df: DataFrame, key_col_names: List[str]) -> DataFrame:
        """
        This method receives source dataframe (with partitions),
        target dataframe (filtered by those partitions) and source to target key mapping.
        The method returns all target dataframe rows which are not related to source - not same key/s values
        """
        return target_filtered_df.join(source_partitioned_df, on=key_col_names, how="leftanti")

    @staticmethod
    def _get_last_records(target_related_df: DataFrame, key_col_names: List[str], ordering_col_name: str) -> DataFrame:
        """
        This method receives target dataframe(which are related to source),
        target key column names and ordering col name.
        the method returns all target dataframe rows which are last(by ordering col name desc)
        """
        target_partitioned = TargetChangeableSelector._get_target_partitioned_by_key_cols_with_row_num(
            target_related_df, key_col_names, ordering_col_name)
        return target_partitioned.filter(F.col(ROW_NUM_COLUMN_NAME) == 1).drop(ROW_NUM_COLUMN_NAME)

    @staticmethod
    def _get_not_last_records(target_related_df: DataFrame, key_col_names: List[str], ordering_col_name: str) -> DataFrame:
        """
        This method receives target dataframe (which are related to source),
        target key column names and ordering col name.
        the method returns all target dataframe rows which are not last (by ordering col name desc)
        """
        target_partitioned = TargetChangeableSelector._get_target_partitioned_by_key_cols_with_row_num(
            target_related_df,
            key_col_names,
            ordering_col_name)
        return target_partitioned.filter(F.col(ROW_NUM_COLUMN_NAME) != 1).drop(ROW_NUM_COLUMN_NAME)

    @staticmethod
    def _get_target_partitioned_by_key_cols_with_row_num(target_related_df: DataFrame, key_col_names: List[str], ordering_col_name: str) -> DataFrame:
        spec = Window.partitionBy(*key_col_names).orderBy(F.col(ordering_col_name).desc())
        return target_related_df.select('*', F.row_number().over(spec).alias(ROW_NUM_COLUMN_NAME))

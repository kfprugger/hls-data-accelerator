from typing import List

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F


class DuplicatesFilter:
    ROW_NUM_COLUMN_NAME: str = "rownum"

    @staticmethod
    def filter(df: DataFrame, key_col_names: List[str], data_col_names: List[str], ordering_col_name: str,
               keep_latest: bool = False) -> DataFrame:
        """
        This method assumes that it receives a DataFrame that contains only 1 update per day per a PK.
        The method identifies repeating values in 'data_col_names' columns and leaves only the most recent record
        if keep_latest=true, otherwise leaves only the oldest record
        """
        if not df:
            raise ValueError("Source Dataframe is not defined")

        if not key_col_names:
            raise ValueError("Key columns list cannot be empty")

        if not data_col_names:
            raise ValueError("Data columns list cannot be empty")

        if not ordering_col_name:
            raise ValueError("Ordering column name is not defined")

        partitioning_cols = [F.col(col_name) for col_name in key_col_names]
        adjacent_values_enriched_df = DuplicatesFilter._fill_adjacent_values(
            df,
            partitioning_cols,
            data_col_names,
            ordering_col_name,
            keep_latest)
        row_numbered_df = DuplicatesFilter._enrich_row_number(
            adjacent_values_enriched_df,
            partitioning_cols,
            ordering_col_name,
            keep_latest)

        joined_filter = " ".join([
            DuplicatesFilter._non_repeating_entries_filter(data_col_names, keep_latest),
            "or",
            DuplicatesFilter._first_entry_in_partition_filter()
        ]
        )

        final_df = row_numbered_df.filter(joined_filter).select(df.columns)
        return final_df

    @staticmethod
    def _first_entry_in_partition_filter() -> str:
        return f"{DuplicatesFilter.ROW_NUM_COLUMN_NAME} == 1"

    @staticmethod
    def _non_repeating_entries_filter(data_col_names: List[str], keep_latest: bool) -> str:
        filters = []
        for data_col_name in data_col_names:
            filters.append(
                f"{data_col_name} <=> {DuplicatesFilter._adjacent_value_col_name(data_col_name, keep_latest)}")
        return "not(" + " AND ".join(filters) + ")"

    @staticmethod
    def _enrich_row_number(df: DataFrame, partitioning_cols: List[Column], ordering_col_name: str,
                           keep_latest: bool) -> DataFrame:
        """
        This method uses Window to order records for partitions defined by 'partitioning_cols'
        orders them in a reverse order and adds rownum. The entry with rownum = 1 is the first entry in the partition
        """
        if keep_latest:
            ordered_column = F.col(ordering_col_name).desc()
        else:
            ordered_column = F.col(ordering_col_name).asc()

        window = Window.partitionBy(*partitioning_cols).orderBy(ordered_column)
        df_with_row_num = df.select('*', F.row_number().over(window).alias(DuplicatesFilter.ROW_NUM_COLUMN_NAME))
        return df_with_row_num

    @staticmethod
    def _fill_adjacent_values(df: DataFrame, partitioning_cols: List[Column], data_col_names: List[str],
                              ordering_col_name: str, keep_latest: bool) -> DataFrame:
        """
        This method uses Window to enrich given 'df' DataFrame with data values of the adjacent record
        """
        if keep_latest:
            ordered_column = F.col(ordering_col_name).asc()
        else:
            ordered_column = F.col(ordering_col_name).desc()

        window = Window.partitionBy(*partitioning_cols).orderBy(ordered_column)

        extended_df = df
        for data_col_name in data_col_names:
            extended_df = extended_df.select(
                "*",
                F.lead(F.col(data_col_name))
                .over(window)
                .alias(DuplicatesFilter._adjacent_value_col_name(data_col_name, keep_latest))
            )

        return extended_df

    @staticmethod
    def _adjacent_value_col_name(orig_col_name: str, keep_latest: bool) -> str:
        if keep_latest:
            return f"next_{orig_col_name}"
        return f"previous_{orig_col_name}"

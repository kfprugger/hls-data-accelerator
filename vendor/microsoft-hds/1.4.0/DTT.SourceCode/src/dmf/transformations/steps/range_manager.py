from functools import lru_cache
from typing import List

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

from dmf.transformations.steps.activeness_status_enricher import ActivenessStatusEnricher
from dmf.utils.dataframe_utils import DataFrameUtils
from dmf.utils.global_constants import GlobalConstants


class RangeManager:
    DATA_EQUALS = 1

    @staticmethod
    def calculate_range(df: DataFrame,
                        key_col_names: List[str],
                        data_column_names: List[str],
                        timestamp_col_name: str,
                        range_start_col_name: str,
                        range_end_col_name: str) -> DataFrame:
        spec = Window.partitionBy(*key_col_names).orderBy(F.col(timestamp_col_name).asc())

        # add 2 columns for prior and next timestamps
        preceding_row_order_col_name = "_last_ts"
        following_row_order_col_name = "_next_ts"
        data_equals_column_name = "data_equals"
        prev_data_column_names = [name + "_prev" for name in data_column_names]

        prev_data_columns = [F.lag(orig_data_column_name).over(spec).alias(prev_data_column_name) for
                             (orig_data_column_name, prev_data_column_name) in
                             zip(data_column_names, prev_data_column_names)]

        df = df.select('*',
                       F.lag(timestamp_col_name).over(spec).alias(preceding_row_order_col_name),
                       F.lead(timestamp_col_name).over(spec).alias(following_row_order_col_name),
                       *prev_data_columns,
                       F.lit(RangeManager.DATA_EQUALS).alias(data_equals_column_name)
                       )

        temp_data_eq_column_name = data_equals_column_name + "_temp"
        data_equals_column = F.col(data_equals_column_name)
        for (orig_data_column_name, prev_data_column_name) in zip(data_column_names, prev_data_column_names):
            orig_data_column = df[orig_data_column_name]
            prev_data_column = df[prev_data_column_name]
            df = df.drop(temp_data_eq_column_name)
            df = df.select("*",
                           ((orig_data_column.eqNullSafe(prev_data_column)).
                            cast(IntegerType().simpleString()) * data_equals_column).
                           alias(temp_data_eq_column_name))
            df = DataFrameUtils.swap_columns(df, data_equals_column_name, temp_data_eq_column_name)

        # compute the 2 new start and end timestamps
        new_range_start_col_name = "_new_" + range_start_col_name
        new_range_end_col_name = "_new_" + range_end_col_name
        new_timestamp_col_name = "_new_" + timestamp_col_name

        df_recalculated = (
            df
            .select('*',
                    RangeManager._compute_start_time(
                        F.col(range_start_col_name),
                        F.col(preceding_row_order_col_name),
                        F.col(timestamp_col_name)).alias(new_range_start_col_name),
                    RangeManager._compute_end_time(
                        F.col(range_end_col_name),
                        F.col(following_row_order_col_name),
                        F.col(timestamp_col_name)).alias(new_range_end_col_name),
                    RangeManager._compute_timestamp(
                        F.col(timestamp_col_name),
                        F.col(following_row_order_col_name),
                        F.col(data_equals_column_name)).
                    alias(new_timestamp_col_name)))

        df_without_redundant_inactive = df_recalculated \
            .where(RangeManager._is_entry_enabled() |
                   (~RangeManager._is_entry_enabled() &
                    ~df_recalculated[data_equals_column_name].eqNullSafe(F.lit(RangeManager.DATA_EQUALS))))

        df_final = df_without_redundant_inactive. \
            drop(preceding_row_order_col_name,
                 following_row_order_col_name,
                 range_start_col_name,
                 range_end_col_name,
                 timestamp_col_name,
                 *prev_data_column_names,
                 ActivenessStatusEnricher.CALCULATED_ACTIVENESS_STATUS_COLUMN_NAME,
                 data_equals_column_name,
                 temp_data_eq_column_name) \
            .withColumnRenamed(new_range_start_col_name, range_start_col_name) \
            .withColumnRenamed(new_range_end_col_name, range_end_col_name) \
            .withColumnRenamed(new_timestamp_col_name, timestamp_col_name)

        return df_final

    @staticmethod
    def _is_active(active_status_col: Column):
        return active_status_col.isNull() | (active_status_col == GlobalConstants.ACTIVE_VALUE)

    @staticmethod
    def _not_deleted(deleted_status_col: Column):
        return deleted_status_col.isNull() | (deleted_status_col == False)  # noqa: E712

    @staticmethod
    def _compute_start_time(existing_start_col: Column, preceding_timestamp: Column, timestamp_col: Column) -> Column:
        start_of_time_col = RangeManager._to_timestamp_col(GlobalConstants.START_OF_TIME_DATE)
        return (
            F.when(existing_start_col.isNotNull(), existing_start_col)  # never re-calculate start timestamp
            .when(preceding_timestamp.isNotNull(), timestamp_col)  # non-first line
            .otherwise(start_of_time_col))  # first line

    @staticmethod
    def _compute_end_time(existing_end_timestamp: Column, next_modifiedon: Column,
                          modified_on_column: Column) -> Column:
        end_of_time_col = RangeManager._to_timestamp_col(GlobalConstants.END_OF_TIME_DATE)
        return (
            F.when(existing_end_timestamp != end_of_time_col, existing_end_timestamp)  # never closed a closed line
            .when(~RangeManager._is_entry_enabled(), modified_on_column)  # close the line if it is not enabled
            .when(next_modifiedon.isNull(), end_of_time_col)  # last line
            .otherwise(next_modifiedon - F.expr("INTERVAL 1 day")))

    @staticmethod
    def _is_entry_enabled() -> Column:
        return F.col(ActivenessStatusEnricher.CALCULATED_ACTIVENESS_STATUS_COLUMN_NAME).eqNullSafe(
            F.lit(ActivenessStatusEnricher.ACTIVENESS_STATUS_ENABLED)
        )

    @staticmethod
    def _compute_timestamp(modified_on: Column, next_modified_on: Column,
                           data_equals_column: Column) -> Column:
        return (
            F.when(next_modified_on.isNull()
                   & ~RangeManager._is_entry_enabled()
                   & ~data_equals_column.eqNullSafe(F.lit(RangeManager.DATA_EQUALS)), modified_on)
            .when(~RangeManager._is_entry_enabled()
                  & data_equals_column.eqNullSafe(F.lit(RangeManager.DATA_EQUALS))
                  & next_modified_on.isNotNull(), modified_on)
            .when((next_modified_on.isNull() & RangeManager._is_entry_enabled()) | next_modified_on.isNotNull(),
                  modified_on)
            .otherwise(next_modified_on))

    @staticmethod
    @lru_cache
    def _to_timestamp_col(timestamp: str) -> Column:
        return F.to_timestamp(F.lit(timestamp))

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

from dmf.utils.global_constants import GlobalConstants


class ActivenessStatusEnricher:
    CALCULATED_ACTIVENESS_STATUS_COLUMN_NAME = "calculated_activeness_status"
    ACTIVENESS_STATUS_ENABLED = 1
    ACTIVENESS_STATUS_DISABLED = 0

    @staticmethod
    def enrich_target(df: DataFrame, activeness_period_end_column_name: str):

        if activeness_period_end_column_name:
            activeness_status_column = ActivenessStatusEnricher. \
                _calc_activeness_status_by_period_end_date(df[activeness_period_end_column_name])
        else:
            activeness_status_column = ActivenessStatusEnricher._cast_and_rename(
                F.lit(ActivenessStatusEnricher.ACTIVENESS_STATUS_ENABLED))

        return \
            df.select("*", activeness_status_column)

    @staticmethod
    def enrich_source(df: DataFrame,
                      active_status_column_name: str,
                      deleted_status_column_name: str) -> DataFrame:

        if active_status_column_name and deleted_status_column_name:
            activeness_status_column = ActivenessStatusEnricher._calc_activeness_status_by_src_status(
                df[active_status_column_name], df[deleted_status_column_name])
        else:
            activeness_status_column = ActivenessStatusEnricher._cast_and_rename(
                F.lit(ActivenessStatusEnricher.ACTIVENESS_STATUS_ENABLED))

        return df.select("*", activeness_status_column)

    @staticmethod
    def _calc_activeness_status_by_period_end_date(activeness_period_end_column: Column) -> Column:
        end_of_time_column = F.to_timestamp(F.lit(GlobalConstants.END_OF_TIME_DATE))

        return ActivenessStatusEnricher. \
            _cast_and_rename(F.when(activeness_period_end_column == end_of_time_column,
                                    F.lit(ActivenessStatusEnricher.ACTIVENESS_STATUS_ENABLED))
                             .otherwise(F.lit(ActivenessStatusEnricher.ACTIVENESS_STATUS_DISABLED))
                             )

    @staticmethod
    def _calc_activeness_status_by_src_status(src_active_status_column: Column, src_deleted_status_column: Column):
        active_status_column = F.lit(GlobalConstants.ACTIVE_VALUE)
        return ActivenessStatusEnricher. \
            _cast_and_rename(F.when((active_status_column == src_active_status_column) & ~src_deleted_status_column,
                                    F.lit(ActivenessStatusEnricher.ACTIVENESS_STATUS_ENABLED))
                             .otherwise(F.lit(ActivenessStatusEnricher.ACTIVENESS_STATUS_DISABLED))
                             )

    @staticmethod
    def _cast_and_rename(column: Column):
        return column \
            .cast(IntegerType().simpleString()) \
            .alias(ActivenessStatusEnricher.CALCULATED_ACTIVENESS_STATUS_COLUMN_NAME)

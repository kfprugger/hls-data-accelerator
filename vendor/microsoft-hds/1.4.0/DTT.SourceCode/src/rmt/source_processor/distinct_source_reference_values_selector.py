from typing import FrozenSet

from common.exceptions.base_dtt_common_exception import BaseDttCommonCustomException
from common.model.source_to_reference_mapping import SourceToReferenceMapping
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, lit

from rmt.core.data_export.source_values_schema import SourceValuesSchema


class BaseDistinctSourceReferenceValuesSelectorException(BaseDttCommonCustomException):
    """Base class for custom exceptions in DistinctSourceReferenceValuesSelector."""

    pass


class ColumnDoesNotExistException(BaseDistinctSourceReferenceValuesSelectorException):
    """Exception raised when a column doesn't exist in the DataFrame."""

    pass


class DistinctSourceReferenceValuesSelector:
    @staticmethod
    def get_distinct_values(df: DataFrame, source_to_reference_mappings: FrozenSet[SourceToReferenceMapping]) -> DataFrame:
        result_df: DataFrame = None
        for source_to_reference_mapping in source_to_reference_mappings:
            source_col_to_map = source_to_reference_mapping.source_field_name

            try:
                distinct_values_df = df.select(source_col_to_map).where(col(source_col_to_map).isNotNull()).distinct()
            except Exception:
                raise ColumnDoesNotExistException(f"Column {source_col_to_map} doesn't exist on df: {df.columns}")

            if result_df is None:
                result_df = DistinctSourceReferenceValuesSelector._create_distinct_df(distinct_values_df, source_col_to_map, source_to_reference_mapping)
            else:
                result_df = result_df.unionByName(DistinctSourceReferenceValuesSelector._create_distinct_df(distinct_values_df, source_col_to_map, source_to_reference_mapping))
        return result_df

    @staticmethod
    def _create_distinct_df(distinct_values_df: DataFrame, source_col_to_map: str, source_to_reference_mapping: SourceToReferenceMapping) -> DataFrame:
        return (
            distinct_values_df.select(col(source_col_to_map).alias(SourceValuesSchema.MAPPING_FIELD_NAME_SOURCE_VALUE))
            .withColumn(SourceValuesSchema.MAPPING_FIELD_NAME_TARGET_TABLE, lit(source_to_reference_mapping.target_reference_table_name))
            .withColumn(SourceValuesSchema.MAPPING_FIELD_NAME_TARGET_FIELD, lit(source_to_reference_mapping.target_reference_field_name))
        )

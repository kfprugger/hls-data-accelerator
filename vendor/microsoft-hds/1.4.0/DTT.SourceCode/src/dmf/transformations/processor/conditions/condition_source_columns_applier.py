from typing import List, Tuple, Union

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from dmf.model.source_configuration import SourceConfiguration
from dmf.model.target_configuration.target_table_schema import TableColumn
from dmf.utils.dataframe_utils import DataFrameUtils


class ConditionedSourceColumnsApplier:
    """for each condition column, add a new column with the condition applied to the original column.add()
    The condition expression evaluates to either the original column value or NULL.
    In case the column is reference value it should be mapped to the default reference value instaed of NULL,
    the default_reference_value is passed as a parameter therefore.
    This is done since several targets may refer to the same source columns. The different mappings
    to those target use source_field_name property so that each target refers to a different column.

    """

    def __init__(self, spark: SparkSession, target_config: SourceConfiguration, source_df: DataFrame, default_reference_value: Union[int, None]):
        self._config: SourceConfiguration = target_config
        self._df: DataFrame = source_df
        self._spark: SparkSession = spark
        self._added_columns = []
        self.default_reference_value_str = "NULL" if default_reference_value is None else str(default_reference_value)

    def apply(self) -> Tuple[DataFrame, List[TableColumn]]:
        self._nullify_false_condition_columns_on_attributes()
        return self._df, self._added_columns

    def _nullify_false_condition_columns_on_attributes(self) -> None:

        ref_source_field_names = [source_to_reference_mapping.source_field_name for source_to_reference_mapping in self._config.source_to_reference_mappings]
        for column_transformation in self._config.all_column_transformations:
            if column_transformation.target_field_value is not None:
                continue  # literal values are already added as columns
            false_condition_value = self.default_reference_value_str if column_transformation.original_source_field_name in ref_source_field_names else "NULL"
            if column_transformation.target_field_condition is not None:
                expression = (
                    f"CASE WHEN {column_transformation.target_field_condition} "
                    f"THEN {column_transformation.original_source_field_name} "
                    f"ELSE {false_condition_value} "
                    "END")

                self._df = DataFrameUtils.with_column_fast(self._df, column_transformation.source_field_name, F.expr(expression))
                self._added_columns.append(TableColumn(
                    name=column_transformation.source_field_name,
                    type=column_transformation.source_field_type,
                    is_nullable=False,
                    expression=None,
                    is_fk_to_ref_table=False))

from typing import List, Tuple

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from dmf.model.source_configuration import SourceConfiguration
from dmf.model.target_configuration.target_table_schema import TableColumn
from dmf.utils.dataframe_utils import DataFrameUtils


class FieldValuesSourceEnricher:

    @staticmethod
    def enrich(source_configuration: SourceConfiguration, df: DataFrame) -> Tuple[DataFrame, List[TableColumn]]:
        extra_columns: List[TableColumn] = []
        for column_mapping in source_configuration.all_column_transformations:
            if column_mapping.target_field_value is not None:
                if column_mapping.source_field_name is None:
                    raise ValueError(f"Transformation spec error. Column mapping '{column_mapping}' has a literal value but no literal value source column name")

                # add the column for the schema and let the ColumnExpressionBuilder select it,
                # may happen multiple times hence avoid df.withColumn
                df = DataFrameUtils.with_column_fast(
                    df, column_mapping.source_field_name, F.expr(column_mapping.target_field_value))
                extra_columns.append(TableColumn(
                    name=column_mapping.source_field_name,
                    type=column_mapping.target_field_type,
                    is_nullable=False,
                    expression=None,
                    is_fk_to_ref_table=False))
        return df, extra_columns

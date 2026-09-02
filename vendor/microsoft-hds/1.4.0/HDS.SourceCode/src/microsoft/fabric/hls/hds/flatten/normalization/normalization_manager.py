from typing import Union
import datetime
from pyspark.sql.types import Row
from pyspark.sql import DataFrame
from microsoft.fabric.hls.hds.flatten.normalization.date_normalization import DateNormalization
from microsoft.fabric.hls.hds.flatten.normalization.identifier_normalization import IdentifierNormalization
from microsoft.fabric.hls.hds.flatten.normalization.reference_normalization import ReferenceNormalization
from microsoft.fabric.hls.hds.flatten.normalization.utils import NormalizationUtils

class FlattenNormalization:
    @staticmethod
    def normalize_date(date: Union[str, datetime.datetime, datetime.date, None]):
        return DateNormalization.normalize_date(date)

    @staticmethod
    def normalize_resource_id(id_value: str,
                              type_value: str,
                              base_url: Union[str, None] = None
                              ) -> Union[str,None]:
        return IdentifierNormalization.normalize_resource_id(id_value, type_value, base_url)

    @staticmethod
    def normalize_resource_identifier(df: DataFrame, identifier_column: str, id_column: str, source_system_column: str) -> DataFrame:
        return IdentifierNormalization.normalize_resource_identifier(df, identifier_column, id_column, source_system_column)

    @staticmethod
    def normalize_ref_struct(reference_row: Row, source_system: str) -> Row:
        return ReferenceNormalization.normalize_ref_struct(reference_row, source_system)
    
    @staticmethod
    def normalize_ref_array(column_data: list, source_system: str | None) -> list:
        return ReferenceNormalization.normalize_ref_array(column_data, source_system)
    
    @staticmethod
    def create_normalize_nested_ref_udf(original_col_schema, nested_ref_name, nested_array):
        return ReferenceNormalization.create_normalize_nested_ref_udf(original_col_schema, nested_ref_name, nested_array)
    
    

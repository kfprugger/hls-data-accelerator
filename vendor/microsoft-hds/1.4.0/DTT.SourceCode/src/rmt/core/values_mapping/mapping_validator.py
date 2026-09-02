from typing import List

from pyspark.sql import DataFrame

from rmt.core.values_mapping.mapping_definition import MappingDefinition
from rmt.core.values_mapping.mapping_schema import MappingSchema


class MappingValidator:

    @staticmethod
    def validate_mapping_for_source(source: str, mapping_definitions: List[MappingDefinition]):

        table_names = [mapping.target_table_name for mapping in mapping_definitions]
        duplicates = set([table_name for table_name in table_names if table_names.count(table_name) > 1])

        if duplicates:
            raise ValueError(f"Duplicate target table name/s found: '{duplicates}' in source: '{source}'")

    @staticmethod
    def validate(mapping_df: DataFrame) -> DataFrame:
        mapping_df = MappingValidator._remove_duplicate_values(mapping_df)
        MappingValidator._validate_mappings_unique(mapping_df)
        return mapping_df

    @staticmethod
    def _remove_duplicate_values(mapping_df: DataFrame) -> DataFrame:
        return mapping_df.distinct()

    @staticmethod
    def _validate_mappings_unique(mapping_df: DataFrame):
        columns = [
            MappingSchema.MAPPING_FIELD_NAME_SOURCE_DOMAIN,
            MappingSchema.MAPPING_FIELD_NAME_SOURCE_VALUE,
            MappingSchema.MAPPING_FIELD_NAME_TARGET_TABLE,
            MappingSchema.MAPPING_FIELD_NAME_TARGET_FIELD,
        ]
        df_duplicates = mapping_df.groupBy(columns).count().filter("count > 1")

        if df_duplicates.count() != 0:
            raise Exception("Mapping dataframe has duplicate mapping for the combination of source_domain, source_value, target_table, target_column")

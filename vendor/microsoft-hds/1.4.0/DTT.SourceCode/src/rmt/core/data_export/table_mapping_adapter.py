from typing import List

from pyspark.sql import DataFrame

from rmt.core.data_management.authoring_mapping_entry import AuthoringMappingEntry
from rmt.core.data_management.primitive_types import ContributorName
from rmt.core.data_management.table_mapping import TableMapping
from rmt.core.values_mapping.mapping_schema import MappingSchema


class TableMappingAdapter:

    @staticmethod
    def get_authoring_entries(contributor_name: ContributorName, table_mapping_list: List[TableMapping]) -> List[AuthoringMappingEntry]:
        authoring_entries = []
        for table_mapping in table_mapping_list:
            for target_key, source_values in table_mapping._target_to_source_mapping.items():
                for source_value in source_values:
                    authoring_entry = AuthoringMappingEntry(contributor_name, table_mapping.table_name, target_key, source_value)
                    authoring_entries.append(authoring_entry)
        return authoring_entries

    @staticmethod
    def get_authoring_entries_from_dataframe(unmapped_source_values_df: DataFrame) -> List[AuthoringMappingEntry]:
        authoring_entries = unmapped_source_values_df.select(
            MappingSchema.MAPPING_FIELD_NAME_SOURCE_DOMAIN,
            MappingSchema.MAPPING_FIELD_NAME_TARGET_TABLE,
            MappingSchema.MAPPING_FIELD_NAME_TARGET_VALUE,
            MappingSchema.MAPPING_FIELD_NAME_SOURCE_VALUE,
        ).collect()

        return [
            AuthoringMappingEntry(
                row[MappingSchema.MAPPING_FIELD_NAME_SOURCE_DOMAIN],
                row[MappingSchema.MAPPING_FIELD_NAME_TARGET_TABLE],
                row[MappingSchema.MAPPING_FIELD_NAME_TARGET_VALUE],
                row[MappingSchema.MAPPING_FIELD_NAME_SOURCE_VALUE],
            )
            for row in authoring_entries
        ]

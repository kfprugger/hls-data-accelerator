from typing import Optional
from common.model.data_access_definition import DataAccessDefinition
from dmf.model.source_configuration import MappingDefinition, SourceConfiguration, SourceTableSchema
from dmf.model.target_configuration.target_configuration import TargetConfiguration


class SourceConfigurationFactory:
    @staticmethod
    def get_instance(
        source_id: str,
        feed_id: str,
        data_access_definition: DataAccessDefinition,
        schema: SourceTableSchema,
        target_configurations: set[TargetConfiguration],
        mapping_definitions: frozenset[MappingDefinition],
        source_to_reference_mappings,  #: FrozenSet[SourceToReferenceMapping],TODO: add this
        source_table_column_name: str,
        secondary_lake_location: str
    ):
        return SourceConfiguration(
            source_id=source_id,
            feed_id=feed_id,
            data_access_definition=data_access_definition,
            table_schema=schema,
            target_configurations=frozenset(target_configurations),
            mapping_definitions=mapping_definitions,
            create_view_only=False,
            view_alias=None,
            source_to_reference_mappings=source_to_reference_mappings,
            source_table_column_name=source_table_column_name,
            secondary_lake_location=secondary_lake_location
        )

    @staticmethod
    def get_view_instance(
        source_id,
        feed_id: str,
        data_access_definition: DataAccessDefinition,
        view_alias: Optional[str],
    ):
        return SourceConfiguration(
            source_id=source_id,
            feed_id=feed_id,
            data_access_definition=data_access_definition,
            table_schema=None,
            target_configurations=frozenset(),
            mapping_definitions=frozenset(),
            create_view_only=True,
            view_alias=view_alias,
            source_to_reference_mappings=frozenset(),
            secondary_lake_location=""
        )

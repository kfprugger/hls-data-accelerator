from typing import FrozenSet, Optional, Set

from configuration_compiler.config_files_models.adapter.model import SourceTable
from configuration_compiler.config_files_models.db_schema.ext_model import DBSchemaModel
from configuration_compiler.config_files_models.env.ext_model import EnvConfigModel
from configuration_compiler.config_files_models.utils.datasource_type_enum_utils import get_data_source_type
from common.model.data_source_type_enum import DataSourceTypeEnum
from dmf.model.source_configuration import MappingDefinition
from dmf.model.target_configuration.target_transformation import ColumnTransformation


class IdsMappingParser:
    @staticmethod
    def parse_ids_mapping(
        all_column_transformations: dict[str, Set[ColumnTransformation]],
        source_table: SourceTable,
        target_schema: DBSchemaModel,
        env_config: EnvConfigModel,
    ) -> FrozenSet[MappingDefinition]:
        mapping_definitions = set()

        origin_target_table_name = source_table.query or source_table.tableName
        for column_transformations_set in all_column_transformations.values():
            for transformation in column_transformations_set:
                external_id_column_name = IdsMappingParser._get_external_id(
                    source_table, transformation.original_source_field_name
                )
                if transformation.should_be_id_mapped:
                    owner_table = target_schema.tables_dict[transformation.owner_target_id]
                    data_source_type = get_data_source_type(env_config.target_entities_container_type, None)
                    mapping_definition = MappingDefinition(
                        target_mapping_table_name=transformation.owner_target_id,
                        source_mapping_table_name=origin_target_table_name,
                        target_id_column_name=transformation.target_field_name,
                        internal_id_column_name=transformation.original_source_field_name,
                        external_id_column_name=external_id_column_name,
                        db=None if data_source_type == DataSourceTypeEnum.STORAGE else target_schema.table_db_name(owner_table),
                        # for mapping purposes, prefer to use the target table type (either storage or table, not query)
                        mapping_entity_type=data_source_type,
                        secondary_lake_location=env_config.secondary_lake_location,
                    )
                    mapping_definitions.add(mapping_definition)

        return frozenset(mapping_definitions)

    @staticmethod
    def _get_external_id(source_table: SourceTable, source_field_name: str) -> Optional[str]:
        for replacement_key in source_table.pkInternalExternalPairs:
            internal_field = replacement_key.internalField
            external_field = replacement_key.externalField
            if internal_field == source_field_name:
                return external_field
        return None

    @staticmethod
    def _is_ref_table(target_table_id, reference_tables):
        return target_table_id in reference_tables

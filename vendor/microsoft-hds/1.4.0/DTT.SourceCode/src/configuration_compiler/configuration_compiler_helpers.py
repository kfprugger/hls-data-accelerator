import os.path
from typing import FrozenSet, Optional, Set
from common.model.base_source_configuration import BaseSourceConfiguration, BaseSourceTableSchema
from configuration_compiler.config_files_models.adapter.ext_model import AdapterModel
from configuration_compiler.config_files_models.common.entity_definition_container import EntityDefinitionContainer
from configuration_compiler.config_files_models.common.entity_definition_container_type import EntityDefinitionContainerTypeEnum
from configuration_compiler.config_files_models.env.ext_model import EnvConfigModel
from configuration_compiler.config_files_models.common.entity_type_enum import EntityTypeEnum
from configuration_compiler.config_files_models.semantics_config.ext_model import SemanticsConfigModel
from configuration_compiler.config_files_models.utils.datasource_type_enum_utils import get_data_source_type
from configuration_compiler.source_configuration_factory import SourceConfigurationFactory
from common.model.data_access_definition import DataAccessDefinition
from common.model.types import DataSourceId, TargetId
from common.model.source_to_reference_mapping import SourceToReferenceMapping
from dmf.model.source_configuration import MappingDefinition, SourceConfiguration, SourceTableSchema
from dmf.model.target_configuration.target_configuration import PartitionConfig, TargetConfiguration, TemporalColumns
from dmf.model.target_configuration.target_table_schema import TargetTableSchema
from dmf.model.target_configuration.target_transformation import ColumnTransformation


def _get_source_owner_id(
    entity_id: DataSourceId,
    container: EntityDefinitionContainer,
    env_config: EnvConfigModel,
) -> Optional[str]:
    return _get_data_source_owner_id(
        entity_id, EntityTypeEnum.SOURCE, container, env_config
    )


def get_target_owner_id(
    entity_id: DataSourceId,
    container: EntityDefinitionContainer,
    env_config: EnvConfigModel,
):
    return _get_data_source_owner_id(
        entity_id, EntityTypeEnum.TARGET, container, env_config
    )


def generate_data_access_definition(
    env_config: EnvConfigModel,
    source_entities_definition_container,
    source_id,
    query: Optional[str],
):
    # TODO: move to DataAccessDefinition module?
    datasource_owner_id = _get_source_owner_id(
        source_id, source_entities_definition_container, env_config
    )
    if env_config.is_source_storage_configured and query:
        datasource_owner_id = None
    data_format = get_data_format(
        source_id,
        EntityTypeEnum.SOURCE,
        source_entities_definition_container,
        env_config,
    )
    data_source_type = get_data_source_type(source_entities_definition_container.type, query)
    return DataAccessDefinition(
        data_source_id=query or source_id,
        data_source_type=data_source_type,
        data_source_owner_id=datasource_owner_id,
        data_format=data_format,
    )


def get_source_entities_container_name(dmf_adaptor: AdapterModel, env_config: EnvConfigModel):
    name = None
    if not env_config.is_source_storage_configured:
        name = dmf_adaptor.source_db_name()
        if not name:
            raise ValueError("Source DB name is missing")

    return name


def get_target_entities_container_name(db: DataSourceId, env_config: EnvConfigModel):
    name = None
    if not env_config.is_target_storage_configured:
        name = db
        if not name:
            raise ValueError("Target DB name is missing")

    return name


def _generate_target_config(
    feed_id,
    raw_target_transformations: Set[ColumnTransformation],
    target_id,
    partitions_fields: FrozenSet[PartitionConfig],
    temporal_tables_semantics: dict[str, TemporalColumns],
    table_schema: TargetTableSchema,
    target_modified_date_column_name,
    env_config: EnvConfigModel,
) -> TargetConfiguration:
    entities_definition_container = EntityDefinitionContainer(
        name=get_target_entities_container_name(
            table_schema.db, env_config
        ),
        type=env_config.target_entities_container_type,
    )

    relevant_target_transformations = []
    for target_transformation in raw_target_transformations:
        relevant_target_transformations.append(target_transformation)

    data_access_definition = DataAccessDefinition(
        data_source_id=target_id,
        data_source_type=get_data_source_type(entities_definition_container.type, None),
        data_source_owner_id=get_target_owner_id(
            target_id, entities_definition_container, env_config
        ),
        data_format=get_data_format(
            entity_id=target_id,
            entity_type=EntityTypeEnum.TARGET,
            env_config=env_config,
            container=entities_definition_container,
        ),
    )
    target_config = TargetConfiguration(
        feed_id=feed_id,
        target_id=target_id,
        data_access_definition=data_access_definition,
        target_columns_transformations=frozenset(relevant_target_transformations),
        partitions_config=partitions_fields,
        temporal_tables_semantics=temporal_tables_semantics.get(target_id, None),
        table_schema=table_schema,
        target_modified_date_column_name=target_modified_date_column_name,
    )
    return target_config


def generate_source_config_for_rmt(source_id: DataSourceId,
                                   source_to_reference_mappings: FrozenSet[SourceToReferenceMapping],
                                   data_access_definition: DataAccessDefinition,
                                   table_schema: Optional[BaseSourceTableSchema]
                                   ) -> BaseSourceConfiguration:
    src_config: BaseSourceConfiguration = BaseSourceConfiguration(
        source_id=source_id,
        data_access_definition=data_access_definition,
        source_to_reference_mappings=source_to_reference_mappings,
        table_schema=table_schema
    )
    return src_config


def generate_source_config(
    columns_transformations: dict[DataSourceId, dict[DataSourceId, Set[ColumnTransformation]]],
    feed_id,
    source_id,
    source_schema: dict[DataSourceId, SourceTableSchema],
    semantics_config_model: Optional[SemanticsConfigModel],
    temporal_tables_semantics: dict[str, TemporalColumns],
    target_tables_schemas,
    target_modified_date_column_name,
    mapping_definitions: FrozenSet[MappingDefinition],
    data_access_definition: DataAccessDefinition,
    env_config: EnvConfigModel,
    source_to_reference_mappings: FrozenSet[SourceToReferenceMapping],
    source_table_column_name: str,
) -> SourceConfiguration:
    target_configurations: Set[TargetConfiguration] = set()
    source_column_transformations: dict[TargetId, Set[ColumnTransformation]] = columns_transformations[source_id]

    for target_id, target_transformations in source_column_transformations.items():
        if not target_transformations:
            raise ValueError("No transformations are defined for target table {}".format(target_id))
        if semantics_config_model is not None:
            partition_rules = semantics_config_model.partition_rules_for_table(target_id)
        else:
            partition_rules = frozenset()
        target_config: TargetConfiguration = _generate_target_config(
            feed_id,
            target_transformations,
            target_id,
            partition_rules,
            temporal_tables_semantics,
            target_tables_schemas[target_id],
            target_modified_date_column_name,
            env_config,
        )
        target_configurations.add(target_config)
    return SourceConfigurationFactory.get_instance(
        source_id=source_id,
        feed_id=feed_id,
        data_access_definition=data_access_definition,
        schema=source_schema[source_id],
        target_configurations=target_configurations,
        mapping_definitions=mapping_definitions,
        source_to_reference_mappings=source_to_reference_mappings,
        source_table_column_name=source_table_column_name,
        secondary_lake_location=env_config.secondary_lake_location
    )


def _get_data_source_owner_id(
    entity_id: DataSourceId,
    entity_type: EntityTypeEnum,
    container: EntityDefinitionContainer,
    env_config: EnvConfigModel,
) -> Optional[str]:
    """if we have a DB, return its logical name, otherwise return the correct storage location"""
    if container.type == EntityDefinitionContainerTypeEnum.METASTORE:
        return container.name
    if container.type == EntityDefinitionContainerTypeEnum.STORAGE:
        entity_specific_location = env_config.entity_specific_location(entity_id, entity_type)
        if entity_specific_location:
            return entity_specific_location
        data_source_root = env_config.data_root_location(entity_type)
        if not data_source_root:
            raise ValueError("Data source is not defined")

        return os.path.join(data_source_root, entity_id)

    raise ValueError(f"Unknown data source type '{container.type}'")


def get_data_format(
    entity_id: DataSourceId,
    entity_type: EntityTypeEnum,
    container: EntityDefinitionContainer,
    env_config: EnvConfigModel,
) -> Optional[str]:
    if container.type == EntityDefinitionContainerTypeEnum.STORAGE:
        return env_config.storage_data_format(entity_id, entity_type)

    return None

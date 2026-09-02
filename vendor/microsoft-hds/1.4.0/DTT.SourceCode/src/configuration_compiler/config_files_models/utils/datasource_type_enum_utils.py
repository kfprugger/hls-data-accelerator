from typing import Optional

from configuration_compiler.config_files_models.common.entity_definition_container_type import EntityDefinitionContainerTypeEnum
from common.model.data_source_type_enum import DataSourceTypeEnum


def get_data_source_type(
    entity_definition_container_type: EntityDefinitionContainerTypeEnum,
    query: Optional[str],
) -> DataSourceTypeEnum:
    if query:
        return DataSourceTypeEnum.QUERY
    if entity_definition_container_type == EntityDefinitionContainerTypeEnum.METASTORE:
        return DataSourceTypeEnum.TABLE
    if entity_definition_container_type == EntityDefinitionContainerTypeEnum.STORAGE:
        return DataSourceTypeEnum.STORAGE
    raise ValueError(f"Unknown value of storage type: '{entity_definition_container_type}' in the environment file")

from dataclasses import dataclass
from typing import Optional

from configuration_compiler.config_files_models.common.entity_definition_container_type import EntityDefinitionContainerTypeEnum


@dataclass(eq=True)
class EntityDefinitionContainer:
    name: Optional[str]
    type: EntityDefinitionContainerTypeEnum

    def __post_init__(self):
        """
        Post initiation validation
        """
        if not self.name and self.type == EntityDefinitionContainerTypeEnum.METASTORE:
            raise ValueError("Data source type was not defined in the environment file")

from abc import ABC, abstractmethod
from typing import List

from rmt.core.values_mapping.mapping_definition import MappingDefinition


class MappingDefinitionsReader(ABC):

    @property
    def sources(self) -> List[str]:
        pass

    @abstractmethod
    def read(self, source: str) -> List[MappingDefinition]:
        pass

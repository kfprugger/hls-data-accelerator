from abc import ABC, abstractmethod
from typing import List, Set, Tuple

from rmt.core.core_exceptions import UpdateValueError
from rmt.core.data_management.authoring_mapping_entry import AuthoringMappingEntry
from rmt.core.data_management.contributor import Contributor


class AbstractAuthoringMappingReader(ABC):

    @abstractmethod
    def read(self, contributor: Contributor, contributors: Set[Contributor]) -> Tuple[List[AuthoringMappingEntry], List[UpdateValueError]]:
        pass

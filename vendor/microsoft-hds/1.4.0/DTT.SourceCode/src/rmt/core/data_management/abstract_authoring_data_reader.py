from abc import ABC, abstractmethod
from typing import List, Set, Tuple

from rmt.core.core_exceptions import UpdateValueError
from rmt.core.data_management.authoring_data_entry import AuthoringDataEntry
from rmt.core.data_management.contributor import Contributor


class AbstractAuthoringDataReader(ABC):

    @abstractmethod
    def read(self, contributor: Contributor, contributors: Set[Contributor]) -> Tuple[List[AuthoringDataEntry], List[UpdateValueError]]:
        pass

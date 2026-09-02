from abc import ABC, abstractmethod
from typing import Set

from rmt.core.data_management.contributor import Contributor


class AbstractContributorsReader(ABC):

    @abstractmethod
    def read(self) -> Set[Contributor]:
        pass

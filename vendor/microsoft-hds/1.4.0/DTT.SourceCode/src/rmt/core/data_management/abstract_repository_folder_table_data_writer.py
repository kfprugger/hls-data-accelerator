from abc import ABC, abstractmethod
from typing import List

from rmt.core.data_management.primitive_types import ContributorName
from rmt.core.data_management.table_data import TableData


class AbstractRepositoryFolderTableDataWriter(ABC):

    @abstractmethod
    def write(self, contributor_name: ContributorName, table_data_list: List[TableData]):
        pass

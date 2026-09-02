from abc import ABC, abstractmethod
from typing import List, Set

from rmt.core.data_management.primitive_types import ContributorName, TableName
from rmt.core.data_management.table_data import TableData


class AbstractRepositoryFolderTableDataReader(ABC):

    @abstractmethod
    def read(self, contributor_name: ContributorName, table_names: Set[TableName] = None) -> List[TableData]:
        pass

    @abstractmethod
    def get_data_repository_path(self):
        pass

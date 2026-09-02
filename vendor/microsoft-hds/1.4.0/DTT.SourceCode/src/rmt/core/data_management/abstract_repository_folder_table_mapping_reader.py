from abc import ABC, abstractmethod
from typing import List, Set

from rmt.core.data_management.primitive_types import ContributorName, TableName
from rmt.core.data_management.table_mapping import TableMapping


class AbstractRepositoryFolderTableMappingReader(ABC):

    @abstractmethod
    def read(self, contributor_name: ContributorName, table_names: Set[TableName] = None) -> List[TableMapping]:
        pass

    @abstractmethod
    def get_mapping_repository_path(self):
        pass

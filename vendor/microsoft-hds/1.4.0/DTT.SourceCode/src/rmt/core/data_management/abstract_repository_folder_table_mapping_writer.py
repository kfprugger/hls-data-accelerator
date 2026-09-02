from abc import ABC, abstractmethod
from typing import List

from rmt.core.data_management.primitive_types import ContributorName
from rmt.core.data_management.table_mapping import TableMapping


class AbstractRepositoryFolderTableMappingWriter(ABC):

    @abstractmethod
    def write(self, contributor_name: ContributorName, table_mapping_list: List[TableMapping]):
        pass

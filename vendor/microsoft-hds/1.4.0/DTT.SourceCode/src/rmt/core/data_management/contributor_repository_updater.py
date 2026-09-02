from typing import List

from rmt.core.data_management.contributor import Contributor
from rmt.core.data_management.primitive_types import DataChanged
from rmt.core.data_management.repository import Repository
from rmt.core.data_management.table_data import TableData
from rmt.core.data_management.table_mapping import TableMapping


class ContributorRepositoryUpdater:
    """
    This class is responsible for updating the repository with the data of a contributor
    its sets the table data and table mapping of the contributor in the repository
    thus overriding the previous data of the contributor in the repository
    """

    @property
    def contributor(self) -> Contributor:
        return self._contributor

    def __init__(self, repository: Repository, contributor: Contributor):
        self._contributor = contributor
        self._repository = repository

    def _set_table_mapping(self, table_mapping: TableMapping) -> DataChanged:
        """
        Set the table data of the contributor in the repository and return True if there was a change
        """
        repository_table_mapping = self._repository.get_table_mapping_by_contributor_and_table(self._contributor, table_mapping.table_name)
        self._repository.set_table_mapping(self._contributor, table_mapping)
        return not repository_table_mapping or repository_table_mapping != table_mapping

    def set_table_mapping_list(self, table_mapping_list: List[TableMapping]) -> List[TableMapping]:
        """
        Set the table data mapping of the contributor in the repository and return True if there was a change
        """
        result: List[TableMapping] = []
        for table_mapping in table_mapping_list:
            if self._set_table_mapping(table_mapping):
                result.append(table_mapping)
        return result

    def _set_table_data(self, table_data: TableData) -> bool:
        repository_table_data = self._repository.get_table_data_by_contributor_and_table(self._contributor, table_data.table_name)
        self._repository.set_table_data(self._contributor, table_data)
        return not repository_table_data or repository_table_data != table_data

    def set_table_data_list(self, table_data_list: List[TableData]) -> List[TableData]:
        result: List[TableData] = []
        for table_data in table_data_list:
            if self._set_table_data(table_data):
                result.append(table_data)
        return result

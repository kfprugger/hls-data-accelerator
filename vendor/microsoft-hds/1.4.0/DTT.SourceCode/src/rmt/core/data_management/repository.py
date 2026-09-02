from typing import List, Set

from rmt.core.core_exceptions import NonExistingContributorInputError
from rmt.core.data_management.contributor import Contributor
from rmt.core.data_management.contributor_table_data_collection import ContributorTableDataCollection
from rmt.core.data_management.contributor_table_mapping_collection import ContributorTableMappingCollection
from rmt.core.data_management.primitive_types import ContributorName
from rmt.core.data_management.table_data import TableData
from rmt.core.data_management.table_mapping import TableMapping


class Repository:
    """
    this class is a repository for all the data and mapping of each contributor per table
    it uses the ContributorTableMappingCollection and ContributorTableDataCollection to store and retrieve
    the data and mapping
    """

    def __init__(self, contributors: Set[Contributor]):
        self._contributors = contributors
        self._contributor_table_mapping_collection = ContributorTableMappingCollection()
        self._contributor_table_data_collection = ContributorTableDataCollection()

    def __str__(self):
        return f"Repository(contributors={self._contributors})"

    def _raise_exception_if_contributor_not_exists(self, contributor: Contributor):
        if contributor not in self._contributors:
            raise NonExistingContributorInputError(contributor.name)

    def get_contributor(self, contributor_name: ContributorName) -> Contributor:
        for contributor in self._contributors:
            if contributor.name == contributor_name:
                return contributor
        return None

    def add_table_mapping_list(self, contributor: Contributor, table_mapping_list: List[TableMapping]):
        self._raise_exception_if_contributor_not_exists(contributor)
        self._contributor_table_mapping_collection.add_table_mapping_list(contributor, table_mapping_list)

    def add_table_data_list(self, contributor: Contributor, reference_data_sets: List[TableData]):
        self._raise_exception_if_contributor_not_exists(contributor)
        self._contributor_table_data_collection.add_table_data_list(contributor, reference_data_sets)

    def set_table_mapping(self, contributor: Contributor, table_mapping: TableMapping):
        self._raise_exception_if_contributor_not_exists(contributor)
        self._contributor_table_mapping_collection.set_table_mapping(contributor, table_mapping)

    def set_table_data(self, contributor: Contributor, table_data: TableData):
        self._raise_exception_if_contributor_not_exists(contributor)
        self._contributor_table_data_collection.set_table_data(contributor, table_data)

    def get_table_mapping_by_contributor_and_table(self, contributor: Contributor, table_name: str) -> TableMapping:
        return self._contributor_table_mapping_collection.get_table_mapping(contributor, table_name)

    def get_table_data_by_contributor_and_table(self, contributor: Contributor, table_name: str) -> TableData:
        return self._contributor_table_data_collection.get_table_data(contributor, table_name)

    def get_table_mapping_list_by_table(self, table_name: str) -> List[TableMapping]:
        return self._contributor_table_mapping_collection.get_table_mapping_list_for_table(table_name)

    def get_table_data_list_by_table(self, table_name: str) -> List[TableData]:
        return self._contributor_table_data_collection.get_table_data_list_for_table(table_name)

    def get_mapping_table_names_for_contributor(self, contributor: Contributor) -> List[str]:
        return self._contributor_table_mapping_collection.get_table_names_for_contributor(contributor)

    def get_data_table_names_for_contributor(self, contributor: Contributor) -> List[str]:
        return self._contributor_table_data_collection.get_table_names_for_contributor(contributor)

from collections import defaultdict
from typing import Dict, List

from rmt.core.core_exceptions import AddContributorTableMappingError
from rmt.core.data_management.contributor import Contributor
from rmt.core.data_management.primitive_types import TableName
from rmt.core.data_management.table_mapping import TableMapping


class ContributorTableMappingCollection:
    """
    this is a collection of table mapping entries for each contributor and table
    this is a helper class for the Repository class which stores the mapping in the same way
    """

    def __init__(self):
        self._mapping_by_contributor_and_table: Dict[Contributor, Dict[TableName, TableMapping]] = defaultdict(dict)

    def _add_table_mapping(self, contributor: Contributor, table_mapping: TableMapping):
        if table_mapping.table_name in self._mapping_by_contributor_and_table[contributor]:
            raise AddContributorTableMappingError(table_mapping.table_name, contributor.name)
        self._mapping_by_contributor_and_table[contributor][table_mapping.table_name] = table_mapping

    def add_table_mapping_list(self, contributor: Contributor, table_mapping_list: List[TableMapping]):
        for table_mapping in table_mapping_list:
            self._add_table_mapping(contributor, table_mapping)

    def set_table_mapping(self, contributor: Contributor, table_mapping: TableMapping):
        self._mapping_by_contributor_and_table[contributor][table_mapping.table_name] = table_mapping

    def get_table_mapping(self, contributor: Contributor, table_name: str) -> TableMapping:
        return self._mapping_by_contributor_and_table.get(contributor, {}).get(table_name, None)

    def get_table_mapping_list_for_table(self, table_name: str) -> List[TableMapping]:
        result: List[TableMapping] = []
        for contributor, contributor_mapping in self._mapping_by_contributor_and_table.items():
            if table_name in contributor_mapping:
                result.append(self._mapping_by_contributor_and_table[contributor][table_name])
        return result

    def get_table_names_for_contributor(self, contributor: Contributor) -> List[str]:
        return [table_name for table_name in self._mapping_by_contributor_and_table.get(contributor, {}).keys()]

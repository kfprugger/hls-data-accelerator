from collections import defaultdict
from typing import Dict, List

from rmt.core.core_exceptions import AddContributorTableDataError
from rmt.core.data_management.contributor import Contributor
from rmt.core.data_management.primitive_types import TableName
from rmt.core.data_management.table_data import TableData


class ContributorTableDataCollection:
    """
    this is a collection of table data entries for each contributor and table
    this is a helper class for the Repository class which stores the data in the same way
    """

    def __init__(self):
        self._data_by_contributor_and_table: Dict[Contributor, Dict[TableName, TableData]] = defaultdict(dict)

    def _add_table_data(self, contributor: Contributor, table_data: TableData):

        if table_data.table_name in self._data_by_contributor_and_table[contributor]:
            raise AddContributorTableDataError(table_data.table_name, contributor.name)
        self._data_by_contributor_and_table[contributor][table_data.table_name] = table_data

    def add_table_data_list(self, contributor: Contributor, table_data_list: List[TableData]):
        for table_data in table_data_list:
            self._add_table_data(contributor, table_data)

    def set_table_data(self, contributor: Contributor, table_data: TableData):
        self._data_by_contributor_and_table[contributor][table_data.table_name] = table_data

    def get_table_data(self, contributor: Contributor, table_name: str) -> TableData:
        return self._data_by_contributor_and_table.get(contributor, {}).get(table_name, None)

    def get_table_data_list_for_table(self, table_name: str) -> List[TableData]:
        result: List[TableData] = []
        for contributor, contributor_data in self._data_by_contributor_and_table.items():
            if table_name in contributor_data:
                result.append(self._data_by_contributor_and_table[contributor][table_name])
        return result

    def get_table_data_list_for_contributor(self, contributor: Contributor) -> List[TableData]:
        return list(self._data_by_contributor_and_table.get(contributor, {}).values())

    def get_table_names_for_contributor(self, contributor: Contributor) -> List[str]:
        return list(self._data_by_contributor_and_table.get(contributor, {}).keys())

from typing import List

from rmt.core.data_management.authoring_data_entry import AuthoringDataEntry
from rmt.core.data_management.primitive_types import ContributorName
from rmt.core.data_management.table_data import TableData


class TableDataAdapter:

    @staticmethod
    def get_authoring_entries(contributor_name: ContributorName, table_data_list: List[TableData]) -> List[AuthoringDataEntry]:
        authoring_entries = []
        for table_data in table_data_list:
            for entry in table_data.entries:
                authoring_entry = AuthoringDataEntry(contributor_name, table_data.table_name, entry.key, entry.name)
                authoring_entries.append(authoring_entry)
        return authoring_entries

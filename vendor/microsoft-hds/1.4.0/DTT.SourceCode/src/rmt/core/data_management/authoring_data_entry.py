from rmt.core.data_management.primitive_types import ContributorName, TableName
from rmt.core.data_management.table_data import DataEntry


class AuthoringDataEntry(DataEntry):
    def __init__(self, contributor_name: ContributorName, table_name: TableName, key: int, name: str):
        super().__init__(key, name)
        self.contributor_name = contributor_name
        self.table_name = table_name

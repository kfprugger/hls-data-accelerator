from typing import Dict, List, Set, Tuple

from rmt.core.core_exceptions import KeyOutOfRangeError, NonExistingContributorInputError, UpdateValueError
from rmt.core.data_management.authoring_data_entry import AuthoringDataEntry
from rmt.core.data_management.contributor import Contributor
from rmt.core.data_management.predefined_name_retriever import PredefinedNameRetriever
from rmt.core.data_management.primitive_types import TableName
from rmt.core.data_management.table_data import DataEntry, TableData


class AuthoringDataAdapter:
    """
    This class is responsible for converting the authoring data entries to a table data list
    By given contributor( which currently its the customer contributor) it
    gather all Authoring data entries for each table and convert them to table data
    in case there is logic error it will raise an exception (duplicate names/ids)
    it also checks for each authoring which is not the given contributor that it has a valid contributor name
    (to verify that the data is not corrupted)
    """

    def __init__(self, contributors: Set[Contributor]):
        self._contributors = contributors

    def get_table_data_for_contributor(self, authoring_table_data_entries: List[AuthoringDataEntry], contributor: Contributor) -> Tuple[List[TableData], List[UpdateValueError]]:
        tables_data: Dict[TableName, TableData] = {}
        errors: List[UpdateValueError] = []

        if contributor not in self._contributors:
            raise NonExistingContributorInputError(contributor.name)

        for authoring_table_entry in authoring_table_data_entries:
            try:
                contributor_predefined_name_retriever = PredefinedNameRetriever(authoring_table_entry.contributor_name, [contributor.name for contributor in self._contributors])
                if contributor_predefined_name_retriever.get_name_in_same_casing_from_predefined_names() == contributor.name:
                    if authoring_table_entry.table_name not in tables_data:
                        tables_data[authoring_table_entry.table_name] = TableData(authoring_table_entry.table_name)
                    if not contributor.is_key_in_contributor_keys_range(int(authoring_table_entry.key)):
                        raise KeyOutOfRangeError(authoring_table_entry.table_name, contributor.name, authoring_table_entry.key)
                    tables_data[authoring_table_entry.table_name].add_data_entry(DataEntry(authoring_table_entry.key, authoring_table_entry.name))
            except UpdateValueError as e:
                errors.append(e)

        return list(tables_data.values()), errors

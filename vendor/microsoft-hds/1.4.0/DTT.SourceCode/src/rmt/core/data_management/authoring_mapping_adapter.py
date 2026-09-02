from typing import Dict, List, Set, Tuple

from rmt.core.core_exceptions import NonExistingContributorInputError, UpdateValueError
from rmt.core.data_management.authoring_mapping_entry import AuthoringMappingEntry
from rmt.core.data_management.contributor import Contributor
from rmt.core.data_management.predefined_name_retriever import PredefinedNameRetriever
from rmt.core.data_management.primitive_types import TableName
from rmt.core.data_management.table_mapping import TableMapping


class AuthoringMappingAdapter:
    """
    This class is responsible for converting the authoring mapping entries to a table mapping list
    By given contributor( which currently its the customer cuntributor) it
    gather all Auhtroing mapping entries for each table and convert them to table mapping
    in case there is logic error it will raise an exception (duplicate source values for different target keys)
    it also checks for each authoring which is not the given contributor that it has a valid contributor name
    (to verify that the mapping is not corrupted)
    """

    def __init__(self, contributors: Set[Contributor]):
        self._contributors: Set[Contributor] = contributors

    def get_table_mapping_for_contributor(
        self, authoring_mapping_entries: List[AuthoringMappingEntry], contributor: Contributor
    ) -> Tuple[List[TableMapping], List[UpdateValueError]]:

        tables_mapping: Dict[TableName, TableMapping] = {}
        errors: List[UpdateValueError] = []

        if contributor not in self._contributors:
            raise NonExistingContributorInputError(contributor.name)

        for authoring_mapping_entry in authoring_mapping_entries:
            try:
                contributor_predefined_name_retriever = PredefinedNameRetriever(authoring_mapping_entry.contributor_name, [contributor.name for contributor in self._contributors])
                if contributor_predefined_name_retriever.get_name_in_same_casing_from_predefined_names() == contributor.name:
                    if authoring_mapping_entry.table_name not in tables_mapping:
                        tables_mapping[authoring_mapping_entry.table_name] = TableMapping(authoring_mapping_entry.table_name)

                    tables_mapping[authoring_mapping_entry.table_name].add_target_mapping(authoring_mapping_entry.target_key, [authoring_mapping_entry.source_value])
            except UpdateValueError as e:
                errors.append(e)

        return list(tables_mapping.values()), errors

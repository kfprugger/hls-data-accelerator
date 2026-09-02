import csv
from io import StringIO
from typing import List, Set, Tuple

from rmt.core.core_exceptions import (AuthoringDataColumnMissingError, AuthoringDataFileNotExistError, EntryNameIsEmpty, IdValueIsNotNumericError,
                                      NonExistingContributorUpdateError, ReferenceTableNotExistInRMTSpecError, UpdateValueError)
from rmt.core.data_export.authoring_data_schema import AuthoringDataSchema
from rmt.core.data_management.abstract_authoring_data_reader import AbstractAuthoringDataReader, AuthoringDataEntry
from rmt.core.data_management.contributor import Contributor
from rmt.core.data_management.predefined_name_retriever import PredefinedNameRetriever
from rmt.file_model.data_management.authoring_files_constants import AUTHORING_DATA_FULL_FILE_NAME
from rmt.file_model.data_management.data_management_context import DataManagementContext


class AuthoringDataFileReader(AbstractAuthoringDataReader):

    def __init__(self, data_management_context: DataManagementContext):
        self._file_system_client = data_management_context.file_system_client
        self._authoring_folder_path = data_management_context.authoring_folder_path
        self._reference_tables = data_management_context.reference_tables

    def read(self, contributor: Contributor, contributors: Set[Contributor]) -> Tuple[List[AuthoringDataEntry], List[UpdateValueError]]:
        file_path = self._file_system_client.join_paths(self._authoring_folder_path, AUTHORING_DATA_FULL_FILE_NAME)
        if not self._file_system_client.path_exist(file_path):
            raise AuthoringDataFileNotExistError(file_path)
        file_content = self._file_system_client.get_file_content_from_path(file_path)
        csv_file = StringIO(file_content)
        reader = csv.DictReader(csv_file)
        missing_columns = []
        if AuthoringDataSchema.CONTRIBUTOR not in reader.fieldnames:
            missing_columns.append(AuthoringDataSchema.CONTRIBUTOR)
        if AuthoringDataSchema.TABLE not in reader.fieldnames:
            missing_columns.append(AuthoringDataSchema.TABLE)
        if AuthoringDataSchema.VALUE not in reader.fieldnames:
            missing_columns.append(AuthoringDataSchema.VALUE)
        if AuthoringDataSchema.ID not in reader.fieldnames:
            missing_columns.append(AuthoringDataSchema.ID)
        if len(missing_columns) > 0:
            raise AuthoringDataColumnMissingError(file_path, missing_columns)

        authoring_data_entries: List[AuthoringDataEntry] = []
        update_error_messages: List[UpdateValueError] = []
        contributors_names = [contributor.name for contributor in contributors]
        rowOk: bool = True
        for row in reader:
            contributor_entry_name = row[AuthoringDataSchema.CONTRIBUTOR]
            table_name = row[AuthoringDataSchema.TABLE]
            key_str = row[AuthoringDataSchema.ID]
            name = row[AuthoringDataSchema.VALUE]
            rowOk = True

            contributor_predefined_name_retriever = PredefinedNameRetriever(contributor_entry_name, [contributor.name])
            # check if current row contributor name is not the same as the requested authoring contributor name
            if contributor_predefined_name_retriever.is_name_not_in_predefined_names():
                contributors_predefined_names_retriever = PredefinedNameRetriever(contributor_entry_name, contributors_names)
                # check if current row contributor name is not a valid (other) contributor name
                if contributors_predefined_names_retriever.is_name_not_in_predefined_names():
                    update_error_messages.append(NonExistingContributorUpdateError(contributor_entry_name, table_name))
                continue
            else:
                contributor_entry_name = contributor_predefined_name_retriever.get_name_in_same_casing_from_predefined_names()

            table_predefined_name_retriever = PredefinedNameRetriever(table_name, [table_name for table_name in self._reference_tables])
            if table_predefined_name_retriever.is_name_not_in_predefined_names():
                update_error_messages.append(ReferenceTableNotExistInRMTSpecError(table_name))
                rowOk = False
            else:
                table_name = table_predefined_name_retriever.get_name_in_same_casing_from_predefined_names()
            if not key_str.isnumeric():
                update_error_messages.append(IdValueIsNotNumericError(table_name, key_str))
                rowOk = False
            else:
                key = int(key_str)

            if not name or name.isspace():
                update_error_messages.append(EntryNameIsEmpty(table_name))
                rowOk = False

            if rowOk:
                authoring_data_entries.append(AuthoringDataEntry(contributor_entry_name, table_name, key, name))

        return authoring_data_entries, update_error_messages

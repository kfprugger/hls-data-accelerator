import csv
from io import StringIO
from typing import List, Set, Tuple

from rmt.core.core_exceptions import (AuthoringMappingColumnMissingError, AuthoringMappingFileNotExistError, NonExistingContributorUpdateError,
                                      ReferenceTableNotExistInRMTSpecError, SourceValueIsEmptyError, TargetIdIsNotNumericError, UpdateValueError)
from rmt.core.data_export.authoring_mapping_schema import AuthoringMappingSchema
from rmt.core.data_management.abstract_authoring_mapping_reader import AbstractAuthoringMappingReader
from rmt.core.data_management.authoring_mapping_entry import AuthoringMappingEntry
from rmt.core.data_management.contributor import Contributor
from rmt.core.data_management.predefined_name_retriever import PredefinedNameRetriever
from rmt.file_model.data_management.authoring_files_constants import AUTHORING_MAPPING_FULL_FILE_NAME
from rmt.file_model.data_management.data_management_context import DataManagementContext


class AuthoringMappingFileReader(AbstractAuthoringMappingReader):

    def __init__(self, datamanagement_context: DataManagementContext):
        self._file_system_client = datamanagement_context.file_system_client
        self._authoring_folder_path = datamanagement_context.authoring_folder_path
        self._reference_tables = datamanagement_context.reference_tables

    def read(self, contributor: Contributor, contributors: Set[Contributor]) -> Tuple[List[AuthoringMappingEntry], List[UpdateValueError]]:
        file_path = self._file_system_client.join_paths(self._authoring_folder_path, AUTHORING_MAPPING_FULL_FILE_NAME)
        if not self._file_system_client.path_exist(file_path):
            raise AuthoringMappingFileNotExistError(file_path)
        file_content = self._file_system_client.get_file_content_from_path(file_path)
        csv_file = StringIO(file_content)
        reader = csv.DictReader(csv_file)
        missing_columns = []
        if AuthoringMappingSchema.CONTRIBUTOR not in reader.fieldnames:
            missing_columns.append(AuthoringMappingSchema.CONTRIBUTOR)
        if AuthoringMappingSchema.TABLE not in reader.fieldnames:
            missing_columns.append(AuthoringMappingSchema.TABLE)
        if AuthoringMappingSchema.SOURCE_VALUE not in reader.fieldnames:
            missing_columns.append(AuthoringMappingSchema.SOURCE_VALUE)
        if AuthoringMappingSchema.TARGET_ID not in reader.fieldnames:
            missing_columns.append(AuthoringMappingSchema.TARGET_ID)

        if len(missing_columns) > 0:
            raise AuthoringMappingColumnMissingError(file_path, missing_columns)

        authoring_mapping_entries: List[AuthoringMappingEntry] = []
        update_error_messages: List[UpdateValueError] = []
        contributors_names = [contributor.name for contributor in contributors]
        rowOk: bool = True
        for row in reader:
            contributor_entry_name = row[AuthoringMappingSchema.CONTRIBUTOR]
            table_name = row[AuthoringMappingSchema.TABLE]
            target_id = row[AuthoringMappingSchema.TARGET_ID]
            source_value = row[AuthoringMappingSchema.SOURCE_VALUE]
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
            if not target_id.isnumeric():
                update_error_messages.append(TargetIdIsNotNumericError(table_name, source_value, target_id))
                rowOk = False
            if not source_value or source_value.isspace():
                update_error_messages.append(SourceValueIsEmptyError(table_name, source_value))
                rowOk = False

            if rowOk:
                authoring_mapping_entries.append(AuthoringMappingEntry(contributor_entry_name, table_name, int(target_id), source_value))

        return authoring_mapping_entries, update_error_messages

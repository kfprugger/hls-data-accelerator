from typing import List, Set

from rmt.core.core_exceptions import ReferenceTableNotExistInRMTSpecError
from rmt.core.data_management.abstract_repository_folder_table_data_reader import AbstractRepositoryFolderTableDataReader
from rmt.core.data_management.contributor import ContributorType
from rmt.core.data_management.primitive_types import ContributorName, TableName
from rmt.core.data_management.table_data import TableData
from rmt.file_model.data_file_model import DataFileModel
from rmt.file_model.data_management.data_management_context import DataManagementContext
from rmt.file_model.data_management.table_data_file_model_adapter import TableDataFileModelAdapter
from rmt.filesystem.files_reader import FilesReader


class RepositoryFolderTableDataReader(AbstractRepositoryFolderTableDataReader):

    def __init__(self, data_management_context: DataManagementContext):
        self._reference_tables = data_management_context.reference_tables
        self._file_system_client = data_management_context.file_system_client
        self._repository_folder = data_management_context.repository_folder

    def read(self, contributor_name: ContributorName, table_names: Set[TableName] = None) -> List[TableData]:
        data_folder = self._repository_folder.get_data_folder_paths()
        if contributor_name not in data_folder:
            # No data for this contributor - a valid scenario when range is defined but a shared file across all
            # possible contributors, but in a given project a contributor is not envolved
            return []

        data_folder = data_folder[contributor_name]
        file_content_dict = FilesReader.read_folder_content(self._file_system_client, data_folder)

        table_data_list = []
        for file_name, file_content in file_content_dict.items():
            if not table_names or file_name in table_names:
                if file_name in self._reference_tables:
                    if file_content == "" and contributor_name == ContributorType.Customer.name:  # New empty file
                        continue
                    try:
                        file_model = DataFileModel.from_str(file_content)
                        table_data_list.append(TableDataFileModelAdapter.to_core_model(file_model, self._reference_tables[file_name]))
                    except Exception as e:
                        raise ValueError(f"Error reading data file. Table '{file_name}'") from e
                elif table_names:  # If table_names is not empty, we should raise an error if the file is not a reference table
                    raise ReferenceTableNotExistInRMTSpecError(file_name)

        return table_data_list

    def get_data_repository_path(self):
        return self._repository_folder.get_data_repository_path()

from typing import Dict, List, Set

from rmt.core.core_exceptions import ReferenceTableNotExistInRMTSpecError
from rmt.core.data_management.abstract_repository_folder_table_mapping_reader import AbstractRepositoryFolderTableMappingReader
from rmt.core.data_management.contributor import ContributorType
from rmt.core.data_management.primitive_types import ContributorName, TableName
from rmt.core.data_management.table_mapping import TableMapping
from rmt.file_model.data_management.data_management_context import DataManagementContext
from rmt.file_model.data_management.repository_folder import FolderPath
from rmt.file_model.data_management.table_mapping_file_model_adapter import TableMappingFileModelAdapter
from rmt.file_model.mapping_file_model import MappingFileModel
from rmt.filesystem.files_reader import FilesReader


class RepositoryFolderTableMappingReader(AbstractRepositoryFolderTableMappingReader):

    def __init__(self, data_management_context: DataManagementContext):
        self._reference_tables = data_management_context.reference_tables
        self._file_system_client = data_management_context.file_system_client
        self._repository_folder = data_management_context.repository_folder

    def read(self, contributor_name: ContributorName, table_names: Set[TableName] = None) -> List[TableMapping]:
        mapping_folders: Dict[ContributorName, FolderPath] = self._repository_folder.get_mapping_folder_paths()
        if contributor_name not in mapping_folders:
            return []

        file_content_dict = FilesReader.read_folder_content(self._file_system_client, mapping_folders[contributor_name])
        table_mapping_list = []
        for file_name, file_content in file_content_dict.items():
            if not table_names or file_name in table_names:
                if file_name in self._reference_tables:
                    if file_content == "" and contributor_name == ContributorType.Customer.name:  # New empty file
                        continue

                    try:
                        file_model = MappingFileModel.from_str(file_content)
                    except Exception as e:
                        raise ValueError(f"Error reading mapping definition file '{file_name}': {str(e)}") from e
                    table_mapping_list.append(TableMappingFileModelAdapter.to_core_model(file_model, self._reference_tables[file_name]))
                elif table_names:  # If table_names is not empty, we should raise an error if the file is not a reference table
                    raise ReferenceTableNotExistInRMTSpecError(file_name)

        return table_mapping_list

    def get_mapping_repository_path(self):
        return self._repository_folder.get_mapping_folder_paths()

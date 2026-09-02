from typing import List

from rmt.core.core_exceptions import ReferenceTableNotExistInRMTSpecError
from rmt.core.data_management.abstract_repository_folder_table_data_writer import AbstractRepositoryFolderTableDataWriter
from rmt.core.data_management.contributor import ContributorType
from rmt.core.data_management.primitive_types import ContributorName
from rmt.core.data_management.table_data import TableData
from rmt.file_model.data_file_model import DataFileModel
from rmt.file_model.data_management.data_management_context import DataManagementContext
from rmt.file_model.data_management.table_data_file_model_adapter import TableDataFileModelAdapter


class RepositoryFolderTableDataWriter(AbstractRepositoryFolderTableDataWriter):

    def __init__(self, data_management_context: DataManagementContext):
        self._file_system_client = data_management_context.file_system_client
        self._repository_folder = data_management_context.repository_folder
        self._reference_tables = data_management_context.reference_tables

    def write(self, contributor_name: ContributorName, table_data_list: List[TableData]):
        data_folders = self._repository_folder.get_data_folder_paths()
        if contributor_name == ContributorType.Customer.name and contributor_name not in data_folders:
            # Create data path for customer
            data_folders[contributor_name] = self._repository_folder.construct_new_data_path(contributor_name)
        if contributor_name not in data_folders:
            raise ValueError(f"Error on writing data definitions to folder. Contributor {contributor_name} not found in the repository folder")

        output_folder = data_folders[contributor_name]
        error_messages = []
        file_models: List[DataFileModel] = []
        for table_data in table_data_list:
            if table_data.table_name not in self._reference_tables:
                raise ReferenceTableNotExistInRMTSpecError(table_data.table_name)
            else:
                reference_table = self._reference_tables[table_data.table_name]
                file_model = TableDataFileModelAdapter.from_core_model(table_data, reference_table)
                file_models.append(file_model)
        if len(error_messages) > 0:
            raise ValueError("\n".join(error_messages))

        for file_model in file_models:
            self._write_table_data_file_model(output_folder, file_model)

    def _write_table_data_file_model(self, output_folder: str, data_file_model: DataFileModel):
        file_path = self._file_system_client.join_paths(output_folder, data_file_model.adrmTableName)
        self._file_system_client.write_json_file(file_path, data_file_model.model_dump_json())

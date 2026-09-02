from typing import List

from rmt.core.core_exceptions import ReferenceTableNotExistInRMTSpecError
from rmt.core.data_management.abstract_repository_folder_table_mapping_writer import AbstractRepositoryFolderTableMappingWriter
from rmt.core.data_management.contributor import ContributorType
from rmt.core.data_management.primitive_types import ContributorName
from rmt.core.data_management.table_mapping import TableMapping
from rmt.file_model.data_management.data_management_context import DataManagementContext
from rmt.file_model.data_management.table_mapping_file_model_adapter import TableMappingFileModelAdapter
from rmt.file_model.mapping_file_model import MappingFileModel


class RepositoryFolderTableMappingWriter(AbstractRepositoryFolderTableMappingWriter):

    def __init__(self, data_management_context: DataManagementContext):
        self._file_system_client = data_management_context.file_system_client
        self._repository_folder = data_management_context.repository_folder
        self._reference_tables = data_management_context.reference_tables

    def write(self, contributor_name: ContributorName, table_mapping_list: List[TableMapping]):
        mapping_folders = self._repository_folder.get_mapping_folder_paths()

        if contributor_name == ContributorType.Customer.name and contributor_name not in mapping_folders:
            # Create mapping path for customer source domain when no source domain dir exists
            mapping_folders[contributor_name] = self._repository_folder.construct_new_mapping_path(contributor_name)

        if contributor_name not in mapping_folders:
            raise ValueError(f"Contributor {contributor_name} not found in the repository folder")

        output_folder = mapping_folders[contributor_name]
        for table_mapping in table_mapping_list:
            if table_mapping.table_name not in self._reference_tables:
                raise ReferenceTableNotExistInRMTSpecError(table_mapping.table_name)
            else:
                mapping_definition_file_model = TableMappingFileModelAdapter.from_core_model(table_mapping)
                self._write_mapping_file_model(output_folder, mapping_definition_file_model, table_mapping.table_name)

    def _write_mapping_file_model(self, output_folder: str, mapping_file_model: MappingFileModel, table_name: str):
        file_path = self._file_system_client.join_paths(output_folder, table_name)
        model_str = ""
        if mapping_file_model.values is not None:
            model_str = mapping_file_model.model_dump_json(by_alias=True)
        self._file_system_client.write_json_file(file_path, model_str)

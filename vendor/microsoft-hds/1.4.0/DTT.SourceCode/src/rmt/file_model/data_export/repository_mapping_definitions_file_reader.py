from rmt.file_model.data_management.data_management_context import DataManagementContext
from rmt.file_model.values_mapping.mapping_definitions_file_reader import MappingDefinitionsFileReader


class RepositoryMappingDefintionsFileReader(MappingDefinitionsFileReader):
    def __init__(self, data_management_context: DataManagementContext):
        super().__init__(
            data_management_context.file_system_client,
            list(data_management_context.repository_folder.get_mapping_folder_paths().values()),
            data_management_context.reference_tables,
        )

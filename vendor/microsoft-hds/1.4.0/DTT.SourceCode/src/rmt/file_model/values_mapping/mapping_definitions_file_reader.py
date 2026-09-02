from typing import Dict, List

from rmt.core.values_mapping.mapping_definition import MappingDefinition
from rmt.core.values_mapping.mapping_definitions_reader import MappingDefinitionsReader
from rmt.core.values_mapping.reference_table import ReferenceTable
from rmt.file_model.values_mapping.mapping_definition_file_model_adapter import MappingDefinitionFileModelAdapter
from rmt.filesystem.file_system_client import FileSystemClient
from rmt.filesystem.files_reader import FilesReader


class MappingDefinitionsFileReader(MappingDefinitionsReader):
    @property
    def sources(self) -> List[str]:
        return self.mapping_definitions_folders

    def __init__(
        self,
        file_system_client: FileSystemClient,
        mapping_definitions_folders: List[str],
        reference_tables: Dict[str, ReferenceTable],
    ):
        self.file_model_to_mapping_definition = MappingDefinitionFileModelAdapter(reference_tables)
        self.file_system_client = file_system_client
        self.mapping_definitions_folders = mapping_definitions_folders

    def read(self, source: str) -> List[MappingDefinition]:
        if source not in self.mapping_definitions_folders:
            raise ValueError(f"{source} is not a definitions folder")
        file_content_dict = FilesReader.read_folder_content(self.file_system_client, source)
        mapping_definitions = []
        for file_name, file_content in file_content_dict.items():
            mapping_definitions.append(self.file_model_to_mapping_definition.to_core_model(file_name, file_content))
        return mapping_definitions

from typing import Dict

from rmt.contract.configuration.reference_table import ReferenceTable
from rmt.file_model.data_management.repository_folder import FolderPath, RepositoryFolder
from rmt.filesystem.file_system_client import FileSystemClient


class DataManagementContext:
    def __init__(
        self,
        file_system_client: FileSystemClient,
        authoring_folder_path: FolderPath,
        repository_folder: RepositoryFolder,
        reference_tables: Dict[str, ReferenceTable],
    ):
        self.file_system_client = file_system_client
        self.authoring_folder_path = authoring_folder_path
        self.repository_folder = repository_folder
        self.reference_tables = reference_tables

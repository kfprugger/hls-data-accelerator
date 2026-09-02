from typing import Dict

from rmt.core.data_management.primitive_types import ContributorName
from rmt.filesystem.file_system_client import FileSystemClient

DATA_FOLDER = "data"
MAPPING_DEFINITIONS_FOLDER = "mapping"
CONTRIBUTORS_FILE = "contributors.json"
CUSTOMER_FOLDER = "Customer"

FolderPath = str
FilePath = str


class RepositoryFolder:
    """_summary_
    This class handles the repository folder paths logic
    it returns the contributors path, mapping paths by contributor name and data paths by contributor name
    """

    def __init__(self, file_system_client: FileSystemClient, source_domain: str, repository_folder_path: str):
        self._repository_folder_path = repository_folder_path
        self._file_system_client = file_system_client
        self._source_domain = source_domain
        self._contributors_path: FilePath = None
        self._mapping_definitions_folders: Dict[str, str] = {}
        self._data_definitions_folders: Dict[str, str] = {}
        self._contributors_file_name: str = CONTRIBUTORS_FILE
        self._data_folder_name: str = DATA_FOLDER
        self._mapping_folder_name: str = MAPPING_DEFINITIONS_FOLDER
        self._data_path: FolderPath = None
        self._mapping_path: FolderPath = None

    def get_mapping_folder_paths(self) -> Dict[ContributorName, FolderPath]:
        if not self._mapping_definitions_folders:
            mapping_path = self.get_mapping_repository_path()
            if self._file_system_client.path_exist(mapping_path):
                contributor_folder_paths = self._file_system_client.get_subfolders(mapping_path)
                for contributor_folder_path in contributor_folder_paths:
                    source_domain_folder_paths = self._file_system_client.get_subfolders(contributor_folder_path)
                    for source_domain_folder_path in source_domain_folder_paths:
                        source_domain_folder_name = self._file_system_client.get_folder_name(source_domain_folder_path)
                        if source_domain_folder_name == self._source_domain:
                            contributor_folder_name = self._file_system_client.get_folder_name(contributor_folder_path)
                            self._mapping_definitions_folders[contributor_folder_name] = source_domain_folder_path
            else:
                raise ValueError(f"Mapping definitions folder {mapping_path} does not exist")
        return self._mapping_definitions_folders

    def get_data_folder_paths(self) -> Dict[ContributorName, FolderPath]:
        if not self._data_definitions_folders:
            data_path = self.get_data_repository_path()
            if self._file_system_client.path_exist(data_path):
                contributor_folder_paths = self._file_system_client.get_subfolders(data_path)
                for contributor_folder_path in contributor_folder_paths:
                    contributor_folder_name = self._file_system_client.get_folder_name(contributor_folder_path)
                    self._data_definitions_folders[contributor_folder_name] = contributor_folder_path
            else:
                raise ValueError(f"Data definitions folder {data_path} does not exist")
        return self._data_definitions_folders

    def get_mapping_repository_path(self) -> FolderPath:
        if not self._mapping_path:
            self._mapping_path = self._file_system_client.get_file_path_case_insensitive(self._repository_folder_path, self._mapping_folder_name)
        return self._mapping_path

    def get_data_repository_path(self) -> FolderPath:
        if not self._data_path:
            self._data_path = self._file_system_client.get_file_path_case_insensitive(self._repository_folder_path, self._data_folder_name)
        return self._data_path

    def get_contributors_path(self) -> FilePath:

        if not self._contributors_path:
            self._contributors_path = self._file_system_client.get_file_path_case_insensitive(self._repository_folder_path, self._contributors_file_name)
        return self._contributors_path

    def construct_new_mapping_path(self, contributor: str) -> FolderPath:
        return self._file_system_client.join_paths(self._file_system_client.join_paths(self.get_mapping_repository_path(), contributor), self._source_domain)

    def construct_new_data_path(self, contributor: str) -> FolderPath:
        return self._file_system_client.join_paths(self.get_data_repository_path(), contributor)

from enum import Enum
from typing import List, Set

from rmt.core.data_management.contributor import Contributor
from rmt.file_model.data_management.contributors_json_reader import ContributorsFileReader
from rmt.file_model.data_management.data_management_context import DataManagementContext
from rmt.file_model.data_management.repository_folder import RepositoryFolder
from rmt.filesystem.file_system_client import FileSystemClient


class FolderType(Enum):
    data = 1
    mapping = 2


class PathsParametersHandler:
    def __init__(self, file_system_client: FileSystemClient, source_domain: str):
        self._file_system_client = file_system_client
        self._source_domain = source_domain

    def _get_contributors(self, repository_folder: RepositoryFolder) -> Set[Contributor]:
        data_management_context = DataManagementContext(self._file_system_client, "", repository_folder, {})
        contributors_file_reader = ContributorsFileReader(data_management_context)
        return contributors_file_reader.read()

    def raise_error_if_folder_not_exist(self, folder_path: str):
        if self._file_system_client.path_exist(folder_path) is False:
            raise ValueError(f"Input folder {folder_path} does not exist")

    def _raise_error_if_folders_not_exist(self, folder_paths: List[str], error_message: str) -> str:
        all_folders_exist = True
        for folder in folder_paths:
            if self._file_system_client.path_exist(folder) is False:
                all_folders_exist = False
                error_message += f" {folder}."
        if not all_folders_exist:
            raise ValueError(error_message)

    def _get_folders_from_parameters_folders_and_staging_folder(self, folder_paths: List[str], staging_folder_path: str, folder_type: FolderType) -> List[str]:

        if (folder_paths and staging_folder_path) or (not folder_paths and not staging_folder_path):
            raise ValueError(f"Exactly one of {folder_type.name} folders or staging_reference_data_folder_path must be provided")
        result_folder_paths = []
        if staging_folder_path:
            self.raise_error_if_folder_not_exist(staging_folder_path)
            repository_folder = RepositoryFolder(self._file_system_client, self._source_domain, staging_folder_path)
            contributors = self._get_contributors(repository_folder)
            if folder_type == FolderType.data:
                all_folder_paths = repository_folder.get_data_folder_paths()
            elif folder_type == FolderType.mapping:
                all_folder_paths = repository_folder.get_mapping_folder_paths()
            else:
                raise ValueError(f"Invalid folder type: {folder_type}")
            result_folder_paths = [all_folder_paths[contributor.name] for contributor in contributors if contributor.name in all_folder_paths]
        else:
            message = "One or more of the mapping definitions folders do not exist:"
            self._raise_error_if_folders_not_exist(folder_paths, message)
            result_folder_paths = folder_paths

        return result_folder_paths

    def get_mapping_folder_paths(self, folder_paths: List[str], staging_folder_path: str) -> List[str]:
        return self._get_folders_from_parameters_folders_and_staging_folder(folder_paths, staging_folder_path, FolderType.mapping)

    def get_data_folder_paths(self, folder_paths: List[str], staging_folder_path: str) -> List[str]:
        return self._get_folders_from_parameters_folders_and_staging_folder(folder_paths, staging_folder_path, FolderType.data)

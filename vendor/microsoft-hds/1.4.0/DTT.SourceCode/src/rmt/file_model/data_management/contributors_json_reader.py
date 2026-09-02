from typing import Set

from rmt.core.data_management.abstract_contributors_reader import AbstractContributorsReader
from rmt.core.data_management.contributor import Contributor
from rmt.file_model.data_management.contributors_file_model import ContributorsFileModel
from rmt.file_model.data_management.contributors_file_model_adapter import ContributorsFileModelAdapter
from rmt.file_model.data_management.data_management_context import DataManagementContext


class ContributorsFileReader(AbstractContributorsReader):

    def __init__(self, datamanagement_context: DataManagementContext):
        self._file_system_client = datamanagement_context.file_system_client
        self._repository_folder = datamanagement_context.repository_folder

    def read(self) -> Set[Contributor]:
        if not self._file_system_client.path_exist(self._repository_folder.get_contributors_path()):
            raise ValueError(f"Contributors file {self._repository_folder} does not exist")
        file_path = self._repository_folder.get_contributors_path()
        contributors_file = self._file_system_client.get_file_content_from_path(file_path)
        contributors_file_model = ContributorsFileModel.from_str(contributors_file)
        return set(ContributorsFileModelAdapter.to_core_model(contributors_file_model).values())

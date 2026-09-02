from abc import ABC, abstractmethod
from typing import List, Optional, Union

from pyspark.sql import DataFrame
from urllib3.util import Url


class FileSystemClient(ABC):
    @abstractmethod
    def get_file_content_from_path(self, file_path: Union[Url, str]) -> str:
        pass

    @abstractmethod
    def get_file_content(self, folder_url: Union[Url, str], file_name: str) -> str:
        pass

    @abstractmethod
    def list_files(self, folder_url: Union[Url, str], file_type: Optional[str]) -> List[str]:
        pass

    @abstractmethod
    def join_paths(self, url1: Union[Url, str], url2: Union[Url, str]) -> str:
        pass

    @abstractmethod
    def path_exist(self, url: Union[Url, str]) -> bool:
        pass

    @abstractmethod
    def get_all_subfolders(self, folders: List[Union[Url, str]]) -> List[str]:
        pass

    @abstractmethod
    def get_subfolders(self, folder: Union[Url, str]) -> List[str]:
        pass

    @abstractmethod
    def get_folder_name(self, folder_path: Union[Url, str]) -> str:
        pass

    @abstractmethod
    def write_csv_file(self, path: Union[Url, str], df: DataFrame):
        pass

    @abstractmethod
    def write_json_file(self, path: Union[Url, str], content: str):
        pass

    @abstractmethod
    def get_file_path_case_insensitive(self, folder_path: str, file_name: str, file_type: str | None = None) -> str:
        pass

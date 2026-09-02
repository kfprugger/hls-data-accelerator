import os.path
from typing import List, Optional, Union

try:
    from notebookutils.fs import exists, ls, mv, rm  # noqa: F401
except ImportError as ie:
    raise ImportError("NotebookUtilsFileSystemClient requires Azure Fabric or Synapse as runtime") from ie

from pyspark.sql import SparkSession
from urllib3.util import Url

from rmt.runners.spark_file_system_client import SparkFileSystemClient


class NotebookUtilsFileSystemClient(SparkFileSystemClient):
    def __init__(self, spark: SparkSession):
        super().__init__(spark)

    def list_files(self, folder_url: Union[Url, str], file_type: Optional[str] = None) -> List[str]:
        if file_type:
            return [f.name for f in ls(folder_url) if f.name.endswith(f".{file_type}")]
        else:
            return [f.name for f in ls(folder_url)]

    def path_exist(self, url: Union[Url, str]) -> bool:
        return exists(url)

    def get_all_subfolders(self, folders: List[Union[Url, str]]) -> list[str]:
        all_subfolders = []
        for folder in folders:
            all_subfolders.append(folder)
            for f in ls(folder):
                if f.isDir:
                    all_subfolders.extend(self.get_all_subfolders([f.path]))
        return all_subfolders

    def get_subfolders(self, folder: Union[Url, str]) -> List[str]:
        subfolders = []
        for f in ls(folder):
            if f.isDir:
                subfolders.append(f.path)
        return subfolders

    def join_paths(self, url1: Union[Url, str], url2: Union[Url, str]) -> str:
        return os.path.join(url1, url2)

    def _rename_and_move_partition(self, path: Union[Url, str], filename: Union[Url, str], file_type: str):
        files = [file.path for file in ls(path) if file.path.endswith(f".{file_type}")]
        if len(files) == 1:
            file = files[0]
            previous_path = file.rsplit("/", 2)[0]
            destination_path = f"{previous_path}/{filename}.{file_type}"
            mv(file, destination_path, True, True)  # Move file , create if not exists, overwrite if exists
            rm(path, True)

import os.path
import shutil
from glob import glob
from pathlib import Path
from typing import List, Optional, Union

from pyspark.sql import DataFrame, SparkSession
from urllib3.util import Url

from rmt.filesystem.file_system_client import FileSystemClient


class SparkFileSystemClient(FileSystemClient):
    def __init__(self, spark: SparkSession):
        self.spark = spark

    def get_file_content_from_path(self, file_path: Union[Url, str]) -> str:
        rdd = self.spark.sparkContext.wholeTextFiles(file_path)
        return rdd.collect()[0][1]

    def get_file_content(self, folder_url: Union[Url, str], file_name: str) -> str:
        rdd = self.spark.sparkContext.wholeTextFiles(folder_url + "/" + file_name)
        return rdd.collect()[0][1]

    def list_files(self, folder_url: Union[Url, str], file_type: Optional[str] = None) -> List[str]:
        rdd = self.spark.sparkContext.wholeTextFiles(folder_url)
        if file_type:
            files = rdd.filter(lambda x: x[0].endswith(f".{file_type}")).map(lambda x: os.path.basename(x[0]))
        else:
            files = rdd.map(lambda x: os.path.basename(x[0]))
        return files.collect()

    def join_paths(self, url1: Union[Url, str], url2: Union[Url, str]) -> str:
        return os.path.join(url1, url2)

    def path_exist(self, url: Union[Url, str]) -> bool:
        try:
            self.spark.sparkContext.wholeTextFiles(url)
            return True
        except Exception:
            return False

    def get_all_subfolders(self, folders: List[Union[Url, str]]) -> List[str]:
        raise NotImplementedError("get_all_subfolders is not implemented for SparkFileSystemClient")

    def get_subfolders(self, folder: Union[Url, str]) -> List[str]:
        raise NotImplementedError("get_subfolders is not implemented for SparkFileSystemClient")

    def get_folder_name(self, folder_path: Union[Url, str]) -> str:
        return Path(folder_path).name

    def write_csv_file(self, path: Union[Url, str], df: DataFrame):
        df.repartition(1).write.csv(path, mode="overwrite", header=True)
        filename = self._get_file_name(path)
        self._rename_and_move_partition(path, filename, "csv")

    def write_json_file(self, path: Union[Url, str], content: str):
        df = self.spark.read.json(self.spark.sparkContext.parallelize([content]))
        df.repartition(1).write.json(path)
        filename = self._get_file_name(path)
        self._rename_and_move_partition(path, filename, "json")

    def get_file_path_case_insensitive(self, folder_path: str, file_name: str, file_type: str | None = None) -> str:
        path = self.join_paths(folder_path, file_name)
        if not self.path_exist(path):
            file_name = self._get_file_name_case_insensitive(folder_path, file_name, file_type)
            path = self.join_paths(folder_path, file_name)
        return path

    def _get_file_name_case_insensitive(self, folder_url: Union[Url, str], file_name: str, file_type: str | None = None):
        folders = self.list_files(folder_url, file_type)
        for folder in folders:
            if folder.lower() == file_name.lower():
                return folder
        return None

    def _rename_and_move_partition(self, path: Union[Url, str], filename: Union[Url, str], file_type: str):

        csv_files = glob(f"{path}/*.{file_type}")
        if len(csv_files) == 1:
            csv_file = csv_files[0]
            new_csv_file_name = os.path.join(path, f"{filename}.{file_type}")
            os.rename(csv_file, new_csv_file_name)
            previous_path = os.path.dirname(path)
            destination_path = os.path.join(previous_path, f"{filename}.{file_type}")
            if os.path.exists(destination_path):
                os.remove(destination_path)
            shutil.move(new_csv_file_name, previous_path)
            shutil.rmtree(path)

    def _get_file_name(self, path: Union[Url, str]):
        parts = path.rsplit("/", 1)
        filename_with_type = parts[-1]
        filename_parts = filename_with_type.rsplit(".", 1)
        filename = filename_parts[0]
        return filename

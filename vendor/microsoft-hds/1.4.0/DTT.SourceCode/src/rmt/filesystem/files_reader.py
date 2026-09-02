from typing import Dict, List, Optional

from rmt.filesystem.file_system_client import FileSystemClient
from rmt.tools.logging import Logger


class FilesReader:
    @staticmethod
    def read_folder_content(file_system_client: FileSystemClient, path: str, file_names: Optional[List[str]] = None) -> Dict[str, str]:
        """read all json files in a folder and return a dict of file name to file content"""
        Logger.debug(f"Reading files from folder {path}, file names: {file_names}")
        files_dict = {}
        folder_file_names = file_system_client.list_files(path, "json")
        Logger.debug(f"Reading files from folder {path}: {folder_file_names}")

        if file_names is None:
            file_names = folder_file_names

        for file_name in file_names:
            if not file_name.endswith(".json"):  # need to add .json in order to read
                file_name += ".json"
            if file_name in folder_file_names:
                file_content = file_system_client.get_file_content(path, file_name)
                files_dict[file_name[: -len(".json")]] = file_content
            else:
                raise FileNotFoundError(f"Missing configuration file: {file_name} in folder {path}")
        return files_dict

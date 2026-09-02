import os
from pathlib import Path
import random
import string
from typing import Any, Optional

from configuration_compiler.path_helpers import is_a_file_uri, is_azure_blob_storage_uri, uri_to_path, uri_parent_path


class LocalFileSystemAccess:
    def __init__(self, path_uri: str, mode: str, notebookutils: Optional[Any] = None) -> None:
        modes = set(mode)
        if modes - set("axrwb+t") or len(mode) > len(modes):
            raise ValueError("invalid mode: %r" % mode)
        self.mode = mode
        self.source = path_uri
        self.notebookutils = notebookutils
        self.mount_point = f"/{self._generate_random_string()}"
        self.locally_mounted_path: Path

    def __enter__(self):
        self._ensure_file_system_is_accessible()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._unmount_filesystem_locally()

    def _ensure_file_system_is_accessible(self):
        if is_a_file_uri(self.source) or os.path.isabs(self.source):
            local_path = uri_to_path(self.source)
            self._create_filesystem_dir_if_not_exist_for_path_uri(local_path)
            has_access = self._get_filesystem_access_errors(local_path)
            self.locally_mounted_path = local_path

        elif is_azure_blob_storage_uri(self.source):
            if not self.notebookutils:
                raise RuntimeError("Cannot mount filesystem locally. notebookutils is not available.")
            self._create_filesystem_dir_if_not_exist_for_azure_blob_storage(self.source)
            self.locally_mounted_path = self._mount_filesystem_locally(self.source)
            has_access = self._get_filesystem_access_errors(self.locally_mounted_path)

        else:
            raise RuntimeError(f"Unsupported file system for: {self.source}")

        if not has_access:
            raise RuntimeError(f"Cannot access filesystem: {self.source} for mode={self.mode}")

    def _get_filesystem_access_errors(self, path: Path) -> bool:
        # ========= ===============================================================
        # Character Meaning
        # --------- ---------------------------------------------------------------
        # 'r'       open for reading (default)
        # 'w'       open for writing, truncating the file first
        # 'x'       create a new file and open it for writing
        # 'a'       open for writing, appending to the end of the file if it exists
        # 'b'       binary mode
        # 't'       text mode (default)
        # '+'       open a disk file for updating (reading and writing)
        # ========= ===============================================================
        if set("rbt").issuperset(set(self.mode)):
            return self._filesystem_has_read_permissions(path)
        else:
            return self._filesystem_has_write_permissions(path)

    def _filesystem_has_read_permissions(self, path: Path) -> bool:
        return os.access(path, os.R_OK)

    def _filesystem_has_write_permissions(self, path: Path) -> bool:
        return os.access(path, os.W_OK) or os.access(path, os.X_OK)

    def _mount_filesystem_locally(self, path: str) -> Path:
        locally_mounted_path = self._get_locally_mounted_path(path)
        if not locally_mounted_path:
            self.notebookutils.fs.mount(path, self.mount_point, {"fileCacheTimeout": 0})
            # self.notebookutils.fs.mount(path, self.mount_point)
            locally_mounted_path = self.notebookutils.fs.getMountPath(self.mount_point)
        return Path(locally_mounted_path)

    def _unmount_filesystem_locally(self) -> None:
        if not self.notebookutils:
            return
        if self._is_mounted_locally():
            self.notebookutils.fs.unmount(self.mount_point)

    def _get_locally_mounted_path(self, path: str) -> Optional[str]:
        mounts = self.notebookutils.fs.mounts()
        for mount in mounts:
            if mount["source"] == path:
                return mount["localPath"]
        return None

    def _is_mounted_locally(self) -> bool:
        mounts = self.notebookutils.fs.mounts()
        for mount in mounts:
            if mount["mountPoint"] == self.mount_point:
                return True
        return False

    def _generate_random_string(self):
        return "".join(random.choice(string.ascii_uppercase) for _ in range(10))

    def adapt_to_local_path(self, path: str) -> Path:
        if not self.locally_mounted_path:
            raise ValueError("Run as a context manager to get the locally mounted path") #kobichangeQ
        return self.locally_mounted_path / Path(path).name
    def _create_filesystem_dir_if_not_exist_for_path_uri(self, path: Path):
        if not path.exists():
            path.mkdir(parents=True)

    def _create_filesystem_dir_if_not_exist_for_azure_blob_storage(self, path: str):
        if not self.notebookutils.fs.exists(path):
            self.notebookutils.fs.mkdirs(path)

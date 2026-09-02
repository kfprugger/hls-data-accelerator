from abc import ABC, abstractmethod
from typing import List, Union

from urllib3.util import Url


class MSSparkUtilsClientBase(ABC):
    @abstractmethod
    def fs_ls(self, folder_url: Union[Url, str]) -> List[str]:
        pass
    
    @abstractmethod
    def fs_exists(self, file_url: Union[Url, str]) -> bool:
        pass
    
    @abstractmethod
    def fs_put(self, file_url: Union[Url, str], file_content: str, overwrite: bool) -> None:
        pass
    
    @abstractmethod
    def fs_mkdirs(self, folder_url: Union[Url, str]) -> None:
        pass
    
    @abstractmethod
    def fs_mv(self, from_url: Union[Url, str], to_url: Union[Url, str], create_path: bool = False) -> None:
        pass
    
    @abstractmethod
    def fs_append(self, file_url: Union[Url, str], file_content: str, create_if_not_exists: bool = False) -> None:
        pass
    
    @abstractmethod
    def fs_rm(self, folder_url: Union[Url, str], recursive: bool) -> None:
        pass
    
    @abstractmethod
    def credentials_getSecret(self, key_vault: str, secret_name: str) -> str:
        pass
    
    @abstractmethod
    def credentials_getToken(self, audience: str) -> str:
        pass
    
    @abstractmethod
    def fs_mount(self, mount_path : str, mount_name : str, configs : dict = {}) -> None:
        pass
    
    @abstractmethod
    def fs_unmount(self, unmount_path : str) -> None:
        pass
    
    @abstractmethod
    def fs_get_mount_path(self, mount_point : str) -> str:
        pass
    
    @abstractmethod
    def get_runtime_context(self) -> dict:
        pass

    @abstractmethod
    def get_lakehouse(self, lakehouse_identifier: str, workspace_id: str = "") -> dict:
        pass

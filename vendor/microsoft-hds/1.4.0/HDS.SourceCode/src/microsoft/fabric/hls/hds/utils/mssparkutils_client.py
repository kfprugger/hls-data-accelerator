from typing import Any, List
from urllib3.util import Url
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase

try:
    from notebookutils import mssparkutils
except ModuleNotFoundError:
    pass

class MSSparkUtilsClient(MSSparkUtilsClientBase):
    def __init__(self):
        pass

    def fs_ls(self, folder_url: Url | str) -> List[any]:
        return mssparkutils.fs.ls(folder_url)

    def fs_exists(self, file_url: Url | str) -> bool:
        return mssparkutils.fs.exists(file_url)
    
    def fs_put(self, file_url: Url | str, file_content: str, overwrite: bool) -> None:
        mssparkutils.fs.put(file_url, file_content, overwrite=overwrite)
        
    def fs_mkdirs(self, folder_url: Url | str) -> None:
        mssparkutils.fs.mkdirs(folder_url)
            
    def fs_append(self, file_url: Url | str, file_content: str, create_if_not_exists: bool = False) -> None:
        mssparkutils.fs.append(file_url, file_content, create_if_not_exists)
        
    def fs_mv(self, from_url: Url | str, to_url: Url | str, create_path: bool = False) -> None:
        mssparkutils.fs.mv(from_url, to_url, create_path)
    
    def fs_rm(self, folder_url: Url | str, recursive: bool) -> None:
        mssparkutils.fs.rm(folder_url, recursive)
        
    def credentials_getSecret(self, key_vault: str, secret_name: str) -> str:
        return mssparkutils.credentials.getSecret(key_vault, secret_name)
    
    def credentials_getToken(self, audience: str) -> str:
        return mssparkutils.credentials.getToken(audience)
    
    def fs_mount(self, mount_path : str, mount_name : str, configs : dict = {}):
        mssparkutils.fs.mount(mount_path, mount_name, configs)
        
    def fs_unmount(self, unmount_path : str):
        mssparkutils.fs.unmount(unmount_path)

    def fs_get_mount_path(self, mount_point : str) -> str :
        return mssparkutils.fs.getMountPath(mount_point)
    
    def get_runtime_context(self) -> dict:
        return mssparkutils.runtime.context

    def get_lakehouse(self, lakehouse_identifier: str, workspace_id: str = "") -> dict:
            return mssparkutils.lakehouse.get(lakehouse_identifier, workspace_id)
    
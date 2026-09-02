from azure.storage.blob import BlobServiceClient
from azure.storage.filedatalake import DataLakeServiceClient
from azure.identity import DefaultAzureCredential
from .base_task import BaseTask
from models.lakehouse import Lakehouse
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class CopyFromStorageAccount(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_lakehouse: Lakehouse = None

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs, None)
        blob_storage_account_url = get_value('blob_storage_account_url', self.context, kwargs)
        container_name = get_value('container_name', self.context, kwargs)
        source_subpath = get_value('source_subpath', self.context, kwargs)
        destination_lakehouse_name = get_value('destination_lakehouse_name', self.context, kwargs)
        destination_subpath = get_value('destination_subpath', self.context, kwargs)
        
        lakehouses = self.fabric_client.get_lakehouses(workspace.id)
        
        target_lakehouse_id = None
        target_lakehouse_name = destination_lakehouse_name.lower()
        for lakehouse in lakehouses:
            if lakehouse.displayName.lower() == target_lakehouse_name.lower():
                target_lakehouse_id = lakehouse.id
                target_lakehouse = lakehouse
                break

        if target_lakehouse_id is None:
            self.logger.info(f"Data configuration lakehouse: {target_lakehouse_name} not found")
        
        chunk_size = 16*1024*1024
        
        # Initialize BlobServiceClient
        blob_service_client = BlobServiceClient(
            account_url=blob_storage_account_url, # ex. "https://stghdssampledatadev.blob.core.windows.net/"
            # CodeQL [SM05139] This is non-production testing code which is not deployed.
            credential=DefaultAzureCredential(),
            max_chunk_get_size=chunk_size,
            max_single_get_size=chunk_size)

        container_client = blob_service_client.get_container_client(container_name)
        
        account_url = f"https://{self.fabric_client.env}-onelake.dfs.fabric.microsoft.com/{target_lakehouse.workspaceId}/{target_lakehouse.id}"
        # CodeQL [SM05139] This is non-production testing code which is not deployed.
        service_client = DataLakeServiceClient(account_url=account_url, credential=DefaultAzureCredential())

        fs_client = service_client.get_file_system_client("Files")

        # Iterate over blobs in the specified subpath
        blobs = container_client.list_blobs(name_starts_with=source_subpath)

        for blob in blobs:
        
            # Only copy ndjson/csv files
            if "json" in blob.name or "csv" in blob.name:
                
                blob_client = container_client.get_blob_client(blob)
                blob_name = blob.name.split("/")[-1]
                
                if destination_subpath is not None and len(destination_subpath) > 0:
                    destination_path = destination_subpath + "/" + blob_name
                else:
                    destination_path = f"{blob.name}"
                
                # Allow config to start with Files but ignore in the client
                # to prevent Files/Files/...
                if destination_path.startswith("/Files"):
                    destination_path = destination_path[len("/Files"):]
                elif destination_path.startswith("Files"):
                    destination_path = destination_path[len("Files"):]
                
                file_client = fs_client.create_file(destination_path)
                
                chunk_count = 1
                offset = 0
                for chunk in blob_client.download_blob().chunks():
                    print(f"uploading chunk for file {blob_name}, chunk {chunk_count} with size {len(chunk)}")
                    file_client.append_data(data=chunk, offset=offset, length=len(chunk))
                    offset += len(chunk)
                    chunk_count += 1
                
                file_client.flush_data(offset)

                print(f"Copied {blob_name} to {destination_path}")

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("CopyFromStorageAccount: workspace is a required parameter.")
        
        if "blob_storage_account_url" not in kwargs:
            raise AutomationFrameworkValidationException("CopyFromStorageAccount: blob_storage_account_url is a required parameter.")
        
        if "container_name" not in kwargs:
            raise AutomationFrameworkValidationException("CopyFromStorageAccount: container_name is a required parameter.")
        
        if "source_subpath" not in kwargs:
            raise AutomationFrameworkValidationException("CopyFromStorageAccount: source_subpath is a required parameter.")
        
        if "destination_lakehouse_name" not in kwargs:
            raise AutomationFrameworkValidationException("CopyFromStorageAccount: destination_lakehouse_name is a required parameter.")
        
        if "destination_subpath" not in kwargs:
            raise AutomationFrameworkValidationException("CopyFromStorageAccount: destination_subpath is a required parameter.")

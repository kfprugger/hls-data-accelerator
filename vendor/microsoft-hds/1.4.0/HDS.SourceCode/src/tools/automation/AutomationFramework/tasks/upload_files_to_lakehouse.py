import os
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
import json

from .base_task import BaseTask
from models.workspace import Workspace
from models.lakehouse import Lakehouse
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException
from logging import Logger
from utils.context_utils import get_value

class UploadFilesToLakehouse(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs, None)
        target_lakehouse: Lakehouse = get_value('target_lakehouse', self.context, kwargs)
        local_src_path = get_value('local_src_path', self.context, kwargs)
        destination_path = get_value('destination_path', self.context, kwargs)
        target_environment = get_value('target_environment', self.context, kwargs)

        account_url = f"https://{target_environment}-onelake.dfs.fabric.microsoft.com/{workspace.id}/{target_lakehouse.id}"
        # CodeQL [SM05139] This is non-production testing code which is not deployed.
        service_client = DataLakeServiceClient(account_url=account_url, credential=DefaultAzureCredential())

        root_target_dir = destination_path.split("/")[0]
        
        if str(root_target_dir).lower() not in ["files", "tables"]:
            raise AutomationFrameworkRuntimeException(f"Lakehouse target directory must start with Files or Tables: {root_target_dir}")
        
        fs_client = service_client.get_file_system_client(root_target_dir)
        full_source_path = os.getcwd() + local_src_path
        files_to_upload = self.flatten_local_directory(full_source_path)
        
        for file_name in files_to_upload:
            self.logger.info("Uploading file: " + file_name)
            
            destination_file_path = file_name[len(full_source_path):] 
            target_subpath = destination_path[len(root_target_dir):] 
            file_client = fs_client.get_file_client(target_subpath + destination_file_path)
            file_client.create_file()
            with open(file_name, 'rb') as file:            
                file_client.upload_data(file, overwrite=True)
    
    def flatten_local_directory(self, directory_path):
        flat_file_list = []

        for root, dirs, files in os.walk(directory_path):
            for file in files:
                flat_file_list.append(os.path.join(root, file))

        return flat_file_list
            
    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("UploadFilesToLakehouse: workspace is a required parameter.")
        
        if "target_lakehouse" not in kwargs:
            raise AutomationFrameworkValidationException("UploadFilesToLakehouse: target_lakehouse is a required parameter.")
        
        
        if "local_src_path" not in kwargs:
            raise AutomationFrameworkValidationException("UploadFilesToLakehouse: local_src_path is a required parameter.")
        
        if "destination_path" not in kwargs:
            raise AutomationFrameworkValidationException("UploadFilesToLakehouse: destination_path is a required parameter.")        
        
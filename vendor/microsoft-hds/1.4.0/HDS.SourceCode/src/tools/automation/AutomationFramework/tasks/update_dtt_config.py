import json
import os
from typing import Dict
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient
import json
from .base_task import BaseTask
from models.workspace import Workspace
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger
from utils.context_utils import get_value

class UpdateDttConfig(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs, None)
        soluation_artifact_id = get_value('soluation_artifact_id', self.context, kwargs)
        dtt_config_path = get_value('dtt_config_path', self.context, kwargs)

        account_url = f"https://{self.fabric_client.env}-onelake.dfs.fabric.microsoft.com/{workspace.id}/{soluation_artifact_id}"
        # CodeQL [SM05139] This is non-production testing code which is not deployed.
        service_client = DataLakeServiceClient(account_url=account_url, credential=DefaultAzureCredential())

        fs_client = service_client.get_file_system_client("DMHConfiguration")

        paths = list(fs_client.get_paths())        
        relative_path = os.getcwd() + dtt_config_path
        local_dtt_config_files = os.listdir(relative_path)
        
        for path in paths:
            if 'json' in path.name and "/fhir4/transformation/omop/" in path.name:
                file_path = path.name.split("DMHConfiguration")[-1]
                file_name = file_path.split("/")[-1]
                file_client = fs_client.get_file_client(file_path)

                # Only swap the file if it exists locally
                if file_name in local_dtt_config_files:
                    self.logger.info(f"Updating dtt file: {file_path}")
                    file_client.delete_file()
                    file_client.create_file()
                    with open(relative_path + "/" + file_name, 'r') as file:
                        dtt_config_content = json.load(file)
                        new_content_str = json.dumps(dtt_config_content, indent=2)                        
                        file_client.upload_data(data=new_content_str, length=len(new_content_str), overwrite=True)

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("UpdateDttConfig: workspace is a required parameter.")
        
        if "soluation_artifact_id" not in kwargs:
            raise AutomationFrameworkValidationException("UpdateDttConfig: soluation_artifact_id is a required parameter.")
        
        if "dtt_config_path" not in kwargs:
            raise AutomationFrameworkValidationException("UpdateDttConfig: dtt_config_path is a required parameter.")
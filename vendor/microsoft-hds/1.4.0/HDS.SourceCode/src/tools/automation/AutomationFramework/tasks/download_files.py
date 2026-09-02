import json
import os
from .base_task import BaseTask
from models.workspace import Workspace
from models.lakehouse import Lakehouse
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger
from utils.upload_files import get_files_client

class DownloadFiles(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        lakehouse: Lakehouse = get_value('lakehouse', self.context, kwargs)
        lakehouse_path = get_value('lakehouse_path', self.context, kwargs)
        local_directory_path = get_value('local_directory_path', self.context, kwargs)

        fs_client = get_files_client(workspace.id, lakehouse.id)
        
        paths = list(fs_client.get_paths(path=lakehouse_path, recursive=True))
        
        for path in paths:
            if not path.is_directory:
                file_path = path.name.split(lakehouse_path)[1]
                print(f"Downloading file: {file_path}")
                
                file_client = fs_client.get_file_client(file_path)
                file_content = file_client.download_file().readall()

                # Write the file content to the local directory
                local_file_path = os.path.join(local_directory_path, os.path.basename(path.name))
                
                os.makedirs("Tests/", exist_ok=True)
                os.makedirs("Tests/Results", exist_ok=True)
                
                write_path = os.getcwd() + local_file_path
                
                with open(write_path, 'wb') as output_file:
                    output_file.write(file_content)

    def onComplete(self, **kwargs):
        pass
    
    def validate_args(self, **kwargs) -> bool:
        
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("DownloadFiles: workspace is required")
        
        if "lakehouse" not in kwargs:
            raise AutomationFrameworkValidationException("DownloadFiles: lakehouse is required")
        
        if "lakehouse_path" not in kwargs:
            raise AutomationFrameworkValidationException("DownloadFiles: lakehouse_path is required")
        
        if "local_directory_path" not in kwargs:
            raise AutomationFrameworkValidationException("DownloadFiles: local_directory_path is required")
        
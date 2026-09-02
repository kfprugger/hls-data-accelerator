import json
import os
from models.create_lakehouse_request import CreateLakehouseRequest
from models.workspace import Workspace
from models.environment import Environment
from .base_task import BaseTask
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class UploadLibrary(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_environment: Environment = None

    def execute(self, **kwargs):
        workspace: Workspace = get_value('workspace', self.context, kwargs)
        environment: Environment = get_value('environment', self.context, kwargs, None)
        libraries_relative_path: str = get_value('libraries_relative_path', self.context, kwargs)
        environment_yml_path: str = get_value('environment_yml_path', self.context, kwargs)
        environment_spark_compute_settings = get_value('environment_spark_compute_settings', self.context, kwargs)
        
        file_dir = os.path.dirname(__file__).split("src")[0]
        dir_path = file_dir + libraries_relative_path

        for file in os.listdir(dir_path):
            if str(file).endswith("whl"):
                file_path = libraries_relative_path + file
                self.fabric_client.upload_library_to_environment(workspace.id, environment.id, file_path)

        self.fabric_client.upload_library_to_environment(workspace.id, environment.id, environment_yml_path)

        if environment_spark_compute_settings:    
            self.logger.info(f"updating environment spark compute settings")
            self.fabric_client.update_environment_spark_compute(workspace.id, environment.id, environment_spark_compute_settings)
        return environment

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("UploadLibrary: workspaceName is a required parameter.")
        
        if "environment" not in kwargs:
            raise AutomationFrameworkValidationException("UploadLibrary: environment is a required parameter.")

        if "libraries_relative_path" not in kwargs:
            raise AutomationFrameworkValidationException("UploadLibrary: libraries_relative_path is a required parameter.")

        if "libraries_relative_path" not in kwargs:
            raise AutomationFrameworkValidationException("UploadLibrary: environment_yml_path is a required parameter.")
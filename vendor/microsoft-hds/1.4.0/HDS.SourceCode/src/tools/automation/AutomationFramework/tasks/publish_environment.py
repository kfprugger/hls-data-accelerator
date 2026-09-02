import json
import os
from models.create_lakehouse_request import CreateLakehouseRequest
from models.workspace import Workspace
from models.environment import Environment
from .base_task import BaseTask
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class PublishEnvironment(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_environment: Environment = None

    def execute(self, **kwargs):
        workspace: Workspace = get_value('workspace', self.context, kwargs)
        display_name: str = get_value('displayName', self.context, kwargs)
        description: str = get_value('description', self.context, kwargs)
        environment: Environment = get_value('environment', self.context, kwargs, None)
        environment_spark_compute_settings = get_value('environment_spark_compute_settings', self.context, kwargs)
        environment_yml_path: str = get_value('environment_yml_path', self.context, kwargs)
        
        
        if environment is None:
            environment = self.fabric_client.create_environment(
                workspace.id, 
                CreateLakehouseRequest(display_name, description)
            )
        
            self.logger.info(f"created new environment:")
            self.logger.info(json.dumps(environment.to_dict(), indent=2))

        if environment_yml_path:
            self.fabric_client.upload_library_to_environment(workspace.id, environment.id, environment_yml_path)

        if environment_spark_compute_settings:    
            self.logger.info(f"updating environment spark compute settings")
            self.fabric_client.update_environment_spark_compute(workspace.id, environment.id, environment_spark_compute_settings)

        self.logger.info("publishing environment...")
        self.fabric_client.publish_environment(workspace.id, environment.id)
        return environment

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("PublishEnvironment: workspaceName is a required parameter.")
        
        if "environment" not in kwargs:
            if "displayName" not in kwargs:
                raise AutomationFrameworkValidationException("PublishEnvironment: displayName is a required parameter when environment is not provided.")
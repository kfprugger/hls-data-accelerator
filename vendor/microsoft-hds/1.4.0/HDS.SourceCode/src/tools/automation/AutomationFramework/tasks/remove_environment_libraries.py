import time
from models.workspace import Workspace
from models.environment import Environment
from .base_task import BaseTask
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class RemoveEnvironmentLibraries(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):
        workspace: Workspace = get_value('workspace', self.context, kwargs)
        environment: Environment = get_value('environment', self.context, kwargs)

        # Get the most recent environment
        environment = self.fabric_client.get_environment(workspace.id, environment.id)
        
        env_props = environment.properties
        cancelled_publish = False
        if "publishDetails" in env_props:
            publish_details = env_props["publishDetails"]
            if "state" in publish_details:
                publish_state = str(publish_details["state"]).lower()
                if publish_state == "running" or publish_state == "waiting":
                    self.fabric_client.cancel_environment_publish(workspace.id, environment.id)
                    cancelled_publish = True
        
        if cancelled_publish:
            while self.is_environment_busy(publish_state):
                self.logger.info(f"Environment is still busy, waiting to cancel. Current state: {publish_state}")
                time.sleep(5)
                environment = self.fabric_client.get_environment(workspace.id, environment.id)
                env_props = environment.properties
                publish_state = env_props["publishDetails"]["state"]
        else:
            self.logger.info("Environment is not busy, no need to cancel.")
        
        staging_libraries = self.fabric_client.get_environment_staged_libraries(workspace.id, environment.id)

        if "customLibraries" in staging_libraries:
            custom_libraries = staging_libraries["customLibraries"]
            if "wheelFiles" in custom_libraries:
                for wheel_file in custom_libraries["wheelFiles"]:
                    self.logger.info(f"Removing library from environment: {wheel_file}")
                    self.fabric_client.delete_environment_library(workspace.id, environment.id, wheel_file)
        else:
            self.logger.info("No custom wheel libraries to remove.")

    def is_environment_busy(self, publish_state: str):
        publish_state = publish_state.lower()
        return publish_state != "cancelled" and publish_state != "failed" and publish_state != "success"

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("RemoveEnvironmentLibraries: workspace is a required parameter.")
        
        if "environment" not in kwargs:
            raise AutomationFrameworkValidationException("RemoveEnvironmentLibraries: environment is a required parameter.")
import time
from .base_task import BaseTask
from models.workspace import Workspace
from models.environment import Environment
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class WaitForEnvironmentPublish(BaseTask):
    
    def __init__(self, fabric_client, context, logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        environment: Environment = get_value('environment', self.context, kwargs)
        
        publishing = True
        count = 0
        delay_in_seconds = 15
        while publishing:
            env = self.fabric_client.get_environment(workspace.id, environment.id)

            publishing_state = None
            env_properties = env.properties
            if "publishDetails" in env_properties:
                if "state" in env_properties["publishDetails"]:
                    publishing_state = str(env_properties["publishDetails"]["state"]).lower()
                    if publishing_state == "success":
                        publishing = False
                    elif publishing_state == "failed":
                        raise AutomationFrameworkValidationException(f"Environment publishing failed: {env_properties['publishDetails']}")
                    elif publishing_state == "cancelled":
                        raise AutomationFrameworkValidationException(f"Environment publishing cancelled: {env_properties['publishDetails']}")
            else:
                self.logger.info("env response did not include publish details")
            
            if publishing_state is not None:
                self.logger.info(f"[{count}] Polling again in {delay_in_seconds} seconds, publishing state: {publishing_state}")
            else:
                self.logger.info(f"[{count}] Polling again in {delay_in_seconds} seconds")

            count = count + 1
            time.sleep(delay_in_seconds)
        
        

    def onComplete(self, **kwargs):
        self.logger.info(f"Environment publishing complete.")

    def validate_args(self, **kwargs) -> bool:
        
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("WaitForEnvironmentPublish: workspaceName is a required parameter.")
    
        if "environment" not in kwargs:
            raise AutomationFrameworkValidationException("WaitForEnvironmentPublish: environment is a required parameter.")
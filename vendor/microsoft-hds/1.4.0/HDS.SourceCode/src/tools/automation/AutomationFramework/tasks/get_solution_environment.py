from .base_task import BaseTask
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException

from logging import Logger

class GetSolutionEnvironment(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        uniquePrefix = get_value("uniquePrefix", self.context, kwargs)
        environments = self.fabric_client.get_environments(workspace.id)
        env_dict = { e.displayName : e for e in environments}
        
        target_env = f"{uniquePrefix}_environment"
        if target_env in env_dict:
            return env_dict[target_env]
        else:
            raise AutomationFrameworkRuntimeException("Environment not found")        

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "uniquePrefix" not in kwargs:
            raise AutomationFrameworkValidationException("uniquePrefix is required")
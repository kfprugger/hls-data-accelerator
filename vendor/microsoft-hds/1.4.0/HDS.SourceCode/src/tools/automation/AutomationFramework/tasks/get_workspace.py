from .base_task import BaseTask
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException

from logging import Logger

class GetWorkspace(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace_id: Workspace = get_value('workspace_id', self.context, kwargs)
        workspace = self.fabric_client.get_workspace(workspace_id)
        self.logger.info(f"Fetched workspace: {workspace.displayName} with ID: {workspace.id}")

        return [
            workspace, 
            workspace.capacityId
        ]
        
    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "workspace_id" not in kwargs:
            raise AutomationFrameworkValidationException("workspace_id is required")
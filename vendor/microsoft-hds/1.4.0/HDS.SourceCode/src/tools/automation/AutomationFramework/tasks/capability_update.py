from .base_task import BaseTask
from models.lakehouse import Lakehouse
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class UpdateHdsCapabilities(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        capacityId: str = get_value('capacityId', self.context, kwargs)
        solutionArtifactId = get_value('solution_artifact_id', self.context, kwargs)

        self.fabric_client.update_capabilities(capacityId, workspace.id, solutionArtifactId)

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("workspace is required")
        
        if "capacityId" not in kwargs:
            raise AutomationFrameworkValidationException("capacityId")
    
        if "solution_artifact_id" not in kwargs:
            raise AutomationFrameworkValidationException("solution_artifact_id is required")
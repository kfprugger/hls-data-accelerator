from .base_task import BaseTask
from models.lakehouse import Lakehouse
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class DeployHdsCapabilities(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_lakehouse: Lakehouse = None

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        capacityId: str = get_value('capacityId', self.context, kwargs)
        solutionArtifactId = get_value('solution_artifact_id', self.context, kwargs)
        capabilities: str = get_value('capabilities', self.context, kwargs)
        uniquePrefix: str = get_value('uniquePrefix', self.context, kwargs)

        deploy_capabilities_request = {
            "capabilities": capabilities,
            "uniquePrefix": uniquePrefix
        }

        self.fabric_client.deploy_capability(
            capacity_id=capacityId,
            workspace_id=workspace.id,
            solution_id=solutionArtifactId,
            request=deploy_capabilities_request)

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "capabilities" not in kwargs:
            raise AutomationFrameworkValidationException("capabilities is required")
    
        if "uniquePrefix" not in kwargs:
            raise AutomationFrameworkValidationException("uniquePrefix is required")
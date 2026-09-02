import time
from typing import List
from models.get_capabilities_response import CapabilityResponse
from .base_task import BaseTask
from models.lakehouse import Lakehouse
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException
from logging import Logger

class PollCapabilityDeployment(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.hds_item: Lakehouse = None

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        capacityId: str = get_value('capacityId', self.context, kwargs)
        solutionArtifactId = get_value('solution_artifact_id', self.context, kwargs)

        self.logger.debug("Polling capability deployment")
        
        all_capabilities_deployed = False
        while all_capabilities_deployed != True:
            capabilities = self.fabric_client.get_installed_capabilities(capacityId, workspace.id, solutionArtifactId)
            
            if len(capabilities) == 0:
                self.logger.info("Deployed capability not registered yet, trying again...")
                time.sleep(5)
            else:
                all_capabilities_deployed = True
                failed_capabilities: List[CapabilityResponse] = []
                for capability in capabilities:
                    if capability.provisionState == "Failed":
                        failed_capabilities.append(capability)
                    elif capability.provisionState != "Active" or not self.all_artifacts_active(capability):
                        all_capabilities_deployed = False
                        break
                
                if len(failed_capabilities) > 0:
                    failed_capabilities_str = ", ".join([f.name for f in failed_capabilities])
                    raise AutomationFrameworkRuntimeException(f"Capabilities failed to deploy: {failed_capabilities_str}")

            if all_capabilities_deployed == False:
                self.logger.info("Polling status again in 15 seconds")
                time.sleep(15)

    def all_artifacts_active(self, capability: CapabilityResponse):
        
        if len(capability.deployedArtifacts) == 0:
            return False

        for deployedArtifact in capability.deployedArtifacts:
            if deployedArtifact.provisionState != "Active":
                return False

        return True

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:

        if "capacityId" not in kwargs:
            raise AutomationFrameworkValidationException("capacityId is required")
        
        if "solution_artifact_id" not in kwargs:
            raise AutomationFrameworkValidationException("solution_artifact_id is required")
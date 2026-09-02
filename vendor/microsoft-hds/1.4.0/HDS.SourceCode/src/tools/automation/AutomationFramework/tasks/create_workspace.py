from datetime import datetime

from .base_task import BaseTask
from models.create_workspace_request import CreateWorkspaceRequest
from models.workspace import Workspace
from utils.context_utils import get_value, update_context
from utils.framework_state_manager import FrameworkStateManager
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException
from logging import Logger

class CreateWorkspace(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_workspace: Workspace = None

    def execute(self, **kwargs):
        display_name = get_value('displayName', self.context, kwargs)
        capacityId = get_value('capacityId', self.context, kwargs)
        resourceGroupName = get_value('resourceGroupName', self.context, kwargs)
        subscriptionId = get_value('subscriptionId', self.context, kwargs)
        description = get_value('description', self.context, kwargs)
        add_datetime_postfix = get_value('add_datetime_postfix', self.context, kwargs, True)

        if not display_name:
            raise AutomationFrameworkRuntimeException("Display name not provided.")

        capacityId = self.prepare_capacity_id(capacityId, subscriptionId, resourceGroupName)
        if capacityId is None:
            raise AutomationFrameworkRuntimeException("No trial capacity found.")
        
        if add_datetime_postfix:
            posfix = datetime.now().strftime('%m%d_%H%M_%S')
            display_name = f"{display_name}_{posfix}"
        
        create_workspace_request = CreateWorkspaceRequest(display_name, capacityId, description)
        self.new_workspace = self.fabric_client.create_workspace(create_workspace_request)
        
        if self.new_workspace is None:
            raise AutomationFrameworkRuntimeException("Error creating workspace, make sure it is configured to have a unique name.")
        
        return [self.new_workspace, capacityId]

    def prepare_capacity_id(self, capacityId, subscriptionId, resourceGroupName):
        if capacityId is None:
            self.logger.info("Capacity Id not found, using default trial capacity")
            capacities = self.fabric_client.get_capacities()
            for capacity in capacities:
                if "trial" in capacity.displayName.lower():
                    capacityId = capacity.id
                    break
        else:
            self.logger.info(f"Using provided capacity: {capacityId}")

            capacity = self.fabric_client.get_capacity(capacityId)
            if capacity is None:
                raise AutomationFrameworkRuntimeException(f"Capacity with id {capacityId} not found.")
            capacityStatus = capacity.state
            capacityName = capacity.displayName
            if capacityStatus != "Active":
                self.logger.info(f"Resuming the capacity {capacityName}")
                self.fabric_client.resume_capacity(capacityName, subscriptionId, resourceGroupName)
                self.context.update(capacityResumed=True)
        return capacityId

    def onComplete(self, **kwargs):
        framework_state_manager: FrameworkStateManager = self.context["framework_state_manager"]
        if self.task_id in framework_state_manager.tasks:

            workspace_url = f"https://{self.fabric_client.env}.powerbi.com/groups/{self.new_workspace.id}/list?experience=power-bi"
            
            framework_state_manager.update_task_description(
                self.pipeline_id,
                self.task_id,
                f"Create workspace {self.new_workspace.displayName}: {workspace_url}",
            )
                        
        self.logger.info(f"Successfully created Workspace: {self.new_workspace.displayName}")

    def validate_args(self, **kwargs) -> bool:
        if "displayName" not in kwargs:
            raise AutomationFrameworkValidationException("displayName is required")
        
        if " " in kwargs["displayName"]:
            raise AutomationFrameworkValidationException("displayName should not contain spaces, use underscores instread")
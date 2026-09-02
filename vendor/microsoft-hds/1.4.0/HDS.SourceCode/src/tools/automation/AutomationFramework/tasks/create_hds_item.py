from .base_task import BaseTask
from models.lakehouse import Lakehouse
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException

class CreateHdsItem(BaseTask):
    
    def __init__(self, fabric_client, context, logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.hds_item: Lakehouse = None

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        solution_display_name: str = get_value('solution_display_name', self.context, kwargs)

        hds_item =  self.fabric_client.create_healthcare_data_solution(workspace.id, solution_display_name)
        return hds_item.id

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "solution_display_name" not in kwargs:
            raise AutomationFrameworkValidationException("solution_display_name is required")
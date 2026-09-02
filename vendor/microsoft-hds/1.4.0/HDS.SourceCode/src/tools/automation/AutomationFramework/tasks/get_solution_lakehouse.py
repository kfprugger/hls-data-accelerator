from .base_task import BaseTask
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException

from logging import Logger

class GetSolutionLakehouse(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        uniquePrefix = get_value("uniquePrefix", self.context, kwargs)
        lakehouse_name = get_value("lakehouse_name", self.context, kwargs)
        
        lakehouses = self.fabric_client.get_lakehouses(workspace.id)
        lh_dict = { e.displayName : e for e in lakehouses}
        
        target_lakehouse = f"{uniquePrefix}_msft_{lakehouse_name}"
        if target_lakehouse in lh_dict:
            return lh_dict[target_lakehouse]
        elif lakehouse_name in lh_dict:
            return lh_dict[lakehouse_name]
        else:
            raise AutomationFrameworkRuntimeException("Lakehouse not found")        

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "lakehouse_name" not in kwargs:
            raise AutomationFrameworkValidationException("lakehouse_name is required")
        
        if "uniquePrefix" not in kwargs:
            raise AutomationFrameworkValidationException("uniquePrefix is required")
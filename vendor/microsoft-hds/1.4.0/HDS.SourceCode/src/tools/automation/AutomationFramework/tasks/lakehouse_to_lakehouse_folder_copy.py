from .base_task import BaseTask
from models.workspace import Workspace
from models.lakehouse import Lakehouse
from utils.context_utils import get_value
from utils.copy_job_utils import create_lakehouse_copy_job
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException
from logging import Logger

class LakehouseToLakehouseFolderCopy(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_lakehouse: Lakehouse = None

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        display_name: str = get_value('displayName', self.context, kwargs)
        source_lakehouse_name: str = get_value('source_lakehouse', self.context, kwargs)
        target_lakehouse_name: Lakehouse = get_value('target_lakehouse', self.context, kwargs)
        source_lakehouse_subpath: str = get_value('source_lakehouse_subpath', self.context, kwargs)
        target__lakehouse_directory: str = get_value('target_lakehouse_directory', self.context, kwargs)
        token_provider = get_value('token_provider', self.context, kwargs)

        lakehouses = {lh.displayName : lh for lh in self.fabric_client.get_lakehouses(workspace.id)}
        
        if source_lakehouse_name not in lakehouses:
            raise AutomationFrameworkRuntimeException("")
        
        if target_lakehouse_name not in lakehouses:
            raise AutomationFrameworkRuntimeException("")
        
        source_lakehouse: Lakehouse = lakehouses[source_lakehouse_name]
        target_lakehouse: Lakehouse = lakehouses[target_lakehouse_name]
        
        create_lakehouse_copy_job(
            workspace.id,
            display_name,
            source_lakehouse.id,
            source_lakehouse_subpath,
            target_lakehouse.id,
            target__lakehouse_directory,
            self.logger,
            token_provider,
            self.fabric_client.env
        )
        
    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "displayName" not in kwargs:
            raise AutomationFrameworkValidationException("displayName is required")
        
        if "source_lakehouse" not in kwargs:
            raise AutomationFrameworkValidationException("source_lakehouse is required")
        
        if "target_lakehouse" not in kwargs:
            raise AutomationFrameworkValidationException("target_lakehouse is required")
        
        if "source_lakehouse_subpath" not in kwargs:
            raise AutomationFrameworkValidationException("source_lakehouse_subpath is required")
        
        if "target_lakehouse_directory" not in kwargs:
            raise AutomationFrameworkValidationException("target_lakehouse_directory is required")
        
        

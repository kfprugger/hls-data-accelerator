from .base_task import BaseTask
from models.create_lakehouse_request import CreateLakehouseRequest
from models.lakehouse import Lakehouse
from models.workspace import Workspace
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from utils.upload_files import create_directory
from utils.context_utils import get_value, update_context

class CreateLakehouse(BaseTask):
    
    def __init__(self, fabric_client, context, logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_lakehouse: Lakehouse = None

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        display_name: str = get_value('displayName', self.context, kwargs)
        description: str = get_value('description', self.context, kwargs)
        subfolders: str = get_value('subfolders', self.context, kwargs)

        if not display_name:
            raise ValueError("display_name is required")

        create_lakehouse_request = CreateLakehouseRequest(display_name, description)
        self.new_lakehouse = self.fabric_client.create_lakehouse(workspace.id, create_lakehouse_request)
        
        if subfolders:
            for subfolder in subfolders:
                self.logger.info(f"Creating subfolder: {subfolder}")
                create_directory(workspace.id, self.new_lakehouse.id, subfolder)

        return self.new_lakehouse
    
    def onComplete(self, **kwargs):
        self.logger.info(f"Successfully created Lakehouse: {self.new_lakehouse.displayName}")
        update_context(self.context, self.new_lakehouse.displayName + "_lakehouse", self.new_lakehouse)

    def validate_args(self, **kwargs) -> bool:
        
        if "displayName" not in kwargs:
            raise AutomationFrameworkValidationException("displayName is required")
from .base_task import BaseTask
from models.workspace import Workspace
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class PollJobCompletion(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        item_id = get_value('item_id', self.context, kwargs)
        job_id = get_value('job_id', self.context, kwargs)
        
        self.fabric_client.poll_job_status(workspace.id, item_id, job_id, interval_in_secords=10)

    def onComplete(self, **kwargs):
        pass
    
    def validate_args(self, **kwargs) -> bool:
        
        if "item_id" not in kwargs:
            raise AutomationFrameworkValidationException("item_id is required")
        
        if "job_id" not in kwargs:
            raise AutomationFrameworkValidationException("job_id is required")
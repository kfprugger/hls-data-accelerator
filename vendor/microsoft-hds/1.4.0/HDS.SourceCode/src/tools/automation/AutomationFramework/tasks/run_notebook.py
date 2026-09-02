import json
from .base_task import BaseTask
from models.workspace import Workspace
from models.environment import Environment
from models.notebook import Notebook
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException

class RunNotebook(BaseTask):
    
    def __init__(self, fabric_client, context, logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.data_pipeline = None
        self.data_pipeline_job_id = None

    def execute(self, **kwargs):
        workspace: Workspace = get_value('workspace', self.context, kwargs)
        environment: Environment = get_value('environment', self.context, kwargs)
        notebook_id: str = get_value('notebook_id', self.context, kwargs)
        default_lakehouse: str = get_value('default_lakehouse', self.context, kwargs)

        job_id = self.fabric_client.run_notebook(
            workspace.id,
            notebook_id,
            environment,
            default_lakehouse,
            paramerters={},
            spark_config={})
        
        return job_id

    def onComplete(self, **kwargs):
        pass
    
    def validate_args(self, **kwargs) -> bool:
        
        self.logger.debug(json.dumps(kwargs, indent=2))
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("RunNotebook: workspace is required")
        
        if "environment" not in kwargs:
            raise AutomationFrameworkValidationException("RunNotebook: environment is required")
        
        if "notebook_id" not in kwargs:
            raise AutomationFrameworkValidationException("RunNotebook: notebook_id is required")

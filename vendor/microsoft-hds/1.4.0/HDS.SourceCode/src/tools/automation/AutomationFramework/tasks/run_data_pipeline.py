import json
from .base_task import BaseTask
from models.workspace import Workspace
from models.data_pipeline import DataPipeline
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException

class RunDataPipeline(BaseTask):
    
    def __init__(self, fabric_client, context, logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.data_pipeline = None
        self.data_pipeline_job_id = None

    def execute(self, **kwargs):
        workspace: Workspace = get_value('workspace', self.context, kwargs)
        dataPipelineName = get_value("dataPipelineName", self.context, kwargs)
        pipelineParameters = get_value("pipelineParameters", self.context, kwargs, {})
        
        pipeline_dict = {}
        data_pipelines = self.fabric_client.get_data_pipelines(workspace.id)

        for pipeline in data_pipelines:
            pipeline_dict[pipeline.displayName] = pipeline

        if dataPipelineName in pipeline_dict:
            self.data_pipeline: DataPipeline = pipeline_dict[dataPipelineName]

            self.logger.info(f"Running {self.data_pipeline.displayName} data pipeline...")
            self.data_pipeline_job_id = self.fabric_client.run_data_pipeline(
                workspace.id,
                self.data_pipeline.id,
                pipelineParameters      
            )
            
            
            return [self.data_pipeline.id, self.data_pipeline_job_id]

    def onComplete(self, **kwargs):
        self.logger.info(f"Pipeline {self.data_pipeline.displayName} running with job id: {self.data_pipeline_job_id}")

    def validate_args(self, **kwargs) -> bool:
        
        self.logger.debug(json.dumps(kwargs, indent=2))
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("workspace is required")
        
        if "dataPipelineName" not in kwargs:
            raise AutomationFrameworkValidationException("dataPipelineName is required")

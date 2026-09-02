import base64
import json
import os
from typing import Any

from models.create_data_pipeline_request import CreateDataPipelineRequest
from models.data_pipeline_definition import DataPipelineDefinition

from .base_task import BaseTask
from models.workspace import Workspace
from utils.context_utils import get_value, get_value_from_context
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException

class CreateDataPipeline(BaseTask):
    
    def __init__(self, fabric_client, context, logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        data_pipeline_path = get_value('data_pipeline_path', self.context, kwargs)
        data_pipeline_configuration = get_value('data_pipeline_configuration', self.context, kwargs)
        
        self.logger.info("Setting up data pipeline...")    
        existing_notebooks = self.fabric_client.get_notebooks(workspace.id)

        existing_notebooks_dict = {}
        for existing_notebook in existing_notebooks:
            existing_notebooks_dict[existing_notebook.displayName] = existing_notebook.id
        
        notebook_activity_configs = {}
        for activity in data_pipeline_configuration["activities"]:
            if activity["notebook_name"] in existing_notebooks_dict:
                notebook_activity_configs[activity["activity_name"]] = existing_notebooks_dict[activity["notebook_name"]]
        
        create_data_pipeline_request = CreateDataPipelineRequest(
            displayName=data_pipeline_configuration["pipeline_name"],
            description=data_pipeline_configuration["pipeline_description"]
        )

        data_pipeline = self.fabric_client.create_data_pipeline(workspace.id, create_data_pipeline_request)
        
        formatted_pipeline_payload = self.get_formated_data_pipeline_payload(
            data_pipeline_definition_path= data_pipeline_path,
            notebook_activity_configs=notebook_activity_configs,
            workspace_id=workspace.id,
            pipeline_configuration=data_pipeline_configuration
        )
        
        definition_part = {
            "path": "test-pipeline.json",
            "payload": base64.b64encode(json.dumps(formatted_pipeline_payload).encode('utf-8')).decode('utf-8'),
            "payloadType": "InlineBase64"
        }
        
        pipeline_definition = DataPipelineDefinition(data={ "parts": [definition_part]})

        self.fabric_client.update_data_pipeline_definition(workspace.id, data_pipeline.id, pipeline_definition)

    def onComplete(self, **kwargs):
        self.logger.info(f"Successfully created data pipeline")

    def validate_args(self, **kwargs) -> bool:

        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("CreateDataPipeline: workspaceName is a required parameter.")

        if "data_pipeline_path" not in kwargs:
            raise AutomationFrameworkValidationException("CreateDataPipeline: data_pipeline_path is a required parameter.")
        
        if "data_pipeline_configuration" not in kwargs:
            raise AutomationFrameworkValidationException("CreateDataPipeline: data_pipeline_configuration is a required parameter.")
    
    def get_formated_data_pipeline_payload(self, data_pipeline_definition_path: str, notebook_activity_configs: Any, workspace_id: str, pipeline_configuration: Any):
        
        self.logger.debug(data_pipeline_definition_path)
        root_dir = os.path.dirname(__file__).split("src")[0]
        with open(root_dir + data_pipeline_definition_path, "r", encoding="utf-8") as f:
            data_pipeline_payload = json.load(f)

        if "properties" in data_pipeline_payload:
            properties = data_pipeline_payload["properties"]
            if "activities" in properties:
                activities = properties["activities"]
                for activity in activities:
                    if "typeProperties" in activity:
                        typeProperties = activity["typeProperties"]
                        if "notebookId" in typeProperties and activity["name"].lower() in notebook_activity_configs:
                            typeProperties["notebookId"] = notebook_activity_configs[activity["name"]]
                        if "workspaceId" in typeProperties:
                            typeProperties["workspaceId"] = workspace_id
                        if "parameters" in typeProperties and "parameters" in pipeline_configuration and pipeline_configuration["parameters"] is not {}:
                            typeProperties["parameters"] = pipeline_configuration["parameters"]
        
        return data_pipeline_payload
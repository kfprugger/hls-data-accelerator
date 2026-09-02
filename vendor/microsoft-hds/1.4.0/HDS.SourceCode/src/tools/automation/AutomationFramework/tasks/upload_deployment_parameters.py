
import json
import os
from typing import Dict
from .base_task import BaseTask
from models.lakehouse import Lakehouse
from models.workspace import Workspace
from utils.context_utils import get_value
from utils.upload_files import create_file_with_content
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class UploadDeploymentParameters(BaseTask):
    
    def __init__(self, fabric_client, context, logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_lakehouse: Lakehouse = None

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs, None)        
        template_path: str = get_value('template_path', self.context, kwargs)
        target_lakehouse_name: str = get_value('target_lakehouse_name', self.context, kwargs, "Administration")
        target_lakehouse_path: str = get_value('target_lakehouse_path', self.context, kwargs, "Files/system-configuration")
        
        root_dir = os.path.dirname(__file__).split("src")[0]
        with open(root_dir + template_path, "+r") as f:
            deployment_parameters_template = json.load(f)
        
        formatted_deployment_parametters = {}
        
        lakehouses = self.fabric_client.get_lakehouses(workspace.id)
        notebooks = self.fabric_client.get_notebooks(workspace.id)
        
        lakehouses_dict: dict[str, Lakehouse] = {}
        for lh in lakehouses:
            lakehouses_dict[lh.displayName.lower()] = lh
            
        lakehouse_patterns: Dict[str, Lakehouse] = {"{"+ lh.displayName.split("_")[0].lower() + "_lakehouse_id}": lh for lh in lakehouses}
        
        notebooks_dict: dict[str, Lakehouse] = {}
        for nb in notebooks:
            notebooks_dict[nb.displayName.lower()] = nb

        # update globals
        if "activitiesGlobalParameters" in deployment_parameters_template:
            for key, value in deployment_parameters_template["activitiesGlobalParameters"].items():
                
                formatted_value = str(value)
                for lakehouse_pattern in lakehouse_patterns.keys():
                    if lakehouse_pattern in formatted_value:
                        formatted_value = formatted_value.replace(lakehouse_pattern, lakehouse_patterns[lakehouse_pattern].id)

                if "workspace_id" in formatted_value:
                        formatted_value = formatted_value.replace("{workspace_id}", workspace.id)

                deployment_parameters_template["activitiesGlobalParameters"][key] = formatted_value

        formatted_deployment_parametters["activitiesGlobalParameters"] = deployment_parameters_template["activitiesGlobalParameters"]
        
        # update activities
        activities = {}
        
        self.logger.debug(list(deployment_parameters_template["activities"]))
        
        if "activities" in deployment_parameters_template:
            for activity_config in deployment_parameters_template["activities"]:
                if "name" in activity_config and str(activity_config["name"]).lower() in notebooks_dict:
                    self.logger.debug(activity_config["name"])
                    notebook = notebooks_dict[str(activity_config["name"]).lower()]
                    if "parameters" in activity_config:
                        for key, value in activity_config["parameters"].items():
                            
                            formatted_value = str(value)
                            for lakehouse_pattern in lakehouse_patterns.keys():
                                if lakehouse_pattern in formatted_value:
                                    if lakehouse_pattern.lower() == "{config_lakehouse_id}":
                                        formatted_value = formatted_value.replace(lakehouse_pattern, lakehouse_patterns[lakehouse_pattern].id + "/Files")
                                    else:
                                        formatted_value = formatted_value.replace(lakehouse_pattern, lakehouse_patterns[lakehouse_pattern].id)

                            if "workspace_id" in formatted_value:
                                formatted_value = formatted_value.replace("{workspace_id}", workspace.id)
                            
                            activity_config["parameters"][key] = formatted_value
                                
                        activities[notebook.id] = activity_config
        
        formatted_deployment_parametters["activities"] = activities
        
        self.logger.debug(json.dumps(formatted_deployment_parametters, indent = 2))
        
        if target_lakehouse_name.lower() in lakehouses_dict:
            lakehouse = lakehouses_dict[target_lakehouse_name.lower()]
            create_file_with_content(workspace.id, lakehouse.id, target_lakehouse_path, formatted_deployment_parametters)
    
    def onComplete(self, **kwargs):
        self.logger.info("Successfully updated and uploaded deployment parameters")

    def validate_args(self, **kwargs) -> bool:
        
        if "template_path" not in kwargs:
            raise AutomationFrameworkValidationException("UploadDeploymentParameters: template_path is a required parameter.")
    
        if "target_lakehouse_name" not in kwargs:
            raise AutomationFrameworkValidationException("UploadDeploymentParameters: target_lakehouse_name is a required parameter.")
        
        if "target_lakehouse_path" not in kwargs:
            raise AutomationFrameworkValidationException("UploadDeploymentParameters: target_lakehouse_path is a required parameter.")
        
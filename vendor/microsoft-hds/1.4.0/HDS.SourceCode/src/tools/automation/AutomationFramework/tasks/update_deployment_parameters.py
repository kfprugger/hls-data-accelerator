import json
from .base_task import BaseTask
from models.workspace import Workspace
from models.lakehouse import Lakehouse
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger
from utils.upload_files import get_files_client

class UpdateDeploymentParameters(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        lakehouse: Lakehouse = get_value('lakehouse', self.context, kwargs)
        parameter_updates = get_value('parameter_updates', self.context, kwargs)
        
        fs_client = get_files_client(workspace.id, lakehouse.id, self.fabric_client.env)
        
        deployment_parameters_path = "/system-configurations/deploymentParametersConfiguration.json"
        
        file_client = fs_client.get_file_client(deployment_parameters_path)

        deployment_parameters_content = json.loads(file_client.download_file().readall())
        
        for parameter_update in parameter_updates:
            activities = deployment_parameters_content["activities"]
            for activity in activities.values():
                if activity["name"] == parameter_update["activity_name"]:
                    parameters = activity["parameters"]
                    for pk in parameters.keys():
                        if pk == parameter_update["parameter_name"]:
                            parameters[pk] = parameter_update["new_value"]
        
        if file_client.exists():
            file_client.delete_file()

        data = json.dumps(deployment_parameters_content)
        file_client = fs_client.create_file(deployment_parameters_path, timeout=300)
        file_client.append_data(data=data, offset=0, length=len(data))
        file_client.flush_data(len(data))

    def onComplete(self, **kwargs):
        pass
    
    def validate_args(self, **kwargs) -> bool:
        
        if "lakehouse" not in kwargs:
            raise AutomationFrameworkValidationException("lakehouse is required")
        
        if "parameter_updates" not in kwargs:
            raise AutomationFrameworkValidationException("parameter_updates is required")
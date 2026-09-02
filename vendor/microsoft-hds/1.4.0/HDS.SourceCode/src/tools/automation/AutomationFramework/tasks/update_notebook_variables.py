import base64
import json
from models.workspace import Workspace
from models.create_notebook_request import CreateNotebookRequest
from clients.fabric_client import FabricClient
from .base_task import BaseTask
from utils.context_utils import get_value
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
import re
from logging import Logger
import nbformat

class UpdateNotebookVariables(BaseTask):
    """
    This task is responsible for updating the parameters of a deployed notebook in a given workspace.
    """
    
    def __init__(self, fabric_client: FabricClient, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):
        workspace: Workspace = get_value('workspace', self.context, kwargs, None)
        notebookName: str = get_value('notebookName', self.context, kwargs)
        notebook_parameters = get_value('notebook_variables', self.context, kwargs, {})
        
        notebooks = self.fabric_client.get_notebooks(workspace.id)

        target_notebook = None
        for notebook in notebooks:
            if notebookName.lower() in notebook.displayName.lower():
                target_notebook = notebook

        if target_notebook is None:
            self.logger.info(f"Notebook {notebookName} not found.")
            return None
        
        target_notebook_definition = self.fabric_client.get_notebook_definition(workspace.id, target_notebook.id)
        definition_payload = target_notebook_definition['definition']['parts'][0]['payload']
        decoded_payload = base64.b64decode(definition_payload)
        
        try:
            nb_json = json.loads(decoded_payload)
        except json.JSONDecodeError as e:
            self.logger.error(f"Error updating notebook {notebookName}, failed to decode JSON payload: {e}")
            return None
        
        # Update notebook parameters with context values
        for key, value in notebook_parameters.items():
            if value[1:] in self.context:
                notebook_parameters[key] = self.context[key[1:]]

        for cell_index, cell in enumerate(nb_json["cells"]):
            if "cell_type" in cell and str(cell["cell_type"]).lower() == "code":
                if "source" in cell:
                    updated_source = self.replace_variables_in_cell(cell["source"], notebook_parameters)
                    nb_json["cells"][cell_index]["source"] = updated_source

        encoded_payload = base64.b64encode(json.dumps(nb_json).encode('utf-8')).decode('utf-8')

        try:
            update_notebook_request = {
                "definition": {
                    "format": "ipynb",
                    "parts": [
                        {
                            "path": notebookName,
                            "payload": encoded_payload,
                            "payloadType": "InlineBase64"
                        }
                    ]
                }
            }

            updated_notebook = self.fabric_client.update_notebook_definition(workspace.id, target_notebook.id, update_notebook_request)

            if updated_notebook is not None:
                self.logger.info(f"Successfully uploaded notebook {notebookName}")
                return target_notebook.id
            else:
                self.logger.info(f"Error uploading notebook: {notebookName}")
                return None

        except Exception as ex:
            self.logger.error(f"Error uploading notebook {notebookName}: {ex}")

    def replace_variable(self, line, variables_dict):
        for var, value in variables_dict.items():
            # Create a regex pattern to match the variable assignment
            pattern = rf'(\b{var}\b\s*=\s*)(["\']?.*?["\']?)\s*(#.*)?$'
            match = re.match(pattern, line)
            if match:
                # Replace the variable value
                if isinstance(value, str):
                    new_value = f'"{value}"'
                else:
                    new_value = str(value)
                line = f'{match.group(1)}{new_value} {match.group(3) or ""}\n'
                print(line)
        return line
    
    def replace_variables_in_cell(self, cell_source, variables_dict):
        """
        Parses the cell block in a Jupyter notebook and replaces variables based on an input dictionary.
        
        Args:
            cell_source (list): The source code of the cell as a list of strings.
            variables_dict (dict): A dictionary containing variable names and their replacement values.
            
        Returns:
            list: The modified source code of the cell as a list of strings.
        """
        modified_cell_source = [self.replace_variable(line, variables_dict) for line in cell_source]
        
        return modified_cell_source

    def onComplete(self, **kwargs):
        pass

    def validate_args(self, **kwargs) -> bool:
        
        if "notebookName" not in kwargs:
            raise AutomationFrameworkValidationException("UpdateNotebookParameters: notebookName is a required parameter.")
        
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("UpdateNotebookParameters: workspaceName is a required parameter.")
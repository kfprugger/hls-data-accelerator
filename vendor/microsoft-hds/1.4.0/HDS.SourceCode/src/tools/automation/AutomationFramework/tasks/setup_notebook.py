import ast
import base64
import json
import os
from models.workspace import Workspace
from models.environment import Environment
from models.create_notebook_request import CreateNotebookRequest
from clients.fabric_client import FabricClient
from .base_task import BaseTask
from utils.context_utils import get_value, update_context
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
import nbformat
from logging import Logger

class SetupNotebook(BaseTask):
    
    def __init__(self, fabric_client: FabricClient, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)
        self.new_notebook = None

    def execute(self, **kwargs):
        workspace: Workspace = get_value('workspace', self.context, kwargs, None)
        environment: Environment = get_value('environment', self.context, kwargs, None)
        notebookName: str = get_value('notebookName', self.context, kwargs)
        lakehouse_config: str = get_value('lakehouseConfig', self.context, kwargs, {})
        notebook_parameters = get_value('notebook_parameters', self.context, kwargs, {})
        notebooks_path: str = get_value('notebooks_path', self.context, kwargs)
        
        lakehouses = self.fabric_client.get_lakehouses(workspace.id)
        
        self.logger.info("Setting up notebooks...")

        if notebooks_path:
            if str(notebookName).endswith("ipynb") == False:
                notebookName = notebookName + ".ipynb"
            
            root_dir = os.path.dirname(__file__).split("src")[0]
            with open(root_dir + notebooks_path + "/" + notebookName, "r", encoding="utf-8") as f:
                notebook_content = nbformat.read(f, as_version=4)
                nb_json = json.loads(nbformat.writes(notebook_content))
                
                parameter_cell = None
                updated_cells = []
                for cell in nb_json["cells"]:
                    if "metadata" in cell and "tags" in cell["metadata"] and "parameters" in cell["metadata"]["tags"] and parameter_cell is None:
                        parameter_cell = cell

                    if "cell_type" in cell and str(cell["cell_type"]).lower() == "code":
                        if "source" in cell:
                            inline_installation_found = False
                            for source in cell["source"]:
                                if "%pip install" in source:
                                    inline_installation_found = True
                            
                            if inline_installation_found == False:
                                updated_cells.append(cell)
                        else:
                            updated_cells.append(cell)
                    else:
                        updated_cells.append(cell)
                
                nb_json["cells"] = updated_cells

                updated_source_lines = []
                if parameter_cell is not None:
                    for idx, line in enumerate(parameter_cell["source"]):
                        formatted_line = str(line).replace("\n", "").replace(" ", "").strip()
                        if "=" in formatted_line:
                            default_notebook_parameters = {}
                            parameter_name, parameter_value = formatted_line.split("=")
                            default_notebook_parameters[parameter_name] = parameter_value
                            
                            resolved_value = parameter_value
                            if parameter_name in self.context:
                                resolved_value = self.context[parameter_name]
                            
                            if parameter_name in notebook_parameters:

                                resolved_value = notebook_parameters[parameter_name]
                                if isinstance(resolved_value, str) and resolved_value.replace("$", "") in self.context:
                                    resolved_value = self.context[resolved_value.replace("$", "")]
                            
                            if isinstance(resolved_value, str) and resolved_value.replace("%%", "") == "workspace_id":
                                resolved_value = workspace.id
                            
                            if isinstance(resolved_value, str) and resolved_value.replace("%%", "") == "workspace_name":
                                resolved_value = workspace.displayName

                            if parameter_name.replace(" ", "").lower() == "is_config_in_workload":
                                resolved_value = "False"
                                self.logger.debug("setting config in workload to false")
                            
                            if "%%" in resolved_value and "_id" in resolved_value:
                                context_reference = resolved_value.replace("%%", "").split("_id")[0]
                                if context_reference in self.context:
                                    resolved_value = self.context[context_reference].id
                            
                            elif "%%" in resolved_value and "lakehouse_id" in resolved_value:
                                for lakehouse in lakehouses:
                                    if lakehouse.displayName.lower() == resolved_value.replace("%%", "").split("_lakehouse_id")[0].lower():
                                        resolved_value = lakehouse.id
                                        break
                            
                            string_eval = None
                            
                            try:
                                string_eval = ast.literal_eval(resolved_value)        
                            except:
                                pass
        
                            value_as_dict = self.try_parse_dict(resolved_value)
                            if resolved_value == "True" or resolved_value == "False":
                                updated_source_lines.append(f"{parameter_name} = {resolved_value}\n")
                            
                            elif isinstance(string_eval, list):
                                updated_source_lines.append(f"{parameter_name} = {string_eval}\n")
                            
                            elif value_as_dict is not None:
                                updated_source_lines.append(f"{parameter_name} = {value_as_dict}\n")
                                
                            elif resolved_value and isinstance(resolved_value, list):
                                updated_source_lines.append(f"{parameter_name} = {resolved_value}\n")
                            
                            elif resolved_value and isinstance(resolved_value, dict):
                                updated_source_lines.append(f"{parameter_name} = {resolved_value}\n")
                            
                            elif isinstance(resolved_value, str) and resolved_value.startswith("\"") and resolved_value.endswith("\""):
                                updated_source_lines.append(f"{parameter_name} = {resolved_value}\n")
                            else:
                                updated_source_lines.append(f"{parameter_name} = \"{resolved_value}\"\n")
                        else:
                            updated_source_lines.append(line)
                
                    parameter_cell["source"] = updated_source_lines
                
                known_lakehouse_ids = []
                default_lakehouse_id = ""
                default_lakehouse_name = ""
                for lakehouse in lakehouses:
                    
                    if lakehouse.displayName.lower() == str(lakehouse_config["default_lakehouse_name"]).lower():
                        default_lakehouse_id = lakehouse.id
                        default_lakehouse_name = lakehouse.displayName
                    
                    for lakehouse_name in lakehouse_config["known_lakehouses"]:
                        if lakehouse_name == lakehouse.displayName: 
                            known_lakehouse_ids.append(lakehouse.id)

                lakehouse_metadata = {
                    "default_lakehouse": default_lakehouse_id,
                    "default_lakehouse_name": default_lakehouse_name,
                    "default_lakehouse_workspace_id": workspace.id,
                    "known_lakehouses": known_lakehouse_ids
                }
                
                if "dependencies" not in nb_json['metadata']:
                    nb_json['metadata']['dependencies'] = {}
                nb_json['metadata']['dependencies']['lakehouse'] = lakehouse_metadata
                
                default_environment_metadata = {
                    "workspaceId": workspace.id,
                }

                if environment:
                    default_environment_metadata["environmentId"] = environment.id

                nb_json["metadata"]["dependencies"]["environment"] = default_environment_metadata
                encoded_payload = base64.b64encode(json.dumps(nb_json).encode('utf-8')).decode('utf-8')

                try:
                    request_body = {
                        "displayName": notebookName.split(".")[0],
                        "description": "",
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
                    
                    create_notebook_request = CreateNotebookRequest(request_body)
                    self.new_notebook = self.fabric_client.create_notebook(workspace.id, create_notebook_request)

                    if self.new_notebook is not None:
                        self.logger.info(f"Successfully uploaded notebook {notebookName}")
                        return self.new_notebook.id
                    else:
                        self.logger.info(f"Error uploading notebook: {notebookName}")
                        return None

                except Exception as ex:
                    self.logger.error(f"Error uploading notebook {notebookName}: {ex}")

    def try_parse_dict(self, parameter_value):
        try:
            # Attempt to parse the string as JSON
            parsed_value = json.loads(parameter_value)
            # Check if the parsed value is a dictionary
            if isinstance(parsed_value, dict):
                return parsed_value
            else:
                return None
        except Exception:
            # If parsing fails, return the original string
            return None

    def onComplete(self, **kwargs):
        self.logger.info(f"Successfully created notebooks")
        update_context(self.context, self.new_notebook.displayName, self.new_notebook)

    def validate_args(self, **kwargs) -> bool:
        
        if "notebookName" not in kwargs:
            raise AutomationFrameworkValidationException("SetupNotebook: notebookName is a required parameter.")
        
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("SetupNotebook: workspaceName is a required parameter.")
import json
from typing import List, Union

import requests

from .client_utils import handle_list_response, handle_response
from models.create_notebook_request import CreateNotebookRequest
from models.notebook import Notebook
from models.notebook_definition import NotebookDefinition
from utils.token_provider import TokenProvider
from logging import Logger

class NotebookClient:

    def __init__(self, token_provder: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provder
        self.logger = logger
        self.endpoint_pattern = f"https://{env}api.fabric.microsoft.com/v1/workspaces/{{}}/notebooks"

    def get_notebook(self, workspaceId: str, notebookId: str) -> Union[Notebook, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{notebookId}"
        response = requests.get(url, headers=self.get_headers())
        return handle_response(response, Notebook)

    def get_notebook_definition(self, workspaceId: str, notebookId: str) -> requests.Response:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{notebookId}/getDefinition?format=ipynb"
        response = requests.post(url, headers=self.get_headers())

        if response.status_code == 202:
            return response.headers["Location"]
        else:
            return handle_response(response, NotebookDefinition)
    
    def update_notebook_definition(self,workspaceId: str, notebookId: str, updated_notebook_definiton: NotebookDefinition) -> Union[NotebookDefinition, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{notebookId}/updateDefinition"
        response = requests.post(url, headers=self.get_headers(), data=json.dumps(updated_notebook_definiton))
        
        if response.status_code == 202:
            return response.headers.get("Location", None)
        else:
            return handle_response(response, NotebookDefinition)
        
    def get_notebooks(self, workspaceId: str) -> List[Notebook]:
        base_url = self.endpoint_pattern.format(workspaceId)
        response = requests.get(base_url,  headers=self.get_headers())
        return handle_list_response(response, Notebook)

    def create_notebook(self, workspaceId: str, request: CreateNotebookRequest) -> Union[Notebook, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        response = requests.post(base_url, headers=self.get_headers(), data=json.dumps(request.to_dict()))
        
        if response.status_code == 202:
            return response.headers.get("Location", None)
        else:
            return handle_response(response, Notebook)
    
    def get_headers(self):
        token = self.token_provider.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
import json
from typing import List, Union

import requests

from .client_utils import handle_list_response, handle_response
from models.create_workspace_request import CreateWorkspaceRequest
from models.update_spark_settings_request import UpdateSparkSettingsRequest
from models.workspace import Workspace
from models.workspace_spark_settings import WorkspaceSparkSettings
from utils.token_provider import TokenProvider
from logging import Logger

class WorkspaceClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token = token_provider.get_token()
        self.logger = logger
        self.endpoint = f"https://{env}api.fabric.microsoft.com/v1/workspaces"

    def get_workspace(self, workspaceId: str) -> Union[Workspace, None]:
        url = f"{self.endpoint}/{workspaceId}"
        
        response = requests.get(url, headers=self.get_headers())
        return handle_response(response, Workspace)

    def get_workspaces(self) -> List[Workspace]:
        response = requests.get(self.endpoint, headers=self.get_headers())
        return handle_list_response(response, Workspace)

    def delete_workspace(self, workspaceId: str):
        url = f"{self.endpoint}/{workspaceId}/"
        response = requests.delete(url, headers=self.get_headers())
        return response

    def create_workspace(self, request: CreateWorkspaceRequest) -> Union[Workspace, None]:
        response = requests.post(self.endpoint,headers=self.get_headers(), data=json.dumps(request.to_dict()))
        return handle_response(response, Workspace)

    def assign_workspace_capacity(self, workspaceId: str, capacityId: str) -> None:
        url = f"{self.endpoint}/{workspaceId}/assignToCapacity"
        payload = {"capacityId": capacityId}
        response = requests.post(url, headers=self.get_headers(), data=json.dumps(payload))
        handle_response(response, Workspace)
    
    def get_spark_settings(self, workspaceId: str) -> Union[WorkspaceSparkSettings, None]:
        url = f"{self.endpoint}/{workspaceId}/spark/settings"
        response = requests.get(url, headers=self.get_headers())
        return handle_response(response, WorkspaceSparkSettings)

    def update_spark_settings(self, workspaceId, update_spark_settings_request: UpdateSparkSettingsRequest) -> Union[WorkspaceSparkSettings, None]:
        url = f"{self.endpoint}/{workspaceId}/spark/settings"
        response = requests.patch(url, headers=self.get_headers(), data=json.dumps(update_spark_settings_request.to_dict()))
        return handle_response(response, WorkspaceSparkSettings)

    def get_headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
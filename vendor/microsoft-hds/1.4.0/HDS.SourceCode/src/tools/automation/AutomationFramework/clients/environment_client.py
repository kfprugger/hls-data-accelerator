import os
import json
from typing import List, Union
from requests_toolbelt import MultipartEncoder

import requests

from .client_utils import handle_list_response, handle_response
from models.create_environment_request import CreateEnvironmentRequest
from models.environment import Environment
from utils.token_provider import TokenProvider

from logging import Logger

class EnvironmentClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provider
        self.logger = logger
        self.endpoint_pattern = f"https://{env}api.fabric.microsoft.com/v1/workspaces/{{}}/environments"

    def get_environment(self, workspaceId: str, environmentId: str) -> Union[Environment, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{environmentId}"
        response = requests.get(url, headers=self.get_headers())
        return handle_response(response, Environment)

    def get_environments(self, workspaceId: str) -> List[Environment]:
        base_url = self.endpoint_pattern.format(workspaceId)
        response = requests.get(base_url, headers=self.get_headers())
        return handle_list_response(response, Environment)

    def create_environment(self, workspaceId: str, request: CreateEnvironmentRequest) -> Union[Environment, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        response = requests.post(base_url, headers=self.get_headers(), data=json.dumps(request.to_dict()))
        return handle_response(response, Environment)
    
    def publish_environment(self, workspaceId: str, environmentId: str):
        base_url = self.endpoint_pattern.format(workspaceId) + f"/{environmentId}/staging/publish"
        response = requests.post(base_url, headers=self.get_headers())
        
        print(f"Publish environment responded with status code: {response.status_code}")
        
        if response.status_code == 200 and response.content:
            print(json.dumps(response.json(), indent=2))
    
    def update_compute_config(self, workspaceId: str, environmentId: str, sparkCompute: any):
        url = self.endpoint_pattern.format(workspaceId) + f"/{environmentId}/staging/sparkcompute"
        response = requests.patch(url, headers=self.get_headers(), data=json.dumps(sparkCompute))
        
        if response.ok == False:
            print("update compute config requires failed:")
            print(response.status_code)
            print(response.content)
        
        return response
    
    def upload_library(self, workspaceId: str, environmentId: str, library_file_path: str):

        url = self.endpoint_pattern.format(workspaceId) + f"/{environmentId}/staging/libraries"
        root_dir = os.path.dirname(__file__).split("src")[0]
        with open(root_dir + library_file_path, "rb") as file:
            file_content = file.read()
        
        self.logger.info(f"uploading environment library: {os.path.basename(library_file_path)}")
        multi_part_form_data = MultipartEncoder(
            fields={
                "file": (
                    os.path.basename(library_file_path),
                    file_content,
                    "application/octet-stream",
                )
            }
        )
        
        headers = self.get_headers()
        headers["Content-Type"] = multi_part_form_data.content_type
        response = requests.post(url, headers=headers, data=multi_part_form_data)

        if response.status_code == 200:
            self.logger.info("Package uploaded successfully to Fabric environment")
        else:
            self.logger.info(
                f"Failed to upload package to Fabric. Status code: {response.status_code}"
            )
            self.logger.info(f"Response: {response.text}")

    def get_headers(self):
        token = self.token_provider.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def get_staging_libraries(self, workspaceId, environmentId):
        url = self.endpoint_pattern.format(workspaceId) + f"/{environmentId}/staging/libraries"
        response = requests.get(url, headers=self.get_headers())
        
        if response.ok:
            return response.json()
        else:
            return {}
    
    def cancel_publish(self, workspaceId, environmentId):
        url = self.endpoint_pattern.format(workspaceId) + f"/{environmentId}/staging/cancelPublish"
        response = requests.post(url, headers=self.get_headers())
        self.logger.info(f"Cancel publish response code {response.status_code}")
        return response
    
    def delete_staging_library(self, workspaceId, environmentId, libraryToDelete):
        url = self.endpoint_pattern.format(workspaceId) + f"/{environmentId}/staging/libraries?libraryToDelete={libraryToDelete}"
        response = requests.delete(url, headers=self.get_headers())
        self.logger.info(f"Delete library response code {response.status_code}")
        return response
    
    
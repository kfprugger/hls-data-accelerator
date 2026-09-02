import json
from typing import List, Union

import requests

from utils.token_provider import TokenProvider
from .client_utils import handle_list_response, handle_response
from models.create_lakehouse_request import CreateLakehouseRequest
from models.lakehouse import Lakehouse

from logging import Logger

class LakehouseClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provider
        self.logger = logger
        self.endpoint_pattern = f"https://{env}api.fabric.microsoft.com/v1/workspaces/{{}}/lakehouses"

    def get_lakehouse(self, workspaceId: str, lakehouseId: str) -> Union[Lakehouse, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{lakehouseId}"
        self.logger.debug(f"Get lakehouses url: {url}")
        response = requests.get(url, headers=self.get_headers())
        self.logger.debug(f"Get lakehouses response: {response.content}")
        return handle_response(response, Lakehouse)

    def get_lakehouses(self, workspaceId: str) -> List[Lakehouse]:
        base_url = self.endpoint_pattern.format(workspaceId)
        self.logger.debug(f"Get lakehouses url: {base_url}")
        response = requests.get(base_url, headers=self.get_headers())
        return handle_list_response(response, Lakehouse)

    def create_lakehouse(self, workspaceId: str, request: CreateLakehouseRequest) -> Union[Lakehouse, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        self.logger.debug(f"Create lakehouses url: {base_url}, request: {request.to_dict()}")
        response = requests.post(base_url, headers=self.get_headers(), data=json.dumps(request.to_dict()))
        return handle_response(response, Lakehouse)
    
    def get_headers(self):
        token = self.token_provider.get_token()
        return { "Authorization": f"Bearer {token}", "Content-Type": "application/json" }
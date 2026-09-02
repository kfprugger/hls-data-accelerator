import json
from typing import List, Union
import requests

from utils.token_provider import TokenProvider
from .client_utils import handle_list_response, handle_response
from models.event_house import EventHouse
from models.create_event_house_request import CreateEventHouseRequest
from models.event_house_definition import EventHouseDefinition

from logging import Logger

class EventHouseClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provider
        self.logger = logger
        self.endpoint_pattern = f"https://{env}api.fabric.microsoft.com/v1/workspaces/{{}}/EventHouses"

    def get_event_house(self, workspaceId: str, lakehouseId: str) -> Union[EventHouse, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{lakehouseId}"
        response = requests.get(url, headers=self.get_headers())
        self.logger.debug(f"Get event stream response: {response.content}")
        return handle_response(response, EventHouse)

    def get_event_houses(self, workspaceId: str) -> List[EventHouse]:
        base_url = self.endpoint_pattern.format(workspaceId)
        self.logger.debug(f"Get EventHouses url: {base_url}")
        response = requests.get(base_url, headers=self.get_headers())
        return handle_list_response(response, EventHouse)

    def create_event_house(self, workspaceId: str, request: CreateEventHouseRequest) -> Union[EventHouse, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        self.logger.debug(f"Create EventHouse url: {base_url}, request: {request.to_dict()}")
        response = requests.post(base_url, headers=self.get_headers(), data=json.dumps(request.to_dict()))
        return handle_response(response, EventHouse)
    
    def get_event_house_definition(self, workspaceId: str, event_houseId: str) -> Union[EventHouseDefinition, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{event_houseId}/getDefinition"
        response = requests.post(url, headers=self.get_headers())
        return handle_response(response, EventHouseDefinition)
    
    def update_event_house_definition(self,workspaceId: str, event_houseId: str, event_house_definiton: EventHouseDefinition) -> Union[EventHouseDefinition, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{event_houseId}/updateDefinition"
        body = {"definition": event_house_definiton}
        response = requests.post(url, headers=self.get_headers(), data=json.dumps(body))
        return handle_response(response, EventHouseDefinition)
    
    def get_headers(self):
        token = self.token_provider.get_token()
        return { "Authorization": f"Bearer {token}", "Content-Type": "application/json" }
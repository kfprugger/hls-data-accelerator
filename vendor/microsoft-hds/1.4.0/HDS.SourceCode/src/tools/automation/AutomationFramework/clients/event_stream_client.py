import json
from typing import List, Union
import requests

from utils.token_provider import TokenProvider
from .client_utils import handle_list_response, handle_response
from models.event_stream import EventStream
from models.create_event_stream_request import CreateEventStreamRequest
from models.event_stream_definition import EventStreamDefinition

from logging import Logger

class EventStreamClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provider
        self.logger = logger
        self.endpoint_pattern = f"https://{env}api.fabric.microsoft.com/v1/workspaces/{{}}/eventstreams"

    def get_event_stream(self, workspaceId: str, lakehouseId: str) -> Union[EventStream, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{lakehouseId}"
        response = requests.get(url, headers=self.get_headers())
        self.logger.debug(f"Get event stream response: {response.content}")
        return handle_response(response, EventStream)

    def get_event_streams(self, workspaceId: str) -> List[EventStream]:
        base_url = self.endpoint_pattern.format(workspaceId)
        self.logger.debug(f"Get eventstreams url: {base_url}")
        response = requests.get(base_url, headers=self.get_headers())
        return handle_list_response(response, EventStream)

    def create_event_stream(self, workspaceId: str, request: CreateEventStreamRequest) -> Union[EventStream, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        self.logger.debug(f"Create eventStream url: {base_url}, request: {request.to_dict()}")
        response = requests.post(base_url, headers=self.get_headers(), data=json.dumps(request.to_dict()))
        return handle_response(response, EventStream)
    
    def get_event_stream_definition(self, workspaceId: str, event_streamId: str) -> Union[EventStreamDefinition, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{event_streamId}/getDefinition"
        response = requests.post(url, headers=self.get_headers())
        return handle_response(response, EventStreamDefinition)
    
    def update_event_stream_definition(self,workspaceId: str, event_streamId: str, event_stream_definiton: EventStreamDefinition) -> Union[EventStreamDefinition, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{event_streamId}/updateDefinition"
        body = {"definition": event_stream_definiton}
        response = requests.post(url, headers=self.get_headers(), data=json.dumps(body))
        return handle_response(response, EventStreamDefinition)
    
    def get_headers(self):
        token = self.token_provider.get_token()
        return { "Authorization": f"Bearer {token}", "Content-Type": "application/json" }
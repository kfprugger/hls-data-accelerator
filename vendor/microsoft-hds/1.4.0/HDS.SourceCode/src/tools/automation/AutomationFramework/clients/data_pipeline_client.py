import json
from typing import List, Union
from datetime import datetime, timedelta
import requests
import time

from models.data_pipeline import DataPipeline
from models.create_data_pipeline_request import CreateDataPipelineRequest
from models.data_pipeline_definition import DataPipelineDefinition
from utils.token_provider import TokenProvider
from .client_utils import handle_list_response, handle_response
from logging import Logger

class DataPipelineClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provider
        self.logger = logger
        self.endpoint_pattern = f"https://{env}api.fabric.microsoft.com/v1/workspaces/{{}}/dataPipelines"
        self.env = env

    def get_data_pipeline(self, workspaceId: str, dataPipelineId: str) -> Union[DataPipeline, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{dataPipelineId}"
        response = requests.get(url, headers=self.get_headers())
        return handle_response(response, DataPipeline)

    def get_data_pipeline_definition(self, workspaceId: str, dataPipelineId: str) -> Union[DataPipelineDefinition, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{dataPipelineId}/getDefinition"
        response = requests.get(url, headers=self.get_headers())
        return handle_response(response, DataPipelineDefinition)
    
    def update_data_pipeline_definition(self,workspaceId: str, dataPipelineId: str, data_pipeline_definiton: DataPipelineDefinition) -> Union[DataPipelineDefinition, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        url = f"{base_url}/{dataPipelineId}/updateDefinition"
        body = {"definition": data_pipeline_definiton.to_dict()}
        response = requests.post(url, headers=self.get_headers(), data=json.dumps(body))
        return handle_response(response, DataPipelineDefinition)

    def get_data_pipelines(self, workspaceId: str) -> List[DataPipeline]:
        base_url = self.endpoint_pattern.format(workspaceId)
        response = requests.get(base_url,  headers=self.get_headers())
        return handle_list_response(response, DataPipeline)

    def create_data_pipeline(self, workspaceId: str, request: CreateDataPipelineRequest) -> Union[DataPipeline, None]:
        base_url = self.endpoint_pattern.format(workspaceId)
        response = requests.post(base_url, headers=self.get_headers(), data=json.dumps(request.to_dict()))
        return handle_response(response, DataPipeline)
    
    def query_data_pipeline_status(self, workspaceId, jobId):
        url = f"https://{self.env}api.fabric.microsoft.com/v1/workspaces/{workspaceId}/datapipelines/pipelineruns/{jobId}/queryactivityruns"
        
        current_time_utc = datetime.utcnow()
        last_updated_after = (current_time_utc - timedelta(hours=10)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        last_updated_before = current_time_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

        query_body = {
            "filters":[],
            "orderBy":[{"orderBy":"ActivityRunStart","order":"DESC"}],
            "lastUpdatedAfter": last_updated_after,
            "lastUpdatedBefore": last_updated_before
        }
        
        response = requests.post(url, headers=self.get_headers(), data=json.dumps(query_body))
        
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            response = requests.post(url, headers=self.get_headers(), data=json.dumps(query_body))
            
            # Job might start before the status is registered
            if response.status_code == 404:
                self.logger.info(f"Attempt {attempt + 1} of {max_retries}: Received 404 status code. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                response.raise_for_status()  # Raise an exception for other HTTP errors
                return response.json()['value']
        
        raise Exception(f"Failed to get a successful response after {max_retries} attempts")
        
    def get_headers(self):
        token = self.token_provider.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
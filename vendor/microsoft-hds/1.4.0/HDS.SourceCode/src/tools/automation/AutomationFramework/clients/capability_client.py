import json
import requests

from utils.token_provider import TokenProvider
from .client_utils import handle_list_response, handle_response
from models.get_capabilities_response import CapabilityResponse
from .auth_utils import get_hds_mwc_token_details, get_shared_host
from logging import Logger

class CapabilityClient:

    def __init__(self, token_provider: TokenProvider, env: str, logger: Logger):
        self.token_provider = token_provider
        self.env = env
        self.endpoint = "https://{}/webapi/capacities/{}/workloads/dmh/DMHService/automatic/artifacts/{}/v1/capabilities"
        self.logger = logger

    def deploy_capability(self, capacity_id: str, workspace_id: str, solution_id: str, request):
        [target_uri, headers] = self.get_mwc_info(capacity_id, workspace_id, solution_id)
        url = self.endpoint.format(target_uri, capacity_id, solution_id)
        response = requests.post(url=url, headers=headers, data=json.dumps(request))
        return response

    def get_available_updates(self, capacity_id: str, workspace_id: str, solution_id: str):
        [target_uri, headers] = self.get_mwc_info(capacity_id, workspace_id, solution_id)
        endpoint = "https://{}/webapi/capacities/{}/workloads/dmh/DMHService/automatic/artifacts/{}/update"
        url = endpoint.format(target_uri, capacity_id, solution_id)
        response = requests.get(url=url, headers=headers)
        return response.json()

    def update_capabilities(self, capacity_id: str, workspace_id: str, solution_id: str, request) -> requests.Response:
        [target_uri, headers] = self.get_mwc_info(capacity_id, workspace_id, solution_id)
        endpoint = "https://{}/webapi/capacities/{}/workloads/dmh/DMHService/automatic/artifacts/{}/update"
        url = endpoint.format(target_uri, capacity_id, solution_id)
        response = requests.post(url=url, headers=headers, data=json.dumps(request))
        return response

    def get_installed_capabilities(self, capacity_id: str, workspace_id: str, solution_id: str):
        [target_uri, headers] = self.get_mwc_info(capacity_id, workspace_id, solution_id)
        endpoint = "https://{}/webapi/capacities/{}/workloads/dmh/DMHService/automatic/artifacts/{}/capabilities"
        url = endpoint.format(target_uri, capacity_id, solution_id)    
        response = requests.get(url=url, headers=headers)
        self.logger.info(f"Getting installed capabilities response code {response.status_code}")
        return handle_list_response(response, CapabilityResponse)

    def get_all_capabilities(self, capacity_id: str, workspace_id: str, solution_id: str):
        [target_uri, headers] = self.get_mwc_info(capacity_id, workspace_id, solution_id)
        url = "https://{}/webapi/capacities/{}/workloads/dmh/DMHService/automatic/capabilities".format(target_uri, capacity_id)    
        response = requests.get(url=url, headers=headers)
        return handle_list_response(response, CapabilityResponse)

    def get_capability(self, capacity_id: str, workspace_id: str, solution_id: str, capability_key: str):
        [target_uri, headers] = self.get_mwc_info(capacity_id, workspace_id, solution_id)
        endpoint = "https://{}/webapi/capacities/{}/workloads/dmh/DMHService/automatic/artifacts/{}/capabilities"
        url = endpoint.format(target_uri, capacity_id, solution_id) + "/" + capability_key
        
        response = requests.get(url=url, headers=headers)
        
        return handle_response(response, CapabilityResponse)
    
    def get_mwc_info(self, capacity_id: str, workspace_id: str, solution_id: str):
        token = self.token_provider.get_token()
        shared_host = get_shared_host(self.env, token, self.logger)
        [target_uri, headers] = self.get_request_info(capacity_id, workspace_id, solution_id, shared_host)
        return [target_uri, headers]

    def get_request_info(self, capacity_id, workspace_id, solution_id, shared_host = None):
        token = self.token_provider.get_token()
        mwc_token_details = get_hds_mwc_token_details(self.env, capacity_id, workspace_id, workload_type="dmh", shared_host=shared_host, token=token)
        
        mwc_token = mwc_token_details["Token"]
        target_uri = mwc_token_details["TargetUriHost"]
        
        return[
            target_uri, 
            {
                'Authorization': f'MwcToken {mwc_token}',
                'Content-Type': 'application/json',
                'x-ms-workload-resource-moniker': solution_id
            }
        ]
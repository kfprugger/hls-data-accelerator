import json
import time
from typing import Union, Any
import requests

from utils.token_provider import TokenProvider
from .auth_utils import get_hds_mwc_token_details, get_shared_host
from models.git_status_response import GitStatusResponse
from models.create_branch_request import CreateBranchRequest
from models.commit_to_git_request import CommitToGitRequest
from models.ado_provider_details import AdoProviderDetails
from .client_utils import handle_response
from logging import Logger

class GitIntegrationClient:

    def __init__(self, token_provider: TokenProvider, env: str, logger: Logger = None):
        self.token_provider = token_provider
        self.env = env
        self.logger = logger
        self.endpoint_pattern = f"https://{env}api.fabric.microsoft.com/v1/workspaces/{{}}/git"
    
    def get_headers(self):
        token = self.token_provider.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def get_target_uri(self, capacityId: str, workspaceId: str, solutionId: str):
        token = self.token_provider.get_token()
        shared_host = get_shared_host(self.env, token, self.logger)
        [target_uri, headers] = self.get_request_info(capacityId, workspaceId, solutionId, shared_host)
        return target_uri

    def get_status(self, workspaceId: str) -> GitStatusResponse:
        url = self.endpoint_pattern.format(workspaceId) + "/status"
        response = requests.get(url, headers=self.get_headers())
        return handle_response(response, GitStatusResponse)
    
    def create_branch(self, create_branch_request: CreateBranchRequest):
        token = self.token_provider.get_token()
        shared_host = get_shared_host(self.env, token, self.logger)
        url = f"{shared_host}/metadata/git/branches"
        response = requests.post(url=url, data=json.dumps(create_branch_request.toDict()), headers=self.get_headers())
        return response
    
    def connect(self, workspaceId: str, ado_provider_details: AdoProviderDetails):
        url = self.endpoint_pattern.format(workspaceId) + f"/connect"
        response = requests.post(url, headers=self.get_headers(), data=json.dumps(ado_provider_details.toDict())) 
        return response
    
    def initialize_connection(self, workspaceId: str) -> Any:
        url = self.endpoint_pattern.format(workspaceId) + f"/initializeConnection"
        response = requests.post(url, headers=self.get_headers(), data=json.dumps({ "mergePolicy": 0 }))
        return response
            
    def commit_to_git(self, workspaceId: str, request: CommitToGitRequest):
        url = self.endpoint_pattern.format(workspaceId) + f"/commitToGit?skipHeadValidation=true"
        response = requests.post(url, headers=self.get_headers(), data=json.dumps(request.toDict()))
        
        if response.status_code == 202:
            return response.headers["Location"]

        if response.status_code == 200:
            self.logger.info("Commit changes to git complete")
        
        else:
            self.logger.info("Commit changes to git failed")
            self.logger.info(response.status_code)
            self.logger.info(response.content)
        return
            
    def update_from_git(self, workspaceId: str, workspaceHead: str, remoteCommitHash: str):
        url = self.endpoint_pattern.format(workspaceId) + f"/updateFromGit"
        payload = {
            "workspaceHead": workspaceHead,
            "remoteCommitHash": remoteCommitHash,
            "conflictResolution": {
                "conflictResolutionType": "Workspace",
                "conflictResolutionPolicy": "PreferWorkspace"
            },
        }
        
        self.logger.debug(json.dumps(payload, indent=2))
        
        response = requests.post(url, headers=self.get_headers(), data=json.dumps(payload))
        
        if response.ok:
            self.logger.info("Starting sync from git branch")
        else:
            self.logger.error(f"Error starting git sync: {response.status_code}, {response.content}")
            return
        
        git_status = self.get_status(workspaceId)
        while git_status.workspaceHead is None:
            git_status = self.get_status(workspaceId)
            self.logger.info("Sync in progress, checking status in 15 seconds...")
            time.sleep(15)
        
        self.logger.info(f"New workspace head commit: {git_status.workspaceHead}")

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
    
    def get_operation_result(self, location: str) -> Any:
        return requests.get(location + "/result", headers=self.get_headers())
    
    def poll_operation(self, location: str, polling_interval = 3, operation_name = "LRO") -> Union[Any, None]:
        lro_complete = False
        status = "not_started"
        duration = 0
        while lro_complete == False:
            lro_response = requests.get(location, headers=self.get_headers())
            if lro_response.ok:
                lro_json = lro_response.json()
                if 'status' in lro_json:
                    status = lro_json['status'].lower()
                    if status == 'succeeded':
                        lro_complete = True
                    elif status == 'failed':
                        lro_complete = True
                    else:
                        self.logger.info(f"{duration}s: {operation_name} operation has a status of {status}, polling again...")
                        time.sleep(polling_interval)
                        duration = duration + polling_interval
                else:
                    self.logger.info(f"Status not found in {operation_name} operation response")
                    lro_complete = True
            else:
                self.logger.info(f"Poll operation error: {lro_response.status_code}")
                self.logger.info(lro_response.content)
                return

import json
import time
from typing import Any, Dict

import requests

from models.environment import Environment
from models.item_job_instance import ItemJobInstance
from models.lakehouse import Lakehouse
from utils.token_provider import TokenProvider
from .client_utils import handle_response
from logging import Logger

class JobClient:
    
    def __init__(self, token_provider: TokenProvider, env="msit", logger: Logger = None):
        self.token_provider = token_provider
        self.logger = logger
        self.endpoint_pattern = f"https://{env}api.fabric.microsoft.com/v1/workspaces/{{}}/items/{{}}/jobs"

    def get_job_status(self, workspace_id: str, item_id, job_id: str) -> ItemJobInstance:
        base_url = self.endpoint_pattern.format(workspace_id, item_id)
        
        url = base_url + f"/instances/{job_id}"
        self.logger.debug(url)
        response = requests.get(url, headers=self.get_headers())
        return handle_response(response, ItemJobInstance)
    
    def poll_job_status(self, workspace_id: str, item_id, job_id: str, interval_in_secords = 5) -> str:
        """_summary_
        Polls the job status until it is completed or failed.

        Args:
            workspace_id (str): Workspace id.
            item_id (_type_): The job item id.
            job_id (str): The job id.

        Returns:
            str: Final job status
        """
        is_first_poll = True

        while True:

            job_instance = self.get_job_status(workspace_id, item_id, job_id)

            self.logger.debug(json.dumps(job_instance.to_dict()))

            if job_instance.status.lower() == 'completed':
                self.logger.info("Job completed successfully.")
                break

            elif job_instance.status.lower() == 'failed':
                if is_first_poll:
                    self.logger.info(f"Job status is failed on first poll, waiting {interval_in_secords} seconds...")
                    time.sleep(15)
                else:
                    self.logger.error("Job failed.")
                    break
            else:
                self.logger.info(f"Job status: {job_instance.status.lower()}. Polling again in {interval_in_secords} seconds...")
                time.sleep(interval_in_secords)
            
            is_first_poll = False

        return job_instance.status
        
    def run_notebook(
        self,
        workspace_id: str,
        notebook_id: str,
        env: Environment,
        default_lakehouse: Lakehouse,
        paramerters: Dict[str, Any],
        spark_config: Dict,
        use_starter_pool: bool = True
    ) -> str:
        """_summary_

        Args:
            workspace_id (str): The workspace id.
            notebook_id (str): The notebook id.
            env (Environment): The environment id.
            default_lakehouse (Lakehouse): The default lakehouse id.
            paramerters (Dict[str, Any]): notebook parameters.
            spark_config (Dict): spark configuration.

        Raises:
            Exception: Raised if job failed to run

        Returns:
            str: The job id
        """

        base_url = self.endpoint_pattern.format(workspace_id, notebook_id) + "/instances?jobType=RunNotebook"
        formatted_parameters: Dict[str, Any] = {}
        for k, v in paramerters.items():
            
            value_type = "string"
            if k.isnumeric():
                value_type = "int"
                
            formatted_parameters[k] = {
                "value": v,
                "type": value_type
                }
        
        run_notebook_request = {
            "executionData": {
                "parameters": formatted_parameters,
                "configuration": {
                    "conf": spark_config,
                    "environment": {
                        "id": env.id,
                        "name": env.displayName
                    },
                    "defaultLakehouse": {
                        "name": default_lakehouse.displayName,
                        "id": default_lakehouse.id,
                        "workspaceId": workspace_id
                    },
                }
            }
        }
        
        if use_starter_pool:
            run_notebook_request["executionData"]["configuration"]["useStarterPool"] = True
        else:
            run_notebook_request["executionData"]["configuration"]["useWorkspacePool"] = True
        
        self.logger.debug(json.dumps(run_notebook_request,indent=2))
        self.logger.debug(base_url)
        
        response = requests.post(base_url, headers=self.get_headers(), data=json.dumps(run_notebook_request))
        self.logger.debug(response.status_code)
        if str(response.status_code).startswith('2'):
            self.logger.debug(response.headers['Location'])
            job_location = response.headers['Location']
            job_id = job_location.split("instances/")[-1]
            self.logger.info(f"job id: {job_id}")
            return job_id
        else:
            raise Exception(f"Failed to run notebook: {response.status_code} {response.text}")
    
    def run_data_pipeline(
        self,
        workspace_id: str,
        data_pipeline_id: str,
        paramerters: Dict[str, Any],
    ) -> str:
        """_summary_
        Run a data pipeline job.

        Args:
            workspace_id (str): The workspace id.
            data_pipeline_id (str): The notebook id.
            paramerters (Dict[str, Any]): pipeline parameters.

        Raises:
            Exception: Raised if job failed to run

        Returns:
            str: The job id
        """

        base_url = self.endpoint_pattern.format(workspace_id, data_pipeline_id) + "/instances?jobType=Pipeline"
        formatted_parameters: Dict[str, Any] = {}
        for k, v in paramerters.items():
            
            value_type = "string"
            if k.isnumeric():
                value_type = "int"
                
            formatted_parameters[k] = {
                "value": v,
                "type": value_type
                }
        
        run_notebook_request = {
            "executionData": {
                "parameters": formatted_parameters,
            }
        }
        
        self.logger.debug(base_url)
        response = requests.post(base_url, headers=self.get_headers(), data=json.dumps(run_notebook_request))
        if response.status_code == 202:
            job_location = response.headers['Location']
            job_id = job_location.split("instances/")[-1]
            return job_id
        else:
            raise Exception(f"Failed to run data pipeline: {response.status_code} {response.text}")
    
    def get_headers(self):
        token = self.token_provider.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
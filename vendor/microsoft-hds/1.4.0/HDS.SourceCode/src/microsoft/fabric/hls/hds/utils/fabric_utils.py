import json
import time
from pandas import DataFrame
from sempy import fabric
from sempy.fabric import FabricRestClient

class FabricClientUtils:
    
    @staticmethod
    def get_fabric_client() -> FabricRestClient:
        """_summary_

        Returns:
            FabricRestClient: A new instance of a fabric rest client
        """
        return FabricRestClient()
    
    @staticmethod
    def get_artifact_id() -> str:
        """_summary_

        Returns:
            str: The artifact id without dashes
        """
        return fabric.get_artifact_id().replace("-", "")
    
    @staticmethod
    def list_capacities() -> DataFrame:
        """
        Return a list of capacities that the principal has access to.

        Returns
            pandas.DataFrame: Dataframe listing the capacities.
        """
        return fabric.list_capacities()
    
    @staticmethod
    def get_spark_compute_details(client: FabricRestClient, workspace_id, environment_id):
        """
        Returns spark compute details
        https://learn.microsoft.com/en-us/rest/api/fabric/environment/spark-compute/get-published-settings?tabs=HTTP
        
        Args:
            client (FabricRestClient): The REST client
            workspace_id (_type_): The workspace id
            environment_id (_type_): The environment id

        Returns:
            _type_: EnvironmentSparkCompute (see online doc)
        """
        spark_compute_response = client.get(f"v1/workspaces/{workspace_id}/environments/{environment_id}/sparkcompute")
        return json.loads(spark_compute_response.content)
    
    @staticmethod
    def get_spark_pool_details(client: FabricRestClient, workspace_id, pool_id):
        """
        Returns spark pool settings for a given pool id
        https://learn.microsoft.com/en-us/rest/api/fabric/spark/custom-pools/get-workspace-custom-pool?tabs=HTTP#custompool
        
        Args:
            client: The REST client
            workspace_id: The workspace id
            environment_id: The environment id
            
        Returns:
            _type_: CustomPool (see online doc)
        """        
        spark_pool_response = client.get(f"v1/workspaces/{workspace_id}/spark/pools/{pool_id}")
        return json.loads(spark_pool_response.text)
    
    @staticmethod
    def get_workspace_spark_settings(client: FabricRestClient, workspace_id):
        """
        Returns workspace spark settings
        https://learn.microsoft.com/en-us/rest/api/fabric/spark/workspace-settings/get-spark-settings?tabs=HTTP#code-try-0
        
        Args:
            client: The REST client
            workspace_id: The workspace id
            
        Returns:
            _type_: WorkspaceSparkSettings (see docs)
        """        
        spark_settings_response = client.get(f"v1/workspaces/{workspace_id}/spark/settings")
        return json.loads(spark_settings_response.text)

    @staticmethod
    def get_environment_spark_properties(workspace_id: str, environment_id: str) -> dict | None:
        try:
            client = FabricRestClient() 
            environment_spark_settings_response = client.get(f"/v1/workspaces/{workspace_id}/environments/{environment_id}/sparkcompute")
            environment_spark_properties = json.loads(environment_spark_settings_response.text)
            return environment_spark_properties["sparkProperties"] if "sparkProperties" in environment_spark_properties else None
        except Exception:
            return {}

    @staticmethod
    def get_notebook(workspace_id: str, notebook_id: str) -> dict:
        """
        Returns a Notebook object
        https://learn.microsoft.com/en-us/rest/api/fabric/notebook/items/get-notebook?tabs=HTTP#code-try-0
        
        Args:
            workspace_id: The workspace id
            notebook_id: The notebook id
        Returns:
            _type_: Notebook (see docs)
        """  
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                client = FabricRestClient()
                response = client.get(f"/v1/workspaces/{workspace_id}/notebooks/{notebook_id}")
                
                # Retry if we get a temporary error: 408, 429 or any 500-level error.
                if response.status_code in [429, 408] or (500 <= response.status_code < 600):
                    if attempt < max_attempts:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        return {}
                    
                # For other error codes, do not retry
                if response.status_code >= 400:
                    return {}
                
                return json.loads(response.text)
            
            except Exception as e:
                return {}
        
        return {}
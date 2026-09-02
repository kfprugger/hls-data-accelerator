from typing import Any, Dict, List, Union

from utils.token_provider import TokenProvider
from .capacity_client import CapacityClient
from .environment_client import EnvironmentClient
from .lakehouse_client import LakehouseClient
from .notebook_client import NotebookClient
from .workspace_client import WorkspaceClient
from .data_pipeline_client import DataPipelineClient
from .capability_client import CapabilityClient
from .job_client import JobClient
from .dmh_client import DmhClient
from .event_stream_client import EventStreamClient
from .event_house_client import EventHouseClient
from .long_running_operations_client import LongRunningOperationsClient
from .git_integration_client import GitIntegrationClient
from models.capacity import Capacity
from models.create_capacity_request import CreateCapacityRequest
from models.create_environment_request import CreateEnvironmentRequest
from models.create_lakehouse_request import CreateLakehouseRequest
from models.create_notebook_request import CreateNotebookRequest
from models.create_workspace_request import CreateWorkspaceRequest
from models.create_data_pipeline_request import CreateDataPipelineRequest
from models.environment import Environment
from models.lakehouse import Lakehouse
from models.notebook import Notebook
from models.notebook_definition import NotebookDefinition
from models.workspace import Workspace
from models.workspace_spark_settings import WorkspaceSparkSettings
from models.data_pipeline import DataPipeline
from models.data_pipeline_definition import DataPipelineDefinition
from models.deploy_capability_request_detail_v1 import DeployCapabilityRequestDetailV1
from models.healthcare_data_solution_item import HealthcareDataSolutionItem
from models.git_status_response import GitStatusResponse
from models.create_branch_request import CreateBranchRequest
from models.ado_provider_details import AdoProviderDetails
from models.initialize_git_connection_response import InitializeGitConnectionResponse
from models.commit_to_git_request import CommitToGitRequest

class FabricClient:

    def __init__(self, token_provider: TokenProvider, env="msit", logger=None):
        self.env = env
        self.token_provider = token_provider
        self.capacity_client = CapacityClient(token_provider, env, logger)
        self.environment_client = EnvironmentClient(token_provider, env, logger)
        self.lakehouse_client = LakehouseClient(token_provider, env, logger)
        self.workspace_client = WorkspaceClient(token_provider, env, logger)
        self.notebook_client = NotebookClient(token_provider, env, logger)
        self.data_pipeline_client = DataPipelineClient(token_provider, env, logger)
        self.job_client = JobClient(token_provider, env, logger)
        self.dmh_client = DmhClient(token_provider, env, logger)
        self.capability_client = CapabilityClient(token_provider, env, logger)
        self.long_running_operations_client = LongRunningOperationsClient(token_provider, env, logger)
        self.git_client = GitIntegrationClient(token_provider, env, logger)
        self.event_stream_client = EventStreamClient(token_provider, env, logger)
        self.event_house_client = EventHouseClient(token_provider, env, logger)

    def get_workspace_git_status(self, workspaceId: str) -> GitStatusResponse:
        return self.git_client.get_status(workspaceId)

    def create_branch(self, create_branch_request: CreateBranchRequest):
        return self.git_client.create_branch(create_branch_request)

    def connect_workspace_to_git(self, workspaceId: str, ado_provider_details: AdoProviderDetails):
        return self.git_client.connect(workspaceId, ado_provider_details)
    
    def initialize_workspace_git_connection(self, workspaceId: str) -> InitializeGitConnectionResponse:
        return self.git_client.initialize_connection(workspaceId)
            
    def commit_worspace_changes_to_git(self, workspaceId: str, request: CommitToGitRequest):
        result = self.git_client.commit_to_git(workspaceId, request)

        if result and isinstance(result, str):
            operation_id = result.split("/")[-1]
            _ = self.long_running_operations_client.poll_operation(operation_id)

    def update_workspace_from_git(self, workspaceId: str, target_commit: str, remoteCommitHash: str):
        self.git_client.update_from_git(workspaceId, target_commit, remoteCommitHash)

    def create_healthcare_data_solution(self, workspace_id: str, solution_display_name: str) -> HealthcareDataSolutionItem:
        return self.dmh_client.create_healthcare_data_solution(workspace_id, solution_display_name)

    def get_healthcare_data_solutions(self, workspace_id) -> List[HealthcareDataSolutionItem]:
        return self.dmh_client.get_healthcare_data_solutions(workspace_id)
    
    def get_healthcare_data_solution(self, workspace_id: str, solution_id: str) -> HealthcareDataSolutionItem:
        return self.dmh_client.get_healthcare_data_solution(workspace_id, solution_id)

    def deploy_capability(self, capacity_id: str, workspace_id: str, solution_id: str, request: DeployCapabilityRequestDetailV1):
        response = self.capability_client.deploy_capability(capacity_id, workspace_id, solution_id, request)
    
    def get_installed_capabilities(self, capacity_id: str, workspace_id: str, solution_id: str):
        return self.capability_client.get_installed_capabilities(capacity_id, workspace_id, solution_id)

    def get_available_capability_updates(self, capacity_id: str, workspace_id: str, solution_id: str):
        return self.capability_client.get_available_updates(capacity_id, workspace_id, solution_id)
    
    def update_capabilities(self, capacity_id: str, workspace_id: str, solution_id: str):
        response = self.capability_client.update_capabilities(capacity_id, workspace_id, solution_id, {})
    
        operation_id = response.headers["Location"].split("/")[-1]
        lro_result = self.long_running_operations_client.poll_operation(operation_id, interval_in_seconds=10)
        return lro_result

    def get_all_capabilities(self, capacity_id: str, workspace_id: str, solution_id: str):
        return self.capability_client.get_all_capabilities(capacity_id, workspace_id, solution_id)

    def get_capability(self, capacity_id: str, workspace_id: str, solution_id: str, capability_key: str):
        return self.capability_client.get_capability(capacity_id, workspace_id, solution_id, capability_key)

    def get_capacities(self) -> List[Capacity]:
        return self.capacity_client.get_capacities()
    
    def get_capacity(self, capacityId: str) -> Capacity:
        return self.capacity_client.get_capacity(capacityId)
    
    def resume_capacity(self, capacityName: str, subscriptionId: str, resourceGroupName: str):
        return self.capacity_client.resume_capacity(capacityName, subscriptionId, resourceGroupName)

    def pause_capacity(self, capacityName: str, subscriptionId: str, resourceGroupName: str):
        return self.capacity_client.pause_capacity(capacityName, subscriptionId, resourceGroupName)

    def create_capacity(self, create_capacity_request: CreateCapacityRequest, azure_mgmt_token: str) -> Union[Capacity, None]:
        return self.capacity_client.create_capacity(create_capacity_request, azure_mgmt_token)

    def get_workspace(self, workspaceId: str) -> Union[Workspace, None]:
        return self.workspace_client.get_workspace(workspaceId)

    def get_workspaces(self) -> List[Workspace]:
        return self.workspace_client.get_workspaces()
    
    def delete_workspace(self, workspaceId: str):
        return self.workspace_client.delete_workspace(workspaceId)

    def create_workspace(self, request: CreateWorkspaceRequest) -> Union[Workspace, None]:
        return self.workspace_client.create_workspace(request)
    
    def get_spark_settings(self, workspaceId: str) -> Union[WorkspaceSparkSettings, None]:
        return self.workspace_client.get_spark_settings(workspaceId)

    def update_spark_settings(self, workspaceId, workspaceSettings: WorkspaceSparkSettings) -> Union[WorkspaceSparkSettings, None]:
        return self.workspace_client.update_spark_settings(workspaceId, workspaceSettings)
    
    def get_pinned_workspaces(self):
        return self.workspace_client.get_pinned_workspaces()

    def pin_workspace(self, workspaceId: str):
        return self.workspace_client.pin_workspace(workspaceId)

    def assign_workspace_capacity(self, workspaceId, capacityId):
        self.workspace_client.assign_workspace_capacity(workspaceId, capacityId)

    def get_notebook_definition(self, workspaceId: str, notebookId: str) -> Union[NotebookDefinition, None]:
        result = self.notebook_client.get_notebook_definition(workspaceId, notebookId)
        
        if isinstance(result, str):
            operation_id = result.split("/")[-1]
            lro_result = self.long_running_operations_client.poll_operation(operation_id)
            return lro_result
        else:
            return result
    
    def update_notebook_definition(self,workspaceId: str, notebookId: str, notebook_definiton: NotebookDefinition) -> Union[NotebookDefinition, None]:
        result = self.notebook_client.update_notebook_definition(workspaceId, notebookId, notebook_definiton)
        if isinstance(result, str):
            operation_id = result.split("/")[-1]
            lro_result = self.long_running_operations_client.poll_operation(operation_id)
            return lro_result
        else:
            return result
    
    def get_notebooks(self, workspaceId: str) -> List[Notebook]:
        return self.notebook_client.get_notebooks(workspaceId)

    def create_notebook(self, workspaceId: str, request: CreateNotebookRequest) -> Union[Notebook, None]:
        result = self.notebook_client.create_notebook(workspaceId, request)

        if isinstance(result, str):
            operation_id = result.split("/")[-1]
            lro_result = self.long_running_operations_client.poll_operation(operation_id)
            return Notebook(lro_result)
        elif isinstance(result, Notebook):
            return result
    
    def get_lakehouse(self, workspaceId: str, lakehouseId: str) -> Union[Lakehouse, None]:
        return self.lakehouse_client.get_lakehouse(workspaceId, lakehouseId)

    def get_lakehouses(self, workspaceId: str) -> List[Lakehouse]:
        return self.lakehouse_client.get_lakehouses(workspaceId)

    def create_lakehouse(self, workspaceId: str, request: CreateLakehouseRequest) -> Union[Lakehouse, None]:
        return self.lakehouse_client.create_lakehouse(workspaceId, request)
    
    def get_environment(self,  workspaceId: str, environmentId: str) -> Union[Environment, None]:
        return self.environment_client.get_environment(workspaceId, environmentId)

    def get_environments(self,  workspaceId: str) -> List[Environment]:
        return self.environment_client.get_environments(workspaceId)

    def create_environment(self, workspaceId: str, request: CreateEnvironmentRequest) -> Union[Environment, None]:
        return self.environment_client.create_environment(workspaceId, request)
    
    def upload_library_to_environment(self, workspaceId: str, environmentId: str, file_path: str):
        return self.environment_client.upload_library(workspaceId, environmentId, file_path)
    
    def update_environment_spark_compute(self,  workspaceId: str, environmentId: str, sparkCompute: str):
        return self.environment_client.update_compute_config(workspaceId, environmentId, sparkCompute)
    
    def publish_environment(self, workspaceId: str, environmentId: str):
        return self.environment_client.publish_environment(workspaceId, environmentId)
    
    def get_environment_staged_libraries(self, workspaceId: str, environmentId: str):
        return self.environment_client.get_staging_libraries(workspaceId, environmentId)
    
    def delete_environment_library(self, workspaceId: str, environmentId: str, library_name: str):
        return self.environment_client.delete_staging_library(workspaceId, environmentId, library_name)
    
    def cancel_environment_publish(self, workspaceId: str, environmentId: str):
        return self.environment_client.cancel_publish(workspaceId, environmentId)
    
    def get_data_pipeline(self, workspaceId: str, notebookId: str) -> Union[DataPipeline, None]:
        return self.data_pipeline_client.get_data_pipeline(workspaceId, notebookId)

    def get_data_pipeline_definition(self, workspaceId: str, dataPipelineId: str) -> Union[DataPipelineDefinition, None]:
        return self.data_pipeline_client.get_data_pipeline_definition(workspaceId, dataPipelineId)
    
    def update_data_pipeline_definition(self,workspaceId: str, dataPipelineId: str, data_pipeline_definiton: DataPipelineDefinition) -> Union[DataPipelineDefinition, None]:
        return self.data_pipeline_client.update_data_pipeline_definition(workspaceId, dataPipelineId, data_pipeline_definiton)

    def get_data_pipelines(self, workspaceId: str) -> List[DataPipeline]:
        return self.data_pipeline_client.get_data_pipelines(workspaceId)

    def create_data_pipeline(self, workspaceId: str, request: CreateDataPipelineRequest) -> Union[DataPipeline, None]:
        return self.data_pipeline_client.create_data_pipeline(workspaceId, request)
    
    def query_data_pipeline_status(self, workspaceId: str, jobId: str):
        return self.data_pipeline_client.query_data_pipeline_status(workspaceId, jobId)
    
    def get_job_status(self, workspace_id: str, item_id, job_id: str):
        return self.job_client.get_job_status(workspace_id, item_id, job_id)
    
    def poll_job_status(self, workspace_id: str, item_id, job_id: str, interval_in_secords = 5) -> str:
        return self.job_client.poll_job_status(workspace_id, item_id, job_id, interval_in_secords)
    
    def get_event_stream(self, workspace_id: str, event_stream_id: str):
        return self.event_stream_client.get_event_stream(workspace_id, event_stream_id)
    
    def get_event_streams(self, workspace_id: str):
        return self.event_stream_client.get_event_streams(workspace_id)
    
    def get_event_stream_definition(self, workspace_id: str, event_stream_id: str):
        return self.event_stream_client.get_event_stream_definition(workspace_id, event_stream_id)
    
    def create_event_stream(self, workspace_id: str, request: Dict[str, Any]):
        return self.event_stream_client.create_event_stream(workspace_id, request)
    
    def get_event_house(self, workspace_id: str, event_house_id: str):
        return self.event_house_client.get_event_house(workspace_id, event_house_id)
    
    def get_event_houses(self, workspace_id: str):
        return self.event_house_client.get_event_houses(workspace_id)
    
    def get_event_house_definition(self, workspace_id: str, event_house_id: str):
        return self.event_house_client.get_event_house_definition(workspace_id, event_house_id)
    
    def create_event_house(self, workspace_id: str, request: Dict[str, Any]):
        return self.event_house_client.create_event_house(workspace_id, request)
    
    def run_notebook(
        self,
        workspace_id: str,
        notebook_id: str,
        env: Environment,
        default_lakehouse: Lakehouse,
        paramerters: Dict[str, Any],
        spark_config: Dict
    ) -> str:

        return self.job_client.run_notebook(workspace_id,
                notebook_id,
                env,
                default_lakehouse,
                paramerters,
                spark_config)
        
    def run_data_pipeline(
        self,
        workspace_id: str,
        data_pipeline_id: str,
        parameters: Dict[str, Any],
    ) -> str:
        
        return self.job_client.run_data_pipeline(workspace_id, data_pipeline_id, parameters)
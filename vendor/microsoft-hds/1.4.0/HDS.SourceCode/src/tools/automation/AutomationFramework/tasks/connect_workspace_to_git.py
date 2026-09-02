from .base_task import BaseTask
from models.workspace import Workspace
from models.ado_provider_details import AdoProviderDetails
from models.create_branch_request import CreateBranchRequest
from models.commit_to_git_request import CommitToGitRequest
from utils.context_utils import get_value
from exceptions.automation_framework_runtime_exception import AutomationFrameworkRuntimeException
from exceptions.automation_framework_config_validation_exception import AutomationFrameworkValidationException
from logging import Logger

class ConnectWorkspaceToGit(BaseTask):
    
    def __init__(self, fabric_client, context, logger: Logger, task_index):
        super().__init__(fabric_client, context, logger, task_index)

    def execute(self, **kwargs):

        workspace: Workspace = get_value('workspace', self.context, kwargs)
        create_new_branch: bool = get_value('create_new_branch', self.context, kwargs, True)
        commit_changes: bool = get_value('commit_changes', self.context, kwargs, True)
        pull_from_branch: bool = get_value('pull_from_branch', self.context, kwargs, not create_new_branch)
        branchName = get_value('branchName', self.context, kwargs)
        organizationName = get_value('organizationName', self.context, kwargs)
        projectName = get_value('projectName', self.context, kwargs)
        repositoryId = get_value('repositoryId', self.context, kwargs)
        
        if create_new_branch and pull_from_branch:
            raise AutomationFrameworkRuntimeException("Cannot create a new branch and pull from an existing branch at the same time.")
        
        if create_new_branch:
            
            create_branch_request = CreateBranchRequest(
            {
                "branchName": branchName,
                "parentBranchName":"main",
                "organizationName": organizationName,
                "projectName": projectName,
                "repositoryId": repositoryId,
                "providerType": 0,
                "workspaceId": workspace.id
            })
            
            self.fabric_client.create_branch(create_branch_request)
        
        ado_provider_details = AdoProviderDetails({
            "organizationName": organizationName,
            "projectName": projectName,
            "gitProviderType": "AzureDevOps",
            "repositoryName": repositoryId,
            "branchName": branchName,
            "directoryName": ""
        })
        
        self.logger.info(f"Setting up git connection for workspace: {workspace.id}")
        git_connection_response = self.fabric_client.connect_workspace_to_git(workspace.id, ado_provider_details)
        self.logger.info(f"Git connection response status code: {git_connection_response.status_code}")
        
        self.logger.info("\nInitializing connection...")
        response = self.fabric_client.initialize_workspace_git_connection(workspace.id)
        self.logger.info(response.status_code)
        
        # Get the current status of changes
        git_status = None
        try:
            git_status = self.fabric_client.get_workspace_git_status(workspace.id)
        except Exception as ex:
            self.logger.error(ex)
        
        if commit_changes:
            self.logger.info("Changes (resources) staged for commit:")
            for c in git_status.changes:
                self.logger.info(f"\t{c.itemMetadata.displayName}, {c.itemMetadata.itemType}")
        
            self.fabric_client.commit_worspace_changes_to_git(workspace.id, CommitToGitRequest({
                "mode": "All",
                "workspaceHead": git_status.workspaceHead,
                "comment": "committing HDS items.",
                "items": []
            }))
            
        if pull_from_branch:
            self.fabric_client.update_workspace_from_git(
                workspace.id,
                git_status.workspaceHead,
                git_status.remoteCommitHash)

    def onComplete(self, **kwargs):
        pass
    
    def validate_args(self, **kwargs) -> bool:
        
        if "workspace" not in kwargs:
            raise AutomationFrameworkValidationException("ConnectWorkspaceToGit: workspace is required")
        
        if "branchName" not in kwargs:
            raise AutomationFrameworkValidationException("ConnectWorkspaceToGit: branchName is required")
        
        if "organizationName" not in kwargs:
            raise AutomationFrameworkValidationException("ConnectWorkspaceToGit: organizationName is required")
        
        if "projectName" not in kwargs:
            raise AutomationFrameworkValidationException("ConnectWorkspaceToGit: projectName is required")
        
        if "repositoryId" not in kwargs:
            raise AutomationFrameworkValidationException("ConnectWorkspaceToGit: repositoryId is required")
        
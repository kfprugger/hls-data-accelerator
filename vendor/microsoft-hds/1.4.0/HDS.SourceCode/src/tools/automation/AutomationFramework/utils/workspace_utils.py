from typing import Dict, List
from clients.fabric_client import FabricClient
from models.create_workspace_request import CreateWorkspaceRequest
from models.workspace import Workspace
from tools.automation.AutomationFramework.utils.context_utils import print_array

def print_workspaces(workspaceInfos: List[Workspace]):
    rows = []
    for index, workspaceInfo in enumerate(workspaceInfos):
        rows.append([index, workspaceInfo.displayName, workspaceInfo.id, workspaceInfo.capacityId])

    print_array(["Index", "Name", "Id", "Assigned Capacity"], rows)

def select_workspace(fabric_client: FabricClient, capacityId, workspace_configuration: Dict) -> Workspace:
    
    if "id" in workspace_configuration and workspace_configuration["id"] != "":
        workspace = fabric_client.get_workspace(workspace_configuration["id"])
        return workspace
    
    workspaces = fabric_client.get_workspaces()
    
    use_existing_workspace = input("\nDo you want to use an existing workspace? (y/n): ")
    if use_existing_workspace.lower() in ["y", "yes"]:
        
        filtered_workspaces = workspaces
        if len(workspaces) > 20:
            keyword_filter = input(f"\nThere are {len(workspaces)} workspaces, provide a key word as a filter: ")
            filtered_workspaces = [workspace for workspace in workspaces if keyword_filter in workspace.displayName]
        
        print_workspaces(filtered_workspaces)
        selected_workspace_num = input("\nSelect the workspace from the list above by index (ex. 1): ")
        
        if selected_workspace_num.isdecimal() and int(selected_workspace_num) < len(filtered_workspaces):
            selected_workspace = filtered_workspaces[int(selected_workspace_num)]
        else:
            print("Selected workspace not recognized, exiting")
            return

        return selected_workspace

    print("Creating new workspace...")
    displayName = input("\nWorkspace name: ")
    
    while displayName in [workspace.displayName for workspace in workspaces]:
        displayName = ("\nWorkspace name already exists, try again: ")
    
    workspace_description = input("Workspace description (Optional): ")
    
    create_workspace_request = CreateWorkspaceRequest(
        capacityId=capacityId,
        displayName=displayName,
        description=workspace_description
    )

    try:
        workspace: Workspace = fabric_client.create_workspace(create_workspace_request)
        print("\nWorkspace created!")
        return workspace

    except Exception as e:
        print(f"Error creating workspace: {e}")
        return None
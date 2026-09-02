import logging
from clients.fabric_client import FabricClient
from utils import context_logger
from utils.default_azure_credential_token_provider import DefaultAzureCredentialTokenProvider

if __name__ == "__main__":



    workspace_id = "5370abd0-e35e-4307-8c0a-465db6cbc34d"
    solution_id = "1c1336b1-bc2b-4638-924e-592a7c92ba7a"
    capacity_id = "cc03f61d-97e3-4212-b3fa-dc3726b2b047"

    token_provider = DefaultAzureCredentialTokenProvider()
    logger = logging.getLogger(__name__)

    fabric_client = FabricClient(token_provider=token_provider, env="msit", logger=logger)

    #workspace = fabric_client.get_workspace(workspace_id)
    #print(workspace)
    # capabilities = fabric_client.get_installed_capabilities(capacity_id=capacity_id, workspace_id=workspace_id, solution_id=solution_id)

    updates = fabric_client.get_available_capability_updates(capacity_id=capacity_id, workspace_id=workspace_id, solution_id=solution_id)

    fabric_client.update_capabilities(capacity_id=capacity_id, workspace_id=workspace_id, solution_id=solution_id)

    print(updates)
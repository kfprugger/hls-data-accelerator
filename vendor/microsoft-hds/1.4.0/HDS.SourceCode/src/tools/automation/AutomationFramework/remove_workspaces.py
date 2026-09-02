import argparse
from clients.fabric_client import FabricClient
from azure.identity import DefaultAzureCredential
from utils.default_azure_credential_token_provider import DefaultAzureCredentialTokenProvider

def main(delete_workspaces: bool, name_pattern: str):
    print("Starting workspace removal script")
    token_provider = DefaultAzureCredentialTokenProvider()
    fabric_client = FabricClient(token_provider, "dxt", None)
    
    workspaces = fabric_client.get_workspaces()
    for ws in workspaces:
        if name_pattern in ws.displayName:
            print(f"Matched workspace: {ws.displayName}")
            if delete_workspaces:
                print(f"Deleting {ws.displayName}")
                fabric_client.delete_workspace(ws.id)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script to quickly remove workspaces")
    parser.add_argument("-d", "--delete", action="store_true", help="Flag to delete matched workspaces")
    parser.add_argument("-p", "--pattern", type=str, required=True, help="Pattern to match workspace names")
    args = parser.parse_args()
    
    main(args.delete, args.pattern)
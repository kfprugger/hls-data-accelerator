import json
import requests

from utils.upload_files import create_sample_data_directory

def create_connection(connection_name: str, account_url: str, bearer_token: str):
    connection_details = {
        "server": account_url,
        "path:": "/"
    }

    credentialData = [
        {
            "name": "redirectEndpoint",
            "value": "https://gatewayadminportal-msit.azure.com/OAuthRedirect?code=0.AQEAv4j5cvGGr0GRqy180BHbR8iTKLUuvPxHkYt3Aispm7waAGs.AgABBAIAAAApTwJmzXqdR4BN2miheQMYAgDs_wUA9P96OVQkGh8ZPFYBeEJXGM8yq04NksyEXF69uhbJRf_8WALIQ-2db127fx9i7UPDI6603zlyqAD4nxcSwRhg87v53HXa8PUaD8g9I6XO8oXPo5TEdf8v-tWZO-7Zcvms-HMQ05RLu0ARmdTNZrLXfiy8a4zsMokrH2R0lfUXdNruV-XxXVpRBRiwFC3XN5zF5Dc2bJ0EGM3uWHQoVbTYqiwhRpvTgxvnzQMsM3TtBY09kRounBBmiIRmB070Gh7Z6BLNUzcgt6mhlN3Ll8n2tuiltZES35MTU9aRXek8C9GyOiqD4kmAdWDWp1ylQ6LndDVbJ-O8arvodqjFngPfd5ehfaazyYLPM5xAtMdHK0AIUMKEubke_ZcA29Mgrrx-7qZdbN7G9EYrgnxG7mbuQEC5nHCXQiiapSoAN15FmlfNcF9FrlQUlD7h8A8pINtLRamgQB2c29N9Mh_uMUnbrRvNLJA_trSzF4pJmQFdN1k9sHMBYVpJ6AiHqsX77L9dqpRHE89kK6gTav25S_hel1bdmOIwHXzk3-uLwID4DdhEjQtGfvk9viTaqGag8Nq2vSlB_3b-bVm1thoPfzQcr8qOl0JvyVisbwqwGVhtovOeCAtt_3yohHtWbR0Mfu3d4vd6iOzWQxL_en13yw40iA38Sf8A179OraaDSrvfXsY1UKB35fPzIl7D4MeBauKP5NNlrpWPhFRA0YKGfgWANDVMA4-e0Wiv3K-4xxb_cxtN8_IwQZnX7NFu_SLLME13mWUysQFp3rdRww7dVzztK7i8JSu6Sf-3lcvDznn-tqTCWPUr1Qe4F1WIqEMcElytLR2ZuT3T5Kp-rtPYGVp0j0z6dg-Ms74MZbqRgXVrXosbHJczMH7Xk0cbMC0cn2ryAI6JbXFnn0Wo6CYgHuxEI-FBrgBwtcZVTb3UkApUUg&state=e643fceb-519c-4bc1-8d84-dab34d0e13d9&session_state=74e0d6f9-5572-4459-883c-235406f01192#/"
        },
        {
            "name": "oAuth2Nonce",
            "value": bearer_token
        }
    ]
    
    credential_details = {
        "credentialType": "OAuth2",
        "credentials": json.dumps(credentialData),
        "encryptedConnection": "Any",
        "privacyLevel": "None",
        "skipTestConnection": "false",
        "encryptionAlgorithm": "NONE",
        "skipGetOAuthToken": "false"
    }
    
    request_body = {
        "datasourceName": connection_name,
        "datasourceType": "AzureDataLakeStorage",
        "connectionDetails": json.dumps(connection_details),
        "singleSignOnType": "None",
        "credentialDetails": credential_details,
        "allowDatasourceThroughGateway": "false"
        }
    
    print(json.dumps(request_body))
    
    endpoint = "https://api.powerbi.com/v2.0/myorg/me/gatewayClusterCloudDatasource"
    headers={"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
    
    response = requests.post(endpoint, headers=headers, data=json.dumps(request_body))
    
    print(response.status_code)
    print(response.content)

def get_connections(token: str):
    
    uri = "https://api.powerbi.com/v2.0/myorg/me/gatewayClusterDatasources?$expand=users"
    
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    response = requests.get(uri, headers=headers)
    
    response_content = json.loads(response.content)
    
    connections = []
    for connection in response_content["value"]:
        if "datasourceName" in connection:
            connection_details = json.loads(connection["datasourceReference"])
            kind = connection_details["kind"]
            path = connection_details["path"]
            if kind == "AzureDataLakeStorage":            
                
                account_name = str(path).replace("https://", "").split(".")[0]
                sub_path = str(path).split(".net")[1]
                connection_details = {
                    "connectionName" : connection["datasourceName"],
                    "accountName" : account_name,
                    "connectionId": connection["id"],
                    "kind": kind,
                    "path": path,
                    "subpath": sub_path
                }
                connections.append(connection_details)

    return connections

def select_connection(shortcut_configuration, token: str):
    
    connections = get_connections(token)
    
    if "target" in shortcut_configuration and "adlsGen2" in shortcut_configuration["target"]:
        if "connectionId" in shortcut_configuration["target"]["adlsGen2"]:
            connectionId = shortcut_configuration["target"]["adlsGen2"]["connectionId"]
            for connection in connections:
                if connectionId == connection["connectionId"]:
                    print(f"Connection from dev settingss validated: {connection['name']}")
                    return connection
    
    print_connections(connections)
    
    selected_connection_num = input("\nSelect the connection from the list above by index (ex. 1): ")

    if selected_connection_num.isdecimal() and int(selected_connection_num) < len(connections):
        selected_connection = connections[int(selected_connection_num)]
    else:
        print("Selected connection not recognized, exiting")
        return
    
    return selected_connection

def print_connections(connections):
    rows = []
    for index, connection in enumerate(connections):
        rows.append([index, connection["connectionId"], connection["connectionName"], connection["accountName"], connection["subpath"]])

    print_array(["Index", "Id", "Name", "Storage Account", "Sub Path"], rows)

def try_create_shortcut_v2(workspaceId, lakehouseId, shortcut_configuration, token):
    
    endpoint = f"https://msit-onelake.dfs.fabric.microsoft.com/v2.0/workspaces/{workspaceId}/artifacts/{lakehouseId}/shortcuts/batchCreate"
    
    data = {
      "autoRenameOnConflict": True,
      "subFolderPath": shortcut_configuration["path"],
      "name": shortcut_configuration["name"],
      "targetProperties": {
        "TargetAccountType": "ExternalADLS",
        "TargetType": "Folder",
        "Path": shortcut_configuration["target"]["adlsGen2"]["location"],
        "CustomProperties": {
          "shortcutDataConnectionId": shortcut_configuration["target"]["adlsGen2"]["connectionId"]
        }
      }
    }
    
    print(json.dumps(data, indent=2))
    
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(endpoint, headers=headers, data=json.dumps(data))

    if response.status_code == 201:
        print(f"Successfully created shortcut")
        return True
    else:
        print(f"Failed to create shortcut: {response.content}")
        return False
    
def try_create_shortcut(workspaceId, lakehouseId, shortcut_configuration, token) -> bool:

    create_sample_data_directory(workspaceId, lakehouseId)

    endpoint = f"https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items/{lakehouseId}/shortcuts"
    print(endpoint)
    print(shortcut_configuration)
    
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(endpoint, headers=headers, data=json.dumps(shortcut_configuration))

    if response.status_code == 201:
        print(f"Successfully created shortcut")
        return True
    else:
        print(f"Failed to create shortcut: {response.content}")
        return False
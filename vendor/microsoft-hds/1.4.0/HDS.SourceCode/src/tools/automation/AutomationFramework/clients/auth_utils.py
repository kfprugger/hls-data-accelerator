import json
import requests
from logging import Logger

PBI_GLOBAL_SERVICE_ENDPOINTS = {
    "public": "https://api.powerbi.com/",
    "fairfax": "https://api.powerbigov.us",
    "mooncake": "https://api.powerbi.cn",
    "blackforest": "https://app.powerbi.de",
    "msit": "https://api.powerbi.com/",
    "prod": "https://api.powerbi.com/",
    "int3": "https://biazure-int-edog-redirect.analysis-df.windows.net/",
    "dxt": "https://powerbistagingapi.analysis.windows.net/",
    "edog": "https://biazure-int-edog-redirect.analysis-df.windows.net/",
    "dev": "https://onebox-redirect.analysis.windows-int.net/",
    "console": "http://localhost:5001/",
    "daily": "https://dailyapi.powerbi.com/",
}

DEFAULT_GLOBAL_SERVICE_ENDPOINT = "https://api.powerbi.com/"
FETCH_CLUSTER_DETAIL_URI = "powerbi/globalservice/v201606/clusterDetails"

def get_shared_host(env: str, token: str, logger: Logger):
    url = PBI_GLOBAL_SERVICE_ENDPOINTS.get(env, DEFAULT_GLOBAL_SERVICE_ENDPOINT) + FETCH_CLUSTER_DETAIL_URI

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        resp = requests.get(url, headers=headers)
        resp_body = json.loads(resp.content)
        return resp_body["clusterUrl"]
    except Exception:
        logger.error("Failed to fetch shared host")
        raise
    
def get_hds_mwc_token_details(env: str, capacity_id: str, workspace_id: str, workload_type: str = "dmh", shared_host = None, token: str = "", logger: Logger = None):

    if shared_host is None:
        shared_host = get_shared_host(env, token, logger)

    payload = {
        "capacityObjectId": capacity_id,
        "workspaceObjectId": workspace_id,
        "workloadType": workload_type,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        url = f"{shared_host}/metadata/v201606/generatemwctokenv2"
        response = requests.post(url=url, data=json.dumps(payload), headers=headers)
        mwc_token_details = json.loads(response.content)
        return mwc_token_details
    except Exception as e:
        logger.error(f"Failed to generate MWC Token: {str(e)}")
        raise
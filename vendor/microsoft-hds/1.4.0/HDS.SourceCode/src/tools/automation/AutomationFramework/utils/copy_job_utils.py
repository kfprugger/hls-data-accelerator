import json
import requests
import time
from logging import Logger

def create_copy_job_artifact(workspace_id, job_display_name, env, token):
    url = f"https://df-{env}-scus-redirect.analysis.windows.net/metadata/workspaces/{workspace_id}/artifacts"
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    create_artifact_payload = {
        "artifactType": "CopyJob",
        "displayName": job_display_name,
        "payloadContentType": "InlineJson",
        "workloadPayload": "{\"name\":\"copyjob\",\"properties\":{},\"activities\":[]}"
    }

    response = requests.post(url, headers=headers, data=json.dumps(create_artifact_payload))
    artifact_data = response.json()
    copy_job_artifact_id = artifact_data["objectId"]

    return copy_job_artifact_id

def create_copy_job(workspace_id, job_display_name, lakehouse_id, lakehouse_sub_path, connection_id, container_name, source_subpath, logger: Logger = None, token_provider = None, env=""):
    token = token_provider.get_token()
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    copy_job_artifact_id = create_copy_job_artifact(workspace_id, job_display_name, env, token)
    patch_artifact_payload = create_copy_job_artifact_payload(workspace_id, copy_job_artifact_id, job_display_name, lakehouse_id, lakehouse_sub_path, connection_id, container_name, source_subpath)

    response = requests.patch(f"https://df-{env}-scus-redirect.analysis.windows.net/metadata/artifacts/{copy_job_artifact_id}", headers=headers, data=json.dumps(patch_artifact_payload))

    if response.ok and logger:
        logger.info("Created copy job")

    job_id = start_copy_job(copy_job_artifact_id, token, env)

    if logger:
        logger.info("Waiting 15 seconds before polling to give time to start the job...")

    time.sleep(15)
    poll_job_completion(copy_job_artifact_id, job_id, token, env, logger)


def create_lakehouse_copy_job(workspace_id, job_display_name, source_lakehouse_id, source_lakehouse_sub_path, target_lakehouse_id, target_lakehouse_directory, logger: Logger, token_provider, env=""):
    token = token_provider.get_token()
    copy_job_artifact_id = create_copy_job_artifact(workspace_id, job_display_name, env, token)
    patch_artifact_payload = create_lakehouse_copy_payload(workspace_id, copy_job_artifact_id, job_display_name, source_lakehouse_id, source_lakehouse_sub_path, target_lakehouse_id, target_lakehouse_directory)
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.patch(f"https://df-{env}-scus-redirect.analysis.windows.net/metadata/artifacts/{copy_job_artifact_id}", headers=headers, data=json.dumps(patch_artifact_payload))

    if response.ok and logger:
        logger.info("Created copy job definition for sample data")

    job_id = start_copy_job(copy_job_artifact_id, token, env)

    if logger:
        logger.info("Waiting 15 seconds before polling to give time to start the job...")

    time.sleep(15)
    poll_job_completion(copy_job_artifact_id, job_id, token, env, logger)

def create_copy_job_artifact_payload(workspace_id, copy_job_artifact_id, job_display_name, lakehouse_id, lakehouse_sub_path, connection_id, container_name, source_subpath):
    return {
        "artifactType": "CopyJob",
        "displayName": job_display_name,
        "payloadContentType": "InlineJson",
        "workloadPayload": json.dumps(get_workload_payload(workspace_id, copy_job_artifact_id, lakehouse_id, lakehouse_sub_path, connection_id, container_name, source_subpath))
    }

def create_lakehouse_copy_payload(workspace_id, copy_job_artifact_id, job_display_name, source_lakehouse_id, source_lakehouse_sub_path, target_lakehouse_id, target_lakehouse_directory):
    return {
        "artifactType": "CopyJob",
        "displayName": job_display_name,
        "payloadContentType": "InlineJson",
        "workloadPayload": json.dumps(get_lakehouse_copy_payload(workspace_id, copy_job_artifact_id, source_lakehouse_id, source_lakehouse_sub_path, target_lakehouse_id, target_lakehouse_directory))
    }

def get_workload_payload(workspace_id, copy_job_artifact_id, lakehouse_id, lakehouse_sub_path, connection_id, container_name, source_subpath):
    payload = {
        "name": copy_job_artifact_id,
        "properties": {
            "jobMode": "Batch",
            "source": {
                "type": "Binary",
                "connectionSettings": {
                    "type": "AzureBlobFS",
                    "externalReferences": {
                        "connection": connection_id
                    }
                }
            },
            "destination": {
                "type": "Binary",
                "connectionSettings": {
                    "annotations": [],
                    "type": "Lakehouse",
                    "typeProperties": {
                        "workspaceId": workspace_id,
                        "artifactId": lakehouse_id,
                        "rootFolder": "Files"
                    }
                }
            },
            "policy": {
                "timeout": "0.12:00:00"
            }
        },
        "activities": [
            {
                "properties": {
                    "source": {
                        "datasetSettings": {
                            "location": {
                                "type": "AzureBlobFSLocation",
                                "folderPath": source_subpath,
                                "fileSystem": container_name
                            }
                        },
                        "storeSettings": {
                            "recursive": True
                        }
                    },
                    "destination": {
                        "datasetSettings": {
                            "location": {
                                "type": "LakehouseLocation",
                                "folderPath": lakehouse_sub_path
                            }
                        },
                        "storeSettings": {
                            "copyBehavior": "PreserveHierarchy"
                        }
                    }
                }
            }
        ]
    }

    return payload

def get_lakehouse_copy_payload(workspace_id, copy_job_artifact_id, source_lakehouse_id, source_lakehouse_sub_path, target_lakehouse_id, target_lakehouse_directory):
    return {
        "name": copy_job_artifact_id,
        "properties": {
            "jobMode": "Batch",
            "source": {
                "type": "Binary",
                "connectionSettings": {
                    "type": "Lakehouse",
                    "typeProperties": {
                        "workspaceId": workspace_id,
                        "artifactId": source_lakehouse_id,
                        "rootFolder": "Files"
                    }
                }
            },
            "destination": {
                "type": "Binary",
                "connectionSettings": {
                    "type": "Lakehouse",
                    "typeProperties": {
                        "workspaceId": workspace_id,
                        "artifactId": target_lakehouse_id,
                        "rootFolder": "Files"
                    }
                }
            },
            "policy": {
                "timeout": "0.12:00:00"
            }
        },
        "activities": [
            {
                "properties": {
                    "source": {
                        "datasetSettings": {
                            "location": {
                                "type": "LakehouseLocation",
                                "folderPath": source_lakehouse_sub_path
                            }
                        },
                        "storeSettings": {
                            "copyBehavior": "PreserveHierarchy"
                        }
                    },
                    "destination": {
                        "datasetSettings": {
                            "location": {
                                "type": "LakehouseLocation",
                                "folderPath": target_lakehouse_directory
                            }
                        },
                        "storeSettings": {
                            "recursive": True
                        }
                    },
                    "enableStaging": False
                }
            }
        ]
    }

def start_copy_job(copy_job_artifact_id, token, env) -> str:

    url = f"https://df-{env}-scus-redirect.analysis.windows.net/metadata/artifacts/{copy_job_artifact_id}/jobs/CopyJob"
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(url, headers=headers)

    job_data = response.json()
    job_id = job_data["artifactJobInstanceId"]

    return job_id

def poll_job_completion(copy_job_artifact_id, job_id, token, env, logger: Logger):

    url = f"https://df-{env}-scus-redirect.analysis.windows.net/metadata/artifacts/{copy_job_artifact_id}/jobs/{job_id}"
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    response = requests.get(url, headers=headers)
    status = response.json()["statusString"]
    logger.info("Initial job status: " + status)

    while status != "Completed" and status != "Cancelled" and status != "Failed":
        response = requests.get(url, headers=headers)
        status = response.json()["statusString"]
        logger.info(f"Sample data copy job last status: {status}")
        time.sleep(5)
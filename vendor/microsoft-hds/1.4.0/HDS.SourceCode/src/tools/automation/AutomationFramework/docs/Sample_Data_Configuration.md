
# Overview

Integration Tests run against deployed resources and can be configured to use different sample data resources. This document is to provide context on how sample data is source by default and the different ways data can be manipulated in tests / automations.

## Deployed Sample Data

Sample data as a capability deployment targets a folder in the Bronze Lakehouse. Prior to running any pipeline, every integration test by default will move the sample data into the Ingest Folder.

There are 3 Tasks in this approach:

1. Uploading the copy_folder notebook which uses mssparkutils to perform a copy

```json
{
    "type": "SetupNotebook",
    "description": "Setting up notebook to copy sample data",
    "ignore": "false",
    "parameters": {
        "workspace": "$workspace",
        "environment": "$environment",
        "notebooks_path": "/src/tools/automation/AutomationFramework/resources/notebooks/",
        "notebookName": "copy_folder.ipynb",
        "lakehouseConfig": {
            "default_lakehouse_name": "healthcare1_msft_bronze",
            "known_lakehouses": [
            "healthcare1_msft_bronze"
            ]
        },
        "notebook_parameters": {
            "workspace_id": "%%workspace_id%%",
            "lakehouse_id": "%%bronze_lakehouse_id%%",
            "source_path": "/Files/SampleData/Clinical/FHIR-NDJSON/FHIR-HDS/51KSyntheticPatients",
            "destination_directory_path": "/Files/Ingest/Clinical/FHIR-NDJSON/FHIR-HDS/",
            "action": "copy"
        }            
    },
    "outputs": [
        "copy_sample_data_notebook_id"
    ]
},
```

2. Running the Notebook
```json
        {
            "type": "RunNotebook",
            "description": "Running copy sample data notebook",
            "parameters": {
                "workspace": "$workspace",
                "environment": "$environment",
                "notebook_id": "$copy_sample_data_notebook_id",
                "default_lakehouse": "$bronze_lakehouse"
            },
            "outputs": [
                "copy_sample_data_notebook_run_id"
            ]
        },
```

3. Polling the notebook until it completes
```json
        {
            "type": "PollJobCompletion",
            "description": "Polling copy sample data notebook completion",
            "parameters": {
                "workspace": "$workspace",
                "item_id": "$copy_sample_data_notebook_id",
                "job_id": "$copy_sample_data_notebook_run_id"
            }
        },
```

## Other Sources of Sample Data

There are other ways to get sample data into the ingest folder prior to a pipeline run. In order to implement one of these approaches, you will first need to either a) remove the 3 steps outlined above or b) mark the 3 steps above as ignored.

For the following example, there is an associated sample test that one can run independently of a full E2E test. This allows for much quicker validation and execution.

NOTE: Pay attention to **when** this step is being invoked. Sample data should be copied **before** a datapipeline is executed.

### Uploading Local Data

You can upload sample data by using a `UploadFilesToLakehouse` task 

Sample Test Config:

src/tools/automation/AutomationFramework/samples/upload_local_sample_data.json

Notes:
 - You will need to make sure the sample data is under the src folder
 - Not recommended for large (n > 2-3gbs) datasets

```json
{
    "type": "UploadFilesToLakehouse",
    "description": "Uploading local sample data",
    "ignore": "false",
    "parameters": {
        "target_environment": "$targetEnvironment",
        "workspace": "$workspace",
        "target_lakehouse": "$test_lakehouse",
        "local_src_path": "/src/tools/automation/AutomationFramework/resources/sample_data/5_dataset",
        "destination_path": "Files/Ingest/Clinical/FHIR-NDJSON/FHIR-HDS"
    },
    "outputs": []
}
```

### Copying from Storage Account

You can copy from a storage account using

Sample Test Config:

src/tools/automation/AutomationFramework/samples/copy_cloud_sample_data.json

Notes:
 - This streams from storage account into a Lakehouse, there is some local overhead 
 - Also not recommended for large (n > 2-3gbs) datasets

```json
{
    "type": "CopyFromStorageAccount",
    "description": "Copy sample data into Test Lakehouse",
    "parameters": {
        "workspace": "$workspace",
        "blob_storage_account_url": "https://dmhdevsharedsa.blob.core.windows.net/",
        "container_name": "sample-data",
        "source_subpath": "/msft_dmh_sample_data/5_dataset/5_dataset",
        "destination_lakehouse_name": "Test",
        "destination_subpath": "Files/Ingest/Clinical/FHIR-NDJSON/FHIR-HDS"
    }
}
```

### Using a CopyJob Artifact

You can make use of a Fabric CopyJob

Notes:
 - This uses AzCopy under the hood
    - More details: https://learn.microsoft.com/en-us/fabric/data-factory/what-is-copy-job
 - Still in preview, not always stable in lower environments
 - The workspace needs to have a connection
    - https://learn.microsoft.com/en-us/rest/api/fabric/core/connections
 - Recommended for large datasets
   - For reference, the current 51k sample dataset takes 2-3 minutes

```json
{
    "type": "CreateCopyJob",
    "description": "Copying sample data to workspace",
    "ignore": "false",
    "parameters": {
        "workspace": "$workspace",
        "copy_job_name": "CopySampleData",
        "storage_account_name": "stghdssampledatadev",
        "container_name": "healthcare-sampledata",
        "source_subpath": "51KSyntheticPatients",
        "destination_lakehouse_name": "Test",
        "destination_subpath": "Ingest/Clinical/FHIR-NDJSON/Fabric-HDS"
    }
}
```
import json
import os
import sys
from typing import Any
import uuid

pipeline_to_capability_mapping = {"cma": os.environ.get("DM_CARE_MANAGEMENT_ANALYTICS_CAPABILITY_KEY"),
                                  "claims": os.environ.get("DM_CLAIMS_DATA_INGESTION_CAPABILITY_KEY"),
                                  "sdoh": os.environ.get("DM_SOCIAL_DETERMINANTS_OF_HEALTH_CAPABILITY_KEY"),
                                  "customer_insights": os.environ.get("DM_PATIENT_OUTREACH_ANALYTICS_CAPABILITY_KEY"),
                                  "omop": os.environ.get("DM_OMOP_ANALYTICS_CAPABILITY_KEY"),
                                  "clinical_notes_enrichment": os.environ.get("DM_CLINICAL_NOTES_ENRICHMENT_CAPABILITY_KEY"),
                                  "poa": os.environ.get("DM_PATIENT_OUTREACH_ANALYTICS_ADVANCED_CAPABILITY_KEY"),
                                  "imaging": os.environ.get("DM_DICOM_DATA_INGESTION_CAPABILITY_KEY"),
                                  "fhirservice_export": os.environ.get("DM_FHIR_DATA_INGESTION_CAPABILITY_KEY"),
                                  "clinical_data_foundation": os.environ.get("DM_FOUNDATIONS_CAPABILITY_KEY"),
                                  "dax": os.environ.get("DM_DAX_COPILOT_DATA_INSIGHTS_CAPABILITY_KEY"),
                                  "ai_enrichments": os.environ.get("DM_AI_ENRICHMENTS_CAPABILITY_KEY"),}
pipeline_default_capability = os.environ.get("DM_FOUNDATIONS_CAPABILITY_KEY")

notebook_to_capability_mapping = {"cma": os.environ.get("DM_CARE_MANAGEMENT_ANALYTICS_CAPABILITY_KEY"),
                                  "claims": os.environ.get("DM_CLAIMS_DATA_INGESTION_CAPABILITY_KEY"),
                                  "sdoh": os.environ.get("DM_SOCIAL_DETERMINANTS_OF_HEALTH_CAPABILITY_KEY"),
                                  "ci": os.environ.get("DM_PATIENT_OUTREACH_ANALYTICS_CAPABILITY_KEY"),
                                  "omop": os.environ.get("DM_OMOP_ANALYTICS_CAPABILITY_KEY"),
                                  "poa": os.environ.get("DM_PATIENT_OUTREACH_ANALYTICS_ADVANCED_CAPABILITY_KEY"),
                                  "dicom": os.environ.get("DM_DICOM_DATA_INGESTION_CAPABILITY_KEY"),
                                  "fhir_export": os.environ.get("DM_FHIR_DATA_INGESTION_CAPABILITY_KEY"),
                                  "dax": os.environ.get("DM_DAX_COPILOT_DATA_INSIGHTS_CAPABILITY_KEY"),
                                  "ai_enrichments": os.environ.get("DM_AI_ENRICHMENTS_CAPABILITY_KEY"),}
notebook_default_capability = os.environ.get("DM_FOUNDATIONS_CAPABILITY_KEY")


def name_to_capability(name: str, mapping_dict: dict, default_value: str) -> str:
    """_summary_
    Maps the notebook name to the capability key

    Args:
        notebook_name (str): The notebook name

    Returns:
        str: The capability key
    """
    for key, value in mapping_dict.items():
        if key in name:
            return value
    return default_value

def copy_notebooks(notebook_directory: str) -> None:
        for notebook_file_name in os.listdir(notebook_directory):
            if notebook_file_name.endswith('.ipynb'):
                copy_notebook(notebook_directory, notebook_file_name)
                
    
def copy_pipelines(pipelines_directory: str) -> None:
        for pipeline_file_name in os.listdir(pipelines_directory):
            if pipeline_file_name.endswith('.json'):
                copy_pipeline(pipelines_directory, pipeline_file_name)   
                         
def copy_notebook(notebook_directory: str, notebook_file_name: str) -> None:
    """_summary_
    Formats the notebook according to the target environment

    Args:
        json_file (str): The notebook name
        environment (str): The environment (prod or dev)
    """
    try:
        capability = str(name_to_capability(notebook_file_name, notebook_to_capability_mapping, notebook_default_capability))
        notebook_file_path = os.path.join(notebook_directory, notebook_file_name)
        new_directory = os.path.join(str(os.environ.get("DM_HEALTHCARE_ARTIFACTS_DIR")), capability, os.environ.get("DM_NOTEBOOKS_DIR"))
        os.makedirs(new_directory, exist_ok=True)
        new_file_path = os.path.join(new_directory, notebook_file_name)
        with open(notebook_file_path, 'r') as src_file:
            with open(new_file_path, 'w') as dest_file:
                dest_file.write(src_file.read())
        print(f"Copied {notebook_file_name} to {new_directory}")
    except Exception as ex:
        print(f"Error: {ex}")
        sys.exit(1)
        
def copy_pipeline(pipeline_directory: str, pipeline_file_name: str) -> None:
    """_summary_
    Formats the notebook according to the target environment

    Args:
        json_file (str): The notebook name
        environment (str): The environment (prod or dev)
    """
    try:
        capability = str(name_to_capability(pipeline_file_name, pipeline_to_capability_mapping, pipeline_default_capability))
        pipeline_file_path = os.path.join(pipeline_directory, pipeline_file_name)
        new_directory = os.path.join(str(os.environ.get("DM_HEALTHCARE_ARTIFACTS_DIR")), capability, os.environ.get("DM_DATPIPELINES_DIR"))
        os.makedirs(new_directory, exist_ok=True)
        new_file_path = os.path.join(new_directory, pipeline_file_name)
        with open(pipeline_file_path, 'r') as src_file:
            with open(new_file_path, 'w') as dest_file:
                dest_file.write(src_file.read())
        print(f"Copied {pipeline_file_name} to {new_directory}")
    except Exception as ex:
        print(f"Error: {ex}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 1:
        print(
            f"Usage: folder_structure.py <path_to_notebooks_directory> | Received {sys.argv}"
        )
        sys.exit(1)
    
    type_of_files = sys.argv[1].lower()
    path_to_directory = sys.argv[2]
    
    if type_of_files == "notebooks":
        copy_notebooks(path_to_directory)
    elif type_of_files == "pipelines":
        copy_pipelines(path_to_directory)

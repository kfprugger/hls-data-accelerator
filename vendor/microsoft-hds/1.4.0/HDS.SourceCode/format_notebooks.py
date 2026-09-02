import json
import os
import sys
from typing import Any
import uuid
import glob


def format_notebook(notebook_file: str, environment: str) -> None:
    """_summary_
    Formats the notebook according to the target environment

    Args:
        json_file (str): The notebook name
        environment (str): The environment (prod or dev)
    """
    try:
        with open(notebook_file, "r") as f:
            notebook_data = json.load(f)

        if environment.lower() == "prod":
            notebook_name = notebook_file.split("/")[-1]
            excluded_files_from_adding_lakehouse_dependency_node = [
                "msft_config_notebook.ipynb"
            ]
            if notebook_name.lower() not in excluded_files_from_adding_lakehouse_dependency_node:
                add_lakehouse_dependency_node(notebook_data=notebook_data, notebook_name=notebook_name)
            
            add_environment_dependency_node(notebook_data=notebook_data, notebook_name=notebook_name)  
            add_percent_signs_from_run_command(notebook_data)
            
            excluded_files_from_removing_markdown_cells = [
                "msft_ci_silver_customerinsights_transformation.ipynb",
                "msft_poa_silver_gold_tranformation.ipynb",
                "msft_omop_drug_exposure_insights_sample.ipynb",
                "msft_omop_drug_exposure_era_sample.ipynb",
                "msft_fhir_flattening_sample.ipynb",
                "msft_alm_helper.ipynb",
                "msft_generic_dtt_transformation.ipynb"
            ]
            if notebook_name.lower() not in excluded_files_from_removing_markdown_cells:
                remove_markdown_cells(notebook_data)         
                
            add_markdown_header(notebook_data)
            notebook_data = remove_pip_install(notebook_data)
            lock_cells(notebook_data)

        with open(notebook_file, "w") as f:
            json.dump(notebook_data, f, indent=2)

        print(f"Formatted notebook: '{notebook_file}'")
    except Exception as ex:
        print(f"Error: {ex}")
        sys.exit(1)


def add_percent_signs_from_run_command(notebook_data) -> None:
    """_summary_

    Args:
        notebook_data (_type_): The json representation of the notebook

    Returns:
        Any: Updated notebook data
    """
    for cell in notebook_data["cells"]:
        if "cell_type" in cell and str(cell["cell_type"]).lower() == "code":
            if "source" in cell:
                for cell_index, source in enumerate(cell["source"]):
                    if str(source).startswith("%run"):
                        # remove first in case there are any that have been checked in
                        cell["source"][cell_index] = str(source).replace("%%", "")
                        cell["source"][cell_index] = str(source).replace("msft_dm4h_setup_and_config_notebook", "%%msft_dm4h_setup_and_config_notebook%%")


def remove_pip_install(notebook_data) -> Any:
    """_summary_

    Args:
        notebook_data (_type_): The json representation of the notebook

    Returns:
        Any: The updated notebook without pip install cells
    """
    filtered_cells = []
    for cell in notebook_data["cells"]:
        remove_cell = False
        if "cell_type" in cell and str(cell["cell_type"]).lower() == "code":
            if "source" in cell:
                for source in cell["source"]:
                    if "pip install" in source:
                        remove_cell = True
                        break

        if not remove_cell:
            filtered_cells.append(cell)

    notebook_data["cells"] = filtered_cells
    return notebook_data


def lock_cells(notebook_data) -> None:
    """_summary_
    Updates code cells in a notebook to be locked

    Args:
        notebook_data (_type_): The json representation of the notebook
    """
    for cell in notebook_data["cells"]:
        if "cell_type" in cell and str(cell["cell_type"]).lower() == "code":

            editable = False
            run_control = {
                "frozen": False,
            }

            if "metadata" not in cell:
                cell["metadata"] = {}

            cell["metadata"]["run_control"] = run_control
            cell["metadata"]["editable"] = editable

def add_markdown_header(notebook_data) -> None:
    """_summary_
    Removed markdown cells from a notebook

    Args:
        notebook_data (_type_): The json representation of the notebook
    """
    cell_id = str(uuid.uuid4())
    header = {
      "cell_type": "markdown",
      "id": cell_id,
      "metadata": {},
      "source": [
        "##### WARNING\n",
        "The following notebook is intended to be read only. Please do not modify the contents of this notebook.\n"
      ]
    }
    
    notebook_data["cells"].insert(0, header)
    return notebook_data

def remove_markdown_cells(notebook_data) -> None:
    """_summary_
    Removed markdown cells from a notebook

    Args:
        notebook_data (_type_): The json representation of the notebook
    """
    filtered_cells = []
    for cell in notebook_data["cells"]:
        if "cell_type" in cell and str(cell["cell_type"]).lower() == "code":
            filtered_cells.append(cell)
    
    notebook_data["cells"] = filtered_cells

def remove_trident_section_and_add_dependencies(notebook_data: Any, notebook_name: str) -> None:
    if "metadata" in notebook_data:
        if "trident" in notebook_data["metadata"]:
            notebook_data["metadata"]["dependencies"] = notebook_data["metadata"][
                "trident"
            ]
            del notebook_data["metadata"]["trident"]
            print(
                f"Trident section replaced with dependencies section in '{notebook_name}'"
            )

        if "dependencies" not in notebook_data["metadata"]:
            notebook_data["metadata"]["dependencies"] = {}
    
def add_lakehouse_dependency_node(notebook_data: Any, notebook_name: str) -> None:
    """_summary_

    Args:
        notebook_data (Any): The json object represetation of the notebook
        notebook_name (str): The name of the notebook
    """
    if "metadata" in notebook_data:
        default_lakehouse_blob = {
            "default_lakehouse": "%%default_lakehouse_id%%",
            "default_lakehouse_name": "%%default_lakehouse_name%%",
            "default_lakehouse_workspace_id": "%%workspace_id%%",
        }

        remove_trident_section_and_add_dependencies(notebook_data, notebook_name)
        notebook_data["metadata"]["dependencies"]["lakehouse"] = default_lakehouse_blob
        print(f"Default Lakehouse added in '{notebook_name}'")

def add_environment_dependency_node(notebook_data: Any, notebook_name: str) -> None:
    """_summary_

    Args:
        notebook_data (Any): The json object represetation of the notebook
        notebook_name (str): The name of the notebook
    """
    if "metadata" in notebook_data:
        default_environment_blob = {
            "environmentId": "%%environment_id%%",
            "workspaceId": "%%workspace_id%%",
        }

        remove_trident_section_and_add_dependencies(notebook_data, notebook_name)
        notebook_data["metadata"]["dependencies"]["environment"] = default_environment_blob
        print(f"Default Environment added in '{notebook_name}'")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            f"Usage: format_notebooks.py <path_to_notebooks_directory> | Received {sys.argv}"
        )
        sys.exit(1)

    path_to_notebooks_directory = sys.argv[1]
    environment = sys.argv[2]
    notebook_files = []
    
    notebook_files = glob.glob(path_to_notebooks_directory, recursive=True)
    
    # notebook_files = glob.glob(path_to_notebooks_directory, recursive=True)
    # for root, dirs, files in os.walk(path_to_notebooks_directory):
    #     for file in files:
    #         if file.endswith(".ipynb"):
    #             notebook_files.append(os.path.join(root, file))

    for notebook_file in notebook_files:
        format_notebook(notebook_file, environment)
    # for notebook_file in notebook_files:
    #     format_notebook(path_to_notebooks_directory + "/" + notebook_file, environment)

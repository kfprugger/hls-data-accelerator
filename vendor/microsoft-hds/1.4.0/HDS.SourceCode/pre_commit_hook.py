import json
import sys


def format_notebook(json_file):
    try:
        
        notebook_name = json_file.split("/")[-1]

        print(f"Formatting notebook: {notebook_name}")
        
        with open(json_file, 'r') as f:
            data = json.load(f)
                
        remove_lakehouse_environment_dependencies_format_notebook(data, notebook_name)
        remove_percent_signs_from_run_command(data, notebook_name)
        
        # Format the notebook
        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Formatted notebook: '{notebook_name}'")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    
def remove_lakehouse_environment_dependencies_format_notebook(data, notebook_name):
    """This function will remove any attached lakehouse and environment dependencies from the notebook.
    """
    try:
        if 'metadata' in data:
            default_lakehouse_blob = {}
            default_environment_blob = {}
            
            if 'trident' in data['metadata']:
                data['metadata']['dependencies'] = data['metadata']['trident']
                del data['metadata']['trident']
                print(f"Trident section replaced with dependencies section in '{notebook_name}'")
            if "dependencies" not in data['metadata']:
                data['metadata']['dependencies'] = {}
            data['metadata']['dependencies']['lakehouse'] = default_lakehouse_blob
            data["metadata"]["dependencies"]["environment"] = default_environment_blob
        
        print(f"Removed any lakehouse and environment dependencies: '{notebook_name}'")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
        
def remove_percent_signs_from_run_command(notebook_data, notebook_name):
    """%% symbols are used by provisioning scripts to identify the start and end of config notebook name and to replace it with the actual notebook name.
    These symbols are not needed for our daily notebooks, so this function removes them if it finds any
    
    Args:
        notebook_data (_type_): The json representation of the notebook

    Returns:
        Any: Updated notebook data
    """
    if "cells" in notebook_data:
        for cell in notebook_data["cells"]:
            if "cell_type" in cell and str(cell["cell_type"]).lower() == "code":
                if "source" in cell:
                    for cell_index, source in enumerate(cell["source"]):
                        if str(source).startswith("%run"):
                            cell["source"][cell_index] = str(source).replace("%%", "")
        
        print(f"Removed any %% from run command for notebook: '{notebook_name}'")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f'Usage: pre_commit_hook.py <path_to_json_file> | Received {sys.argv}')
        sys.exit(1)
    
    json_file_list = sys.argv[1:]
    for json_file in json_file_list:
        format_notebook(json_file)
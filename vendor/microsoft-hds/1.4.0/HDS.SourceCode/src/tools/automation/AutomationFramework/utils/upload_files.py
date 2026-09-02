from concurrent.futures import ThreadPoolExecutor
import json
from typing import Dict
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient, FileSystemClient
import os
import concurrent.futures

def upload_directory(package_directory: str, fs_client: FileSystemClient, target_folder_root: str, in_parallel = False):

    print("package directory: " + package_directory)
    file_queue = [package_directory]
    
    files_to_upload = []
    while len(file_queue) > 0:
        
        # Pop relative directory off of the queue
        curr_path = file_queue[0]
        file_queue = file_queue[1:]

        # Walk the directory and add files to the list of files to upload
        for root, dirs, files in os.walk(curr_path):
            
            for file in files:
                file_path = os.path.join(root, file)
                files_to_upload.append(file_path)
            
            for dir in dirs:
                file_queue.append(os.path.join(root, dir))
    
    files_to_upload = list(set(files_to_upload))
    print(f"\nuploading {len(files_to_upload)} files to {target_folder_root}: \n")
    
    if in_parallel:
        upload_files_in_parallel(fs_client, package_directory, files_to_upload, target_folder_root)
    else:
        for file_to_upload in files_to_upload:
            upload_file(fs_client, package_directory, file_to_upload, target_folder_root)
    
    print("upload complete.")

def upload_files_in_parallel(fs_client: FileSystemClient, package_directory, files_to_upload: list, target_folder_root: str):
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(upload_file, fs_client, package_directory, file_path, target_folder_root) for file_path in files_to_upload]
        exceptions = []
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as ex:
                exceptions.append(ex)

def create_file_with_content(workspace_id: str, lakehouse_id: str, target_file_path: str, file_content: Dict):

    file_client = None
    try:
        fs_client = get_files_client(workspace_id, lakehouse_id)
        file_client = fs_client.get_file_client(target_file_path)

        # Delete the file if it exists, overwrite content by default
        if fs_client.exists():
            file_client.delete_file()
        
        fc = json.dumps(file_content)
        file_client = fs_client.create_file(f"{target_file_path}", timeout=300)
        file_client.append_data(data=fc, offset=0, length=len(fc))
        file_client.flush_data(len(fc))
        
        file_properties = file_client.get_file_properties()
        
        file_name = file_properties["name"]
        file_size = file_properties["size"]
        print(f"successfully uploaded {target_file_path}, bytes: {file_size}")
    except Exception as ex:
        print(f"Error uploading content to {target_file_path}: {ex}")
        return

def upload_file(fs_client: FileSystemClient, local_directory: str, local_file_path: str, target_folder_root: str):
    
    file_client = None

    try:
        # Augment target Lakehouse path to start at the target directory, not the local directory    
        if target_folder_root != "":
            target_file_path = target_folder_root + local_file_path.split(local_directory)[-1]
        else:
            target_file_path = local_file_path.split(local_directory)[-1]
        
        file_client = fs_client.get_file_client(target_file_path)

        # Delete the file if it exists, overwrite content by default
        if fs_client.exists():
            file_client.delete_file()
        
        file_client = fs_client.create_file(f"{target_file_path}", timeout=300)

        file_content = None

        with open(local_file_path, "rb") as file:
            file_content = file.read()
            
        file_client.append_data(data=file_content, offset=0, length=len(file_content))
        file_client.flush_data(len(file_content))
        
        file_properties = file_client.get_file_properties()
        
        file_name = file_properties["name"]
        file_size = file_properties["size"]
        print(f"successfully uploaded {target_file_path}, bytes: {file_size}")
    except Exception as ex:
        print(f"Error uploading {local_file_path} to {target_folder_root}: {ex}")
        return

def get_tables_client(workspace_id, lakehouse_id, env="msit"):
    # CodeQL [SM05139] This is non-production testing code which is not deployed.
    credential = DefaultAzureCredential()
    account_url = f"https://{env}-onelake.dfs.fabric.microsoft.com/{workspace_id}/{lakehouse_id}"
    
    service_client = DataLakeServiceClient(account_url=account_url, credential=credential)

    fs_client = service_client.get_file_system_client("Tables")
    return fs_client

def get_files_client(workspace_id, lakehouse_id, env="msit"):
    # CodeQL [SM05139] This is non-production testing code which is not deployed.
    credential = DefaultAzureCredential()
    account_url = f"https://{env}-onelake.dfs.fabric.microsoft.com/{workspace_id}/{lakehouse_id}"
    
    service_client = DataLakeServiceClient(account_url=account_url, credential=credential)

    fs_client = service_client.get_file_system_client("Files")
    return fs_client

def upload_assets(workspace_id, lakehouse_id, local_dist_directory_path, target_folder_root):
    
    fs_client = get_files_client(workspace_id, lakehouse_id)
    upload_directory(local_dist_directory_path, fs_client, target_folder_root)
    
def upload_tables(workspace_id, lakehouse_id, local_dist_directory_path, target_folder_root):
    
    fs_client = get_tables_client(workspace_id, lakehouse_id)
    upload_directory(local_dist_directory_path, fs_client, target_folder_root, in_parallel=True)

def upload_sample_data(workspace_id, lakehouse_id, local_directory_path):
    
    fs_client = get_files_client(workspace_id, lakehouse_id, )
    target_folder_root = "DMHSampleData"
    upload_directory(local_directory_path, fs_client, target_folder_root)

def create_sample_data_directory(workspace_id, lakehouse_id):
    
    fs_client = get_files_client(workspace_id, lakehouse_id)
    target_folder_root = "DMHSampleData"
    
    directory_client = fs_client.get_directory_client(target_folder_root)
    
    if directory_client.exists() == False:
        print(f"Creating {target_folder_root} under Files...")
        fs_client.create_directory(target_folder_root)

def create_directory(workspace_id, lakehouse_id, directory_path: str):
    fs_client = get_files_client(workspace_id, lakehouse_id)
    
    directory_client = fs_client.get_directory_client(directory_path)
    
    if directory_client.exists() == False:
        fs_client.create_directory(directory_path)
        print(f"Created {directory_path} under Files...")

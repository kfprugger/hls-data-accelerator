from concurrent.futures import ThreadPoolExecutor, as_completed
import os, shutil, zipfile,ast
from pyspark.sql.functions import udf
from pyspark.sql.types import MapType,StringType
from microsoft.fabric.hls.hds.orchestrate.file_orchestration.file_orchestrator_util import FileOrchestratorUtil as Utils
from microsoft.fabric.hls.hds.orchestrate.file_orchestration.constants import FileOrchestratorConstants as C

# Function to be executed for each partition
def move_files_from_partition(partition, target_path : str, path_to_split : str, thread_size : int) -> list :
    
    def move_file(file_path_row, target_path):
        source_file_path = file_path_row.path
        target_file_path = None
        
        try:            
            file_name = f"{Utils.get_current_timestamp_in_utc()}_{os.path.basename(source_file_path)}"
            source_file_path_split = source_file_path.split(path_to_split)
            source_file_path_split = os.path.dirname(source_file_path_split[1]).lstrip('/')
            os.makedirs(os.path.join(target_path, source_file_path_split), exist_ok=True)
            target_file_path = os.path.join(target_path, source_file_path_split, file_name)
            source_file_path = source_file_path[5:]
            shutil.move(source_file_path, target_file_path)
        except Exception as ex:            
            msg = f"source_file_path: {source_file_path} \ntarget_file_path : {target_file_path}"
            raise Exception(str(ex) + "\n" + str(msg))
    
    with ThreadPoolExecutor(max_workers = thread_size) as executor:
        futures = [executor.submit(move_file, row, target_path) for row in partition]

    exceptions = []
    for future in as_completed(futures):
        try:
            future.result()
        except Exception as ex:                
            exceptions.append(str(ex))
                
    return exceptions

@udf(MapType(StringType(),StringType()))
def extract_files_from_archive(archive_file_path : str, target_path_to_extract : str, 
                                thred_size : int, file_extensions : str, 
                                path_to_split : str) -> list[str] :
    """
    Extracts files from an archive file to a target path.
    Parameters:
    - archive_file_path (str): The path of the archive file.
    - target_path_to_extract (str): The path where the files will be extracted to.
    - thred_size: The size of the thread.
    Returns:
    - list[str]: A list of exceptions that occurred during the extraction process.
    """        
    
    
    def write_file(zip_ref, file : str, target_path_to_extract : str):
        file_name = f"{Utils.get_current_timestamp_in_utc()}_{os.path.basename(file)}"
        target_file_path = os.path.join(target_path_to_extract, file_name)    
        with open(target_file_path, 'wb') as file_wr:                        
            file_wr.write(zip_ref.read(file))
            file_wr.close()    
     
    try:
        exceptions = []
        results = []    
        archive_file_path = archive_file_path[5:]
        file_extensions_list = ast.literal_eval(file_extensions)         
        archive_file_path_split = archive_file_path.split(path_to_split)
        archive_file_path_split = os.path.dirname(archive_file_path_split[1]).lstrip('/')
        target_folder_path = os.path.join(target_path_to_extract, archive_file_path_split)
        os.makedirs(os.path.join(target_folder_path), exist_ok=True)    
                
        with zipfile.ZipFile(archive_file_path, "r") as zip_ref:
            file_list = [x for x in zip_ref.namelist() if x.endswith(tuple(file_extensions_list))]
            thred_size = min(thred_size, len(file_list))
            with ThreadPoolExecutor(max_workers = thred_size) as executor:
                results = [executor.submit(write_file, zip_ref, file, target_folder_path) for file in file_list]
                
        for future in as_completed(results):
            try:
                future.result()
            except Exception as ex:
                exceptions.append(str(ex))
        
        if exceptions:
            return {C.ERROR_ATTR_NAME : exceptions}
        else:
            os.remove(archive_file_path)
    
    except Exception as zip_ex:
        return {C.ERROR_ATTR_NAME : str(zip_ex)}
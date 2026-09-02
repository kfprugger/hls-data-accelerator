import os
import re
from datetime import datetime
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType, BooleanType
from zipfile import ZIP_DEFLATED, ZipFile

@udf(StringType())
def compress_and_delete_file(file_path: str, source_path: str, mount_path: str, delete_enabled: bool) -> str:
    file_name = os.path.basename(file_path)
    leaf_path = os.path.relpath(file_path, source_path)
    
    zip_mount_path = os.path.join(mount_path, f"{leaf_path}.zip")
    file_mount_path = os.path.join(mount_path, leaf_path)
    zip_path_to_be_stored = os.path.join(f"{file_path}.zip")

    # Check if the zipped file already exists to avoid reprocessing
    if os.path.exists(zip_mount_path):
        return zip_path_to_be_stored
    
    try:
        with ZipFile(zip_mount_path, "w", ZIP_DEFLATED) as zf:
            zf.write(file_mount_path, file_name)
        if delete_enabled:
            os.remove(file_mount_path)
        return zip_path_to_be_stored
    except Exception as ex:
        if os.path.exists(zip_mount_path):
            return zip_path_to_be_stored
        return file_path
    
@udf(StringType())
def compress_mv_and_delete_file(
    file_path: str, 
    source_path: str, 
    source_mount_path: str, 
    target_path: str, 
    target_mount_path: str,
    delete_enabled: bool
    ) -> str:
    
    file_name = os.path.basename(file_path)
    leaf_path = os.path.relpath(file_path, source_path)
    target_file_path = file_path.replace(source_path, target_path)

    # replace date if it exists
    date_pattern = r"\d{4}/\d{2}/\d{2}"
    new_date = datetime.utcnow().strftime("%Y/%m/%d")
    target_file_path = re.sub(date_pattern, new_date, target_file_path)

    target_leaf_path = os.path.relpath(target_file_path, target_path)

    zip_mount_path = os.path.join(target_mount_path, f"{target_leaf_path}.zip")
    file_mount_path = os.path.join(source_mount_path, leaf_path)
    zip_path_to_be_stored = os.path.join(f"{target_file_path}.zip")

    os.makedirs(os.path.dirname(zip_mount_path), exist_ok=True)

    # Check if the zipped file already exists to avoid reprocessing
    if os.path.exists(zip_mount_path):
        return zip_path_to_be_stored
    
    try:
        with ZipFile(zip_mount_path, "w", ZIP_DEFLATED) as zf:
            zf.write(file_mount_path, file_name)
        if delete_enabled:
            os.remove(file_mount_path)
        return zip_path_to_be_stored
    except Exception as ex:
        return file_path
    
@udf(BooleanType())
def delete_source_file(file_path: str, base_source_path: str, mount_path: str) -> bool:
    try:
        leaf_path = os.path.relpath(file_path, base_source_path)
        file_mount_path = os.path.join(mount_path, leaf_path)
        if os.path.exists(file_mount_path):
            os.remove(file_mount_path)
            return True
        else:
            return False
    except Exception as e:
        return False
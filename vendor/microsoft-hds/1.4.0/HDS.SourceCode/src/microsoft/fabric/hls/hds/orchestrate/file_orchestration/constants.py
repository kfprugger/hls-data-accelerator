# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing constants used through out the package
"""
from pyspark.sql.types import MapType, StringType

class FileOrchestratorConstants:
    
    LOGGING_FILE_EXTRACTION_ORCHESTRATION: str = "file_orchestration_[extraction_and_movement]"
    
    MAX_THREAD_TO_EXTRACT_ARCHIVE_FILE_DEFAULT = 1000
    MAX_THREAD_TO_MOVE_FILE_DEFAULT = 100
      
    MAX_ARCHIVE_FILE_SIZE_IN_GB_DEFAULT = 8
    
    INGEST_FOLDER = "Ingest"
    PROCESS_FOLDER = "Process"
    
    STATE_STARTED = "started"
    STATE_COMPLETED = "completed"
    
    ORCHESTRATION_MOVE_TYPE = 'File_Movement' 
    ORCHESTRATION_EXTRACT_TYPE = 'Archive_Extract'    
    
    ARCHIVE_EXTRACTION_STATUS = "archive_extraction_status"
    ERROR_ATTR_NAME = "error"
    SOURCE_MOUNT_NAME = "/file_movement_source"
    TARGET_MOUNT_NAME = "/file_movement_target"
    
    MOUNT_FILE_CACHE_TIMEOUT = 100000
    MOUNT_TIMEOUT = 5000
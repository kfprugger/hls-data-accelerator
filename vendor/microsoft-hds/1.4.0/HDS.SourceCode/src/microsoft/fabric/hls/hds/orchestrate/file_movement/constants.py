# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing constants used through out the package
"""
class ArchiveOrchestratorConstants:

    # constants related to compression service
    FILE_PATH_COLUMN_NAME = "filePath"
    FILE_COMPRESSION_PROCESS_NAME = 'FileCompression'     
    FILE_COMPRESSION_MOVEMENT_PROCESS_NAME = 'FileCompressionMovement'
    FILE_DELTETION_PROCESS_NAME = 'FileDeletion'
    FILE_DELETION_STATUS_COLUMN_NAME = 'deletionStatus'
    
    STATE_STARTED = "started"
    STATE_COMPLETED = "completed"


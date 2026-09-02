# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a data class to extract archived files and place them into ready to process state
"""
from pyspark import StorageLevel
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import lit, col, udf, round
from pyspark.sql.types import MapType,StringType
from datetime import datetime
import os, shutil
from microsoft.fabric.hls.hds.orchestrate.file_orchestration.file_orchestrator_util import FileOrchestratorUtil as Utils
from microsoft.fabric.hls.hds.orchestrate.file_orchestration.constants import FileOrchestratorConstants as C

from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.utils import Utils as PlatformCommonUtil
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.orchestrate.file_orchestration.constants import FileOrchestratorConstants as C
from microsoft.fabric.hls.hds.orchestrate.file_orchestration.file_orchestrator_handler import move_files_from_partition, extract_files_from_archive
from microsoft.fabric.hls.hds.execution_metrics.execution_metrics_collector import ExecutionMetricsCollector

class FileOrchestrator():
    
    """
    This class is a wrapper to invoke the the file archive extraction and movement  extract files from archive folder and move them into ready state to start the metadata extraction.
    """
    
    def __init__(self,  spark: SparkSession,                        
                        max_archive_file_size_in_gb : int,
                        max_thread_to_extract_archive_file : int,
                        max_thread_to_move_file : int,
                        mssparkutils_client: MSSparkUtilsClientBase = None) -> None :
        
        self._spark = spark
        self._max_archive_file_size_in_gb = max_archive_file_size_in_gb
        self._max_thread_to_extract_archive_file = max_thread_to_extract_archive_file
        self._max_thread_to_move_file = max_thread_to_move_file
        self._mssparkutils_client = mssparkutils_client
        
        self._logger = LoggingHelper.get_generic_logger(
                    self._spark, f"{C.LOGGING_FILE_EXTRACTION_ORCHESTRATION}.{self.__class__.__name__}", GC.LOGGING_LEVEL)
        
    def start_process(self, modality_paths : list,
                    execution_metrics_collector : ExecutionMetricsCollector,
                    accumulator_activity_id : str):
        self._spark.conf.set("spark.sql.files.ignoreMissingFiles", "true")
        self._execution_metrics_collector = execution_metrics_collector
        self._accumulator_activity_id = accumulator_activity_id
        for modality_path in modality_paths:
            self._process(modality_path)
        self._spark.conf.set("spark.sql.files.ignoreMissingFiles", "false")
    
    def _process(self, modality_path : dict):
       
        source_file_path  = modality_path.get("source_file_path")
        target_file_path  = modality_path.get("target_file_path") 
        file_extensions   = modality_path.get("file_extensions") 
        source_mount_name = modality_path.get("source_mount_name")
        target_mount_name = modality_path.get("target_mount_name")
        modality_name     = modality_path.get("modality_name")
        modality_folder_path = modality_path.get("modality_path")
        
        file_extensions.append("*.zip")
        
        self._logger.info(LC.FO_VERIFY_SOURCE_PATH_INFO_MSG.format(modality_name = modality_name))
        
        # Verifying the modality folders exist inside ingest folder
        if self._mssparkutils_client.fs_exists(source_file_path):
            self._logger.info(LC.FO_MODALITY_PATH_FOUND_INFO_MSG.format(modality_name = modality_name, source_file_path =  source_file_path))
            
            folder_paths = self._mssparkutils_client.fs_ls(source_file_path)

            # Verifying the namespace folders exist in target folder
            if folder_paths:                
                for folder_path in folder_paths:
                    if folder_path.isDir:
                        folder_to_create = os.path.join(target_file_path, folder_path.name, Utils.get_current_date_in_utc())
                        if not self._mssparkutils_client.fs_exists(folder_to_create):
                            self._mssparkutils_client.fs_mkdirs(folder_to_create)
                        
                self._mssparkutils_client.fs_mount(source_file_path,source_mount_name,  {"fileCacheTimeout": C.MOUNT_FILE_CACHE_TIMEOUT, "timeout": C.MOUNT_TIMEOUT})
                self._mssparkutils_client.fs_mount(target_file_path,target_mount_name, {"fileCacheTimeout": C.MOUNT_FILE_CACHE_TIMEOUT, "timeout": C.MOUNT_TIMEOUT})
                
                source_mount_path = "file:" + self._mssparkutils_client.fs_get_mount_path(source_mount_name)
                target_mount_path = "file:" + self._mssparkutils_client.fs_get_mount_path(target_mount_name)

                namespace_folder_paths = self._mssparkutils_client.fs_ls(source_mount_path)
                
                for ns_folder in namespace_folder_paths:
                    if ns_folder.isDir:                
                        files_to_move_path = os.path.join(target_mount_path, ns_folder.name, Utils.get_current_date_in_utc())
                        modality_folder_ns_path = os.path.join(modality_folder_path, ns_folder.name)
                        df = Utils.read_files_with_spark(self._spark, ns_folder.path, file_extensions).cache()
                       
                        if df.isEmpty():
                            self._logger.info(LC.FO_NO_FILES_FOUND_INFO_MSG.format(
                                    orchestration_type = C.ORCHESTRATION_MOVE_TYPE + '_' + C.ORCHESTRATION_EXTRACT_TYPE, modality_name = modality_name, source_path = ns_folder.path))
                        else:
                            files_to_move_df = df.filter(~df['path'].endswith('.zip')).cache()
                            zip_files_to_extract_df = df.filter((df['path'].endswith('.zip')) & (round(df["length"] / (1024 ** 3)) <= int(self._max_archive_file_size_in_gb))).cache()
                                                        
                            if files_to_move_df.isEmpty():
                                self._logger.info(LC.FO_NO_FILES_FOUND_INFO_MSG.format(
                                                orchestration_type = C.ORCHESTRATION_MOVE_TYPE, modality_name = modality_name, source_path = source_file_path))
                            else:
                                self._file_movement_process(modality_name, files_to_move_df, files_to_move_path, source_file_path, modality_folder_ns_path)
                            
                            if zip_files_to_extract_df.isEmpty():
                                self._logger.info(LC.FO_NO_FILES_FOUND_INFO_MSG.format(
                                                orchestration_type = C.ORCHESTRATION_EXTRACT_TYPE, modality_name = modality_name, source_path = source_file_path))
                            else:
                                self._file_archive_extraction_process(modality_name, zip_files_to_extract_df, files_to_move_path, list(file_extensions), modality_folder_ns_path)

                            files_to_move_df.unpersist()
                            zip_files_to_extract_df.unpersist()
                        self._logger.info(LC.FO_DELETING_EMPTY_SOURCE_DIRECTORIES.format(namespace=ns_folder.name))
                        Utils.delete_empty_source_dir(ns_folder.path[5:])
                        df.unpersist()
                           
                self._mssparkutils_client.fs_unmount(source_mount_name)
                self._mssparkutils_client.fs_unmount(target_mount_name)
            else:                
                self._logger.info(LC.FO_NO_NAMESPACE_FOUND_INFO_MSG.format(source_file_path = source_file_path, modality_name = modality_name))
        else:
            self._logger.info(LC.FO_SOURCE_PATH_NOT_FOUND_INFO_MSG.format(source_file_path = source_file_path, modality_name = modality_name))
        
        
    def _file_movement_process(self, modality_name : str, files_to_move_df : DataFrame, 
                                    files_to_move_path : str, source_file_path : str, 
                                    modality_folder_ns_path : str):
        self._logger.info(LC.FO_MOVEMENT_PROCESS_STATE_INFO_MSG.format(
                state = C.STATE_STARTED, modality_name = modality_name, target_path_to_move = files_to_move_path))
        
        files_to_move_path = files_to_move_path[5:]        
        total_files_count = files_to_move_df.count()
        max_thread_to_move_file = min(self._max_thread_to_move_file, total_files_count)
        # Move files from the partition to target path
        failed_files = files_to_move_df.rdd.mapPartitions(lambda partition: move_files_from_partition(partition, files_to_move_path, modality_folder_ns_path, max_thread_to_move_file)).collect()
        
        if failed_files:
            for failed_file in failed_files:
                self._logger.error(LC.FO_PROCESSING_FAILED_ERR_MSG.format(modality_name = modality_name, error_mssg = failed_file))
                
        total_failed_files_count = len(failed_files)
        success_files_count = total_files_count - total_failed_files_count            
        
        self._logger.info(LC.FILE_ORCHESTRATION_PROCESSING_STATUS_INFO_MSG.format(
            modality_name = modality_folder_ns_path,
            total_files_count = total_files_count,
            success_files_count= success_files_count,
            failed_files_count = total_failed_files_count,
            orchestration_type = C.ORCHESTRATION_MOVE_TYPE))
        
        # Collect the execution metrics for logging purposes
        self._execution_metrics_collector.accumulate(
            accumulator_activity_id=self._accumulator_activity_id,
            metrics={ 
                "numSourceFiles": total_files_count,
                "batchesProcessed": 1,
                "numTargetFiles": success_files_count,                                                   
                "activityAttributes": {        
                            "fileSuccessCount": success_files_count,            
                            "fileFailedCount": total_failed_files_count}
            }
        )
        
        self._logger.info(LC.FO_MOVEMENT_PROCESS_STATE_INFO_MSG.format(
            state = C.STATE_COMPLETED, modality_name = modality_name, target_path_to_move = files_to_move_path))
            
            
    def _file_archive_extraction_process(self, modality_name : str, zip_files_to_extract_df : DataFrame,
                                                target_path_extract : str, file_extensions : list, 
                                                modality_folder_ns_path : str):
        self._logger.info(LC.FO_EXTRACT_PROCESS_STATE_INFO_MSG.format(
                state = C.STATE_STARTED, modality_name = modality_name, target_path_to_extract = target_path_extract))
        
        target_path_extract = target_path_extract[5:]
        file_extensions = [x[1:] for x in file_extensions]
        processed_df = zip_files_to_extract_df.select("path",extract_files_from_archive(
            "path", lit(target_path_extract), lit(int(self._max_thread_to_extract_archive_file)), lit(str(list(file_extensions))), lit(modality_folder_ns_path)).alias(C.ARCHIVE_EXTRACTION_STATUS)).cache()

        total_count = processed_df.count()
        failed_archive_files_df = processed_df.filter(col(f"{C.ARCHIVE_EXTRACTION_STATUS}").isNotNull()).cache()
        
        if failed_archive_files_df.isEmpty():
            success_count = total_count
            failed_count = 0
        else:
            failed_archive_files = failed_archive_files_df.collect()
            failed_count = len(failed_archive_files)
            success_count = total_count - failed_count
        
            for row in failed_archive_files:
                error_mssg = row.archive_extraction_status[C.ERROR_ATTR_NAME]
                self._logger.error(LC.FO_PROCESSING_FAILED_ERR_MSG.format(modality_name = modality_name, error_mssg = error_mssg))
    
        failed_archive_files_df.unpersist()
        processed_df.unpersist()
        
        self._logger.info(LC.FILE_ORCHESTRATION_PROCESSING_STATUS_INFO_MSG.format(
                modality_name = modality_folder_ns_path,
                total_files_count = total_count,
                success_files_count= success_count,
                failed_files_count = failed_count,
                orchestration_type = C.ORCHESTRATION_EXTRACT_TYPE))
        
                # Collect the execution metrics for logging purposes
        self._execution_metrics_collector.accumulate(
            accumulator_activity_id=self._accumulator_activity_id,
            metrics={ 
                "numSourceFiles": total_count,
                "batchesProcessed": 1,
                "numTargetFiles": success_count,                   
                "activityAttributes": {  
                        "archiveFileSuccessCount": success_count,
                        "archiveFileFailedCount": failed_count}
            }
        )
        
        self._logger.info(LC.FO_EXTRACT_PROCESS_STATE_INFO_MSG.format(
                state = C.STATE_COMPLETED, modality_name = modality_name, target_path_to_extract = target_path_extract))
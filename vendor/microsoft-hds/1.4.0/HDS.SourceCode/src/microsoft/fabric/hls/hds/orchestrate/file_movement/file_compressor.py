import os
from datetime import datetime
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, lit, input_file_name
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.orchestrate.file_movement.constants import ArchiveOrchestratorConstants as C
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.orchestrate.file_movement.compress_file import compress_and_delete_file, compress_mv_and_delete_file, delete_source_file

class FileCompressor():
    
    def __init__(self, 
                spark: SparkSession,
                source_path_pattern : str,
                source_mount_path: str,
                target_path_pattern: str = None,
                target_mount_path: str = None) -> None:
        
        self.spark = spark
        self._source_path_pattern = source_path_pattern
        self._source_mount_path = source_mount_path
        self._target_path_pattern = target_path_pattern
        self._target_mount_path = target_mount_path

        self._logger = LoggingHelper.get_generic_logger(spark, 
                f"{C.FILE_COMPRESSION_PROCESS_NAME}.{self.__class__.__name__}", GC.LOGGING_LEVEL)         
        
           
    def run_compression_from_df(self, compression_df : DataFrame, row_count : int = 0, **kwargs)  -> DataFrame :
        base_source_path = self._source_path_pattern.split("*")[0]
        
        file_path_column = kwargs.get("file_path_column", C.FILE_PATH_COLUMN_NAME)
        
        delete_enabled = kwargs.get("delete_enabled", True)
        
        self._logger.info(LC.FILE_COMPRESSION_STATE_INFO_MSG.format(
            state= C.STATE_STARTED,
            process_name= C.FILE_COMPRESSION_PROCESS_NAME,
            timestamp= datetime.now(),
            files_path= base_source_path))

        compression_df = compression_df.withColumn(file_path_column, 
            compress_and_delete_file(
                    col(file_path_column),
                    lit(base_source_path),
                    lit(self._source_mount_path),
                    lit(delete_enabled)))
                   
        self._logger.info(LC.FILE_COMPRESSION_STATE_INFO_MSG.format(
            state= C.STATE_COMPLETED, 
            process_name= C.FILE_COMPRESSION_PROCESS_NAME, 
            timestamp= datetime.now(), 
            files_path= base_source_path))
            
        self._logger.info(LC.TOTAL_FILE_COMPRESSION_INFO_MSG.format(
            process_name=C.FILE_COMPRESSION_PROCESS_NAME, 
            compressed_files_count = row_count))
         
        return compression_df
    
    def run_movement_and_compression_from_df(self, compression_df : DataFrame, row_count : int = 0, **kwargs)  -> DataFrame :
        base_source_path = self._source_path_pattern.split("*")[0]
        
        file_path_column = kwargs.get("file_path_column", C.FILE_PATH_COLUMN_NAME)
        
        delete_enabled = kwargs.get("delete_enabled", True)
        
        self._logger.info(LC.FILE_COMPRESSION_STATE_INFO_MSG.format(
            state= C.STATE_STARTED,
            process_name= C.FILE_COMPRESSION_MOVEMENT_PROCESS_NAME,
            timestamp= datetime.now(),
            files_path= base_source_path))

        compression_df = compression_df.withColumn(file_path_column,
            compress_mv_and_delete_file(
                col(file_path_column),
                lit(base_source_path),
                lit(self._source_mount_path),
                lit(self._target_path_pattern),
                lit(self._target_mount_path),
                lit(delete_enabled)))
                   
        self._logger.info(LC.FILE_COMPRESSION_STATE_INFO_MSG.format(
            state= C.STATE_COMPLETED, 
            process_name= C.FILE_COMPRESSION_MOVEMENT_PROCESS_NAME, 
            timestamp= datetime.now(), 
            files_path= base_source_path))

        self._logger.info(LC.TOTAL_FILE_COMPRESSION_INFO_MSG.format(
            process_name=C.FILE_COMPRESSION_MOVEMENT_PROCESS_NAME, 
            compressed_files_count = row_count))
         
        return compression_df
    
    def run_delete_source_files(self, df: DataFrame, file_path_column: str = C.FILE_PATH_COLUMN_NAME) -> DataFrame:
        
        base_source_path = self._source_path_pattern.split("*")[0]
        mount_path = self._source_mount_path
        
        self._logger.info(LC.FILE_COMPRESSION_STATE_INFO_MSG.format(
            state= C.STATE_STARTED,
            process_name= C.FILE_DELTETION_PROCESS_NAME,
            timestamp= datetime.now(),
            files_path= base_source_path))

        # Select distinct file paths
        distinct_paths_df = df.select(file_path_column).distinct()

        # Break the lineage by converting the DataFrame to an RDD and back to a DataFrame
        distinct_paths_df_with_broken_lineage = self.spark.createDataFrame(distinct_paths_df.rdd, distinct_paths_df.schema)
        
        # Delete the files
        result_df = distinct_paths_df_with_broken_lineage.withColumn(
            C.FILE_DELETION_STATUS_COLUMN_NAME, 
            delete_source_file(
                col(file_path_column), 
                lit(base_source_path), 
                lit(mount_path))
            )
        
        successful_deletion_count = result_df.filter(col(C.FILE_DELETION_STATUS_COLUMN_NAME) == True).count()
        
        self._logger.info(LC.TOTAL_FILE_DELETION_INFO_MSG.format(
            process_name=C.FILE_DELTETION_PROCESS_NAME, 
            deleted_files_count = successful_deletion_count))
        
        self._logger.info(LC.FILE_COMPRESSION_STATE_INFO_MSG.format(
            state= C.STATE_COMPLETED, 
            process_name= C.FILE_DELTETION_PROCESS_NAME, 
            timestamp= datetime.now(), 
            files_path= base_source_path))
        
        return result_df
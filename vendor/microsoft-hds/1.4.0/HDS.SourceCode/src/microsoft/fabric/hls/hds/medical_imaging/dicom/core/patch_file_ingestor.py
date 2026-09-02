# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class to extract and Ingest the PATCH File into the Delta Table (ImagingDicom).
This module is part of the Microsoft Fabric Healthcare Data Solutions (HDS) project.
"""

import os
import uuid
from functools import reduce
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.window import Window
from pyspark.sql.functions import filter, col, to_json,from_json, lit, when, size,input_file_name, lower, concat, array, expr,struct,collect_list,row_number, coalesce
from datetime import datetime

from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.constants import ImagingStudyConstants as C
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.utils import Utils as CommonUtils
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.medical_imaging.dicom.utils.utils import Utils
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_to_delta_table_using_path
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.orchestrate.file_movement.file_compressor import FileCompressor
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType
from microsoft.fabric.hls.hds.structured_stream.file_stream_reader import FileStreamReader


class PatchFileIngestor(BaseRunnableService):
    """
    Class used to process the PATCH files and ingest the metadata into the Delta table (ImagingDicom).
    It reads the NDJSON files from the source path, extracts the metadata, and writes it to the Delta table.
    It also handles the ingestion pattern, file compression, and failed files management.   
    """

    def __init__(self,
                 spark: SparkSession,
                 workspace_name: str,
                 solution_name: str,
                 admin_lakehouse_name: str,
                 inline_params: dict = None,
                 one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
                 mssparkutils_client: MSSparkUtilsClientBase = None) -> None:
        """
        Args:
            - spark: spark session
            - workspace_name: Name of the Fabric Workspace
            - solution_name (str): Name of the HDS-Healthcare data solutions OneLake workload solution
            - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
            - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuratio
            - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
            - mssparksutils_client (MSSparkUtilsClientBase): The mssparkutils client
        """
        super().__init__(spark=spark,
                         workspace_name=workspace_name,
                         solution_name=solution_name,
                         admin_lakehouse_name=admin_lakehouse_name,
                         inline_params=inline_params,
                         one_lake_endpoint=one_lake_endpoint,
                         mssparkutils_client=mssparkutils_client)       

    def _setup(self) -> None:
        """
        The setup method for initializing the PATCH Files Ingestion variables
        """
        self.lakehouse_name = self.parameter_service.get_foundation_config_value(
            GC.BRONZE_LAKEHOUSE_ID_KEY)

        self.business_events_ingestion_service = BusinessEventsIngestion(
            spark=self.spark,
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.admin_lakehouse_name,
            solution_name=self.solution_name,
            parameter_service=self.parameter_service
        )

        try:
            self.lakehouse_files_root_path = FolderPath.get_fabric_files_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.lakehouse_name
            )

            self.ingestion_pattern = int(self.parameter_service.get_activity_config_value(
                GC.INGESTION_PATTERN_KEY, C.IngestionPattern.INGEST.value))

            if self.ingestion_pattern == C.IngestionPattern.BYOS.value:
                self.base_source_path = self.parameter_service.get_activity_config_value(GC.EXTERNAL_SOURCE_PATH_KEY,
                                                                                         os.path.join(self.lakehouse_files_root_path, GC.EXTERNAL_FOLDER, GC.MEDICAL_IMAGING_FOLDER, GC.IMAGING_OPERATIONS_FOLDER))
            else:
                self.base_source_path = self.parameter_service.get_activity_config_value(GC.PROCESS_SOURCE_PATH_KEY,
                                                                                         os.path.join(self.lakehouse_files_root_path, GC.PROCESS_FOLDER, GC.MEDICAL_IMAGING_FOLDER, GC.IMAGING_OPERATIONS_FOLDER))

            self.namespace = self.parameter_service.get_activity_config_value(
                GC.NAMESPACE_KEY, None)

            self.failed_files_path = os.path.join(
                self.lakehouse_files_root_path,
                C.FAILED_FILES_FOLDER,
                GC.MEDICAL_IMAGING_FOLDER,
                GC.IMAGING_OPERATIONS_FOLDER
            )

            self.target_table_path = self.parameter_service.get_foundation_config_value(
                GC.IMAGING_DELTA_TABLE_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.lakehouse_name
                )
            )            
            self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            solution_name=self.solution_name
            )                     
            self.base_checkpoint_path = self.parameter_service.get_activity_config_value(
                GC.BASE_CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                    root_path=self.config_files_root_path,
                    checkpoint_folder_name=f"{GC.MEDICAL_IMAGING_CONFIG_FOLDER}/{C.PATCH_FILE_INGESTION_CHECKPOINT_FOLDER}"
                )
            )

            self.business_event_logging_enabled = CommonUtils.to_bool(self.parameter_service.get_activity_config_value(GC.IMAGING_PATCH_FILE_BUSINESS_EVENTS_TABLE_LOGGING_KEY, True))
            
            self.checkpoint_path = Utils.get_chkpt_path_based_on_source(
                self.base_checkpoint_path, self.base_source_path)

            self.is_byos_enabled = self.ingestion_pattern == C.IngestionPattern.BYOS.value
                                    
            self.move_failed_files = CommonUtils.to_bool(self.parameter_service.get_activity_config_value(
                GC.MOVE_FAILED_FILES_KEY, not self.is_byos_enabled))
            self.compression_enabled = CommonUtils.to_bool(self.parameter_service.get_activity_config_value(
                GC.COMPRESSION_ENABLED_KEY, not self.is_byos_enabled))
            self.max_files_per_trigger = int(self.parameter_service.get_activity_config_value(
                GC.MAX_FILES_PER_TRIGGER_KEY, C.ME_MAX_FILES_PER_TRIGGER))
            self.max_bytes_per_trigger = int(self.parameter_service.get_activity_config_value(
                GC.MAX_BYTES_PER_TRIGGER_KEY, C.ME_MAX_BYTES_PER_TRIGGER))

            self.source_mount_path = None
            if self.compression_enabled:                
                self.mssparkutils_client.fs_mount(
                self.base_source_path,
                C.PATCH_FILE_MOUNT_LOCATION,
                {"fileCacheTimeout": C.MOUNT_FILE_CACHE_TIMEOUT, "timeout": C.MOUNT_TIMEOUT})           
           
                self.source_mount_path = self.mssparkutils_client.fs_get_mount_path(C.PATCH_FILE_MOUNT_LOCATION)
                self.spark.conf.set(
                    "spark.sql.files.ignoreMissingFiles", "true")
                self._file_compressor = FileCompressor(
                    self.spark, self.base_source_path, self.source_mount_path)      
            
        except Exception as ex:
            self._logger.error(message=str(ex))
                # Insert a row into Business Events table
            business_events_row_init_failed = self.business_events_ingestion_service.create_new_business_event_row(
                id=str(uuid.uuid4()), activityName=C.IMAGING_PATCH_FILE_NOTEBOOK, sourceLakehouseName=f"{self.lakehouse_name}", targetLakehouseName=f"{self.lakehouse_name}", runId=self.pipeline_run_id, severity=GC.ERROR, eventType=C.BE_EVENT_TYPE_ME_INIT_FAILED, message=str(ex), exception=str(ex)
            )
            self.business_events_ingestion_service.insert_business_events(
                [business_events_row_init_failed])
            raise

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.file,
            sourcePath=self.base_source_path,
            sourceLakehouseName=self.mssparkutils_client.get_lakehouse(
                self.lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(
                self.lakehouse_name).get("id"),
            targetType=ExecutionDataType.deltaTable,
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(
                self.lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(
                self.lakehouse_name).get("id"),
            targetPath=self.target_table_path
        )

    def _get_internal_activity_name(self) -> str:
        return GC.IMAGING_PATCH_FILE_INGESTION_ACTIVITY_NAME

    def _execute(self, **kwargs) -> None:
        """
        Executes the Process function to start the PATCH file ingestion process.
        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.        
        """
        self.process()

    def process(self):
        """
        This method processes NDJSON files present in the folder structure defined by source_path
        and saves the extracted IDs and metadata into the Delta table.
        """
        for namespace in Utils.get_namespaces(self.mssparkutils_client, self.base_source_path, self.namespace):
            source_path = os.path.join(self.base_source_path, namespace)
            checkpoint_path = os.path.join(self.checkpoint_path, namespace)

            self._logger.info(LC.IMAGING_PATCH_FILE_PROCESSING_STATE_INFO_MSG.format(
                state=C.STATE_STARTED,
                process_name=C.PATCH_FILE_PROCESS_NAME,
                timestamp=datetime.now(),
                file_path=source_path))

            # Set up the file stream reader to read NDJSON files
            file_stream_reader = FileStreamReader(self.spark,
                                                    recursiveFileLookup="true",
                                                    pathGlobFilter="*.ndjson",
                                                    maxFilesPerTrigger=self.max_files_per_trigger,
                                                    maxBytesPerTrigger=self.max_bytes_per_trigger)
            
            self._logger.info(
                f"{LC.SET_STRUCTURED_STREAMING_INFO_MSG.format(source_path)}")
            df_stream = file_stream_reader.set_up_streaming_json(C.PATCH_FILE_SCHEMA,source_path)

            query = (df_stream.writeStream.format("delta")
                     .trigger(availableNow=True)
                     .option("checkpointLocation", checkpoint_path)
                     .foreachBatch(lambda df, epoch_id: self._process_patch_files(df, namespace))
                     .start())

            query.awaitTermination()

            self._logger.info(LC.IMAGING_PATCH_FILE_PROCESSING_STATE_INFO_MSG.format(
                state=C.STATE_COMPLETED,
                process_name=C.PATCH_FILE_PROCESS_NAME,
                timestamp=datetime.now(),
                file_path=source_path))

        if self.compression_enabled:
            self.spark.conf.set("spark.sql.files.ignoreMissingFiles", "false")
        if self.source_mount_path is not None:
            self.mssparkutils_client.fs_unmount(C.PATCH_FILE_MOUNT_LOCATION)

    def _process_patch_files(self, df: DataFrame, namespace: str):
        """
        Processes the DataFrame containing patch file metadata, transforms it, validates it,
        and writes valid records to the Delta table. It also handles invalid records and failed file management.

        Args:
            df (DataFrame): The DataFrame containing the patch file metadata.
            namespace (str): The namespace/source system name.
        """
        try:
            
            total_count = df.count()
            if total_count > 0:                
                patch_data_df = self._transform_patch_data_to_df(df, namespace)                    
                patch_data_df = patch_data_df.drop("id","meta","resourceType","identifier", "series", "extension","tag_string")
                
                patch_data_df_valid, patch_data_df_invalid = self._get_valid_and_invalid_df(patch_data_df)
                patch_data_df_valid = patch_data_df_valid.drop('missing_columns_list', 'invalid_operation_flag', 'validation_description')
                                
                if not patch_data_df_valid.isEmpty():               
                    append_to_delta_table_using_path(
                        df_to_process=patch_data_df_valid,
                        delta_table_path=os.path.join(
                            self.target_table_path, C.METADATA_TABLE_NAME),
                        logger=self._logger,
                        collect_metrics_fn=self.collect_target_delta_table_operation_summary_metrics
                    )                
                
                    
                if self.compression_enabled :
                    patch_data_df_valid_distinct_filePaths = patch_data_df_valid.dropDuplicates(["filePath"])
                    distinct_success_files_count = patch_data_df_valid_distinct_filePaths.count()
                    df_success = self._file_compressor.run_compression_from_df(patch_data_df_valid_distinct_filePaths, distinct_success_files_count)
                
                business_events = []
                success_count = total_count
                validation_failed_rows = patch_data_df_invalid.collect()
                failed_count = len(validation_failed_rows)                
                if failed_count > 0:                    
                    #invalid_summary_json_df = self.generate_invalid_summary_json(patch_data_df_invalid)                    
                    success_count = total_count - failed_count
                    for row in validation_failed_rows:
                        validation_error_msg = row.validation_description
                        
                        if self.business_event_logging_enabled:
                            business_events_failed_rows=self._initialize_business_event(namespace, message=validation_error_msg)
                            business_events.append(business_events_failed_rows)                        
                            
                        self._logger.error(LC.IMAGING_PATCH_VALIDATION_FAILED_AGGREGATED_ERR_MSG.format(
                        process_name= C.PATCH_FILE_PROCESS_NAME,                        
                        error_mssg=validation_error_msg))                        
                
                    if self.move_failed_files:
                        patch_data_df_invalid_distinct_filePaths = patch_data_df_invalid.dropDuplicates([C.FILE_PATH_COLUMN_NAME])  # Remove duplicates based on filePath and studyInstanceUid
                        failed_rows_mv_files = patch_data_df_invalid_distinct_filePaths.collect()                        
            
                        for failed_row in failed_rows_mv_files:                        
                            error_mssg=row.validation_description
                            self._logger.error(LC.IMAGING_PATCH_PROCESSING_FAILED_ERR_MSG.format(
                                process_name= C.PATCH_FILE_PROCESS_NAME, 
                                file_name= os.path.basename(failed_row.filePath), 
                                error_mssg=error_mssg))
                            try:
                                Utils.move_files(failed_row.filePath, 
                                                    os.path.join(self.failed_files_path, 
                                                                namespace, 
                                                                Utils.get_current_date_in_utc(), 
                                                                os.path.basename(failed_row.filePath)), 
                                                    self.mssparkutils_client, True)
                            except Exception as e:
                                self._logger.error(LC.FAILED_FILES_NOT_MOVED_ERR_MSG.format(
                                    error_msg=str(e)
                                ))
                                business_events_failed_rows=self._initialize_business_event(namespace, 
                                                                                    LC.IMAGING_PATCH_FILE_FAILED_BS,
                                                                                    str(e),
                                                                                    LC.IMAGING_PATCH_FILE_MOVE_FAILED_FILE_BS,
                                                                                    sourceFilePath=failed_row.filePath)
                                business_events.append(business_events_failed_rows)
                                raise
                        
                if len(business_events) > 0 and self.business_event_logging_enabled:
                    self.business_events_ingestion_service.insert_business_events(business_events)
                 
                self._logger.info(LC.IMAGING_PATCH_FILE_PROCESSING_SUMMARY_INFO_MSG.format(
                total_patch_files=total_count,
                success_files_count=success_count,
                failed_files_count=failed_count,
                process_name=C.PATCH_FILE_PROCESS_NAME,
                timestamp=datetime.now(),
                namespace=namespace))                                             
                
                # Collect the execution metrics for logging purposes
                self.execution_metrics_collector.accumulate(
                accumulator_activity_id=self.get_execution_metrics_accumulator_activity_id(),
                metrics={                    
                    "numSourceFiles": total_count,                    
                    "activityAttributes": {"successCount": success_count,
                                           "failedCount": failed_count }
                }
            )
        except Exception as ex:
            self._logger.error(message=str(ex))    
            business_events_failed_rows=self._initialize_business_event(namespace, 
                                                                        LC.IMAGING_PATCH_FILE_FAILED_BS,
                                                                        str(ex),
                                                                        LC.IMAGING_PATCH_FILE_UNHANDLED_ERROR,
                                                                        sourceFilePath= self.base_source_path)
            self.business_events_ingestion_service.insert_business_events([business_events_failed_rows])
            raise

    def _transform_patch_data_to_df(self, patch_df: DataFrame, namespace: str) -> DataFrame:
        """
        Transforms a DataFrame containing patch file metadata into a structured DataFrame with extracted fields.
        It also parses JSON metadata and tranform into ImagingDicom table schema.

        Args:
            patch_df (DataFrame): The DataFrame containing the patch file data.
            namespace (str): The namespace/source system name.
            
        Returns:
            DataFrame: The transformed metadata DataFrame.
        """
        # Extracting operation, tags, series_uid, and instance_uid
        df_transformed = patch_df.withColumn(
            C.OPERATION,
            expr("""
                filter(extension, x -> lower(trim(x.url)) = 'http://healthcaredatasolutions.com/data-extensions/operation')[0].valueString
            """)
        ).withColumn(C.FILE_PATH_COLUMN_NAME, input_file_name()  
        ).withColumn(C.SOURCE_MODIFIED_COLUMN_NAME,col("meta").getField("lastUpdated").cast("timestamp")                  
        ).withColumn(C.STUDY_INSTANCE_UID,col("identifier").getItem(0).getField("value")                
        ).withColumn(
            C.SERIES_INSTANCE_UID,
            when(size(col("series")) > 0, col("series").getItem(
                0).getField("uid")).otherwise(lit(None))
        ).withColumn(
            C.SOP_INSTANCE_UID,
            when(
                (size(col("series")) > 0) &
                (col("series").getItem(0).getField("instance").isNotNull()) &
                (size(col("series").getItem(0).getField("instance")) > 0),
                col("series").getItem(0).getField(
                    "instance").getItem(0).getField("uid")
            ).otherwise(lit(None))
        ).withColumn(
            C.TAG_STRING,
                expr("""
                    filter(extension, x -> lower(trim(x.url)) = 'http://healthcaredatasolutions.com/data-extensions/operation-dicomtags')[0].valueString
                    """)
        ).withColumn(C.TAGS_JSON_COLUMN_NAME,
                        when(col(C.TAG_STRING).isNotNull(), from_json(
                            col(C.TAG_STRING), C.METADATA_SCHEMA)).otherwise(lit(None))
        ).withColumn(C.TAGS_METADATA_STRING,
                        when(col(C.TAGS_JSON_COLUMN_NAME).isNotNull(), to_json(col(C.TAGS_JSON_COLUMN_NAME))).otherwise(lit(None))    
        ).withColumn(C.SOURCE_SYSTEM_COLUMN_NAME,lit(namespace))
               
        return df_transformed
    
    
    def _get_valid_and_invalid_df(self, patch_data_df: DataFrame) -> tuple[DataFrame, DataFrame]:
        """
        Validates the patch data DataFrame and returns two DataFrames:
        one with valid rows and another with invalid rows based on required columns and operation validity.

        Args:
            patch_data_df (DataFrame): The DataFrame containing the patch file data.

        Returns:
            tuple: A tuple containing two DataFrames:
                - valid_df: DataFrame with valid rows (no nulls in required columns and valid operation),
                            without intermediate validation columns.
                - invalid_df: DataFrame with invalid rows (nulls in required columns OR invalid operation),
                            including a 'validation_description' column (as a string with JSON format).
        """
        # Define required columns and allowed values (keep allowed_operations lowercase for consistent comparison)
        required_columns = ['studyInstanceUid', 'operation']
        allowed_operations = ['patch', 'move', 'soft-delete']

        # Identify existing required columns in the DataFrame schema
        existing_required_columns = [c for c in required_columns if c in patch_data_df.columns]
                
        # missing_columns_list: Array of names of required columns that are null
        raw_missing_columns_array_expr = array(*[
            when(col(c).isNull(), lit(c)).otherwise(lit(None)) for c in existing_required_columns
        ])
        patch_data_df = patch_data_df.withColumn(
            "missing_columns_list",
            filter(raw_missing_columns_array_expr, lambda x: x.isNotNull())
        )

        patch_data_df = patch_data_df.withColumn(
            "invalid_operation_flag",
            when(
                (col("operation").isNull()) | (~lower(col("operation")).isin(allowed_operations)),
                concat(lit("invalid or missing value '"), coalesce(col("operation"), lit("null")), lit("'"))
            ).otherwise(lit(None))
        )

        # This column holds the validation details as a StructType initially.
        validation_struct_col = struct(
            col("missing_columns_list").alias("columns_with_null"),
            col("invalid_operation_flag").alias("invalid_operation")
        )
        
        # Convert the StructType to a JSON string
        patch_data_df_with_validation = patch_data_df.withColumn(
            "validation_description",
            to_json(validation_struct_col) # <--- CHANGE IS HERE
        ).drop("validation_struct") # Drop the intermediate struct column if it was created previously

        # Condition for missing required columns (if any required columns exist)
        missing_required_cols_condition = lit(False)
        if existing_required_columns:
            missing_required_cols_condition = reduce(
                lambda a, b: a | b,
                [col(c).isNull() for c in existing_required_columns]
            )

        # Condition for invalid operation (case-insensitive)
        invalid_operation_condition = (col("operation").isNull()) | (~lower(col("operation")).isin(allowed_operations))

        # A row is invalid if ANY required column is NULL OR the operation is invalid.
        invalid_df = patch_data_df_with_validation.filter(
            missing_required_cols_condition | invalid_operation_condition
        ).drop("missing_columns_list", "invalid_operation_flag")
        
        # No need to rename 'validation_struct' to 'validation_description' if we already created it as such
        # invalid_df = invalid_df.withColumnRenamed("validation_struct", "validation_description") # REMOVE THIS LINE
        
        valid_df = patch_data_df_with_validation.filter(
            ~missing_required_cols_condition & ~invalid_operation_condition
        ).drop("missing_columns_list", "invalid_operation_flag", "validation_description") # Also drop validation_description from valid_df

        return valid_df, invalid_df    
        
    def _initialize_business_event(self, namespace: str, message : str = None, exception : str = None, eventType = "validation" , sourceFilePath = None, targetFilePath = None)-> dict:
        """
        Creates a new business event row for failed patch file processing.  
        This function is called when there is an error in processing the patch files.
        It inserts a record into the Business events table with details about the error.
        """
        business_events_row  =   self.business_events_ingestion_service.create_new_business_event_row(
            id                      =   str(uuid.uuid4())
            , activityName          =   C.IMAGING_PATCH_FILE_NOTEBOOK
            , targetTableName       =   C.METADATA_TABLE_NAME 
            , targetFilePath        =   targetFilePath
            , sourceLakehouseName   =   f"{self.lakehouse_name}"
            , targetLakehouseName   =   f"{self.lakehouse_name}" 
            , sourceFilePath        =   sourceFilePath 
            , runId                 =   self.pipeline_run_id
            , severity              =   GC.ERROR
            , eventType             =   eventType
            , message               =   message
            , exception             =   exception
        )
        return business_events_row
            

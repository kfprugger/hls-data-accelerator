# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class to orchestrate metadata extraction
"""

import os
import ast
import json, uuid
from typing import Callable
from pyspark.sql import SparkSession, DataFrame, functions as F
from pyspark.sql.functions import col, from_json, lit
from pyspark.sql.types import StringType
from datetime import datetime
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.metadata_extractor import extract_metadata
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

class MetadataExtractionOrchestrator(BaseRunnableService):
    """
    Class used to orchestrate metadata extraction process
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
        The setup method for initializing the MetadataExtraction variables
        """
        self.lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
    
        self.business_events_ingestion_service = BusinessEventsIngestion(
            spark = self.spark,
            workspace_name = self.workspace_name,
            one_lake_endpoint = self.one_lake_endpoint,
            lakehouse_name = self.admin_lakehouse_name,
            solution_name = self.solution_name,
            parameter_service = self.parameter_service
            )

        try:
            self.lakehouse_files_root_path = FolderPath.get_fabric_files_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.lakehouse_name
            )
            
            self.ingestion_pattern = int(self.parameter_service.get_activity_config_value(GC.INGESTION_PATTERN_KEY, C.IngestionPattern.INGEST.value))
             
            if self.ingestion_pattern == C.IngestionPattern.INVENTORY.value:
                self.base_source_path = self.parameter_service.get_activity_config_value(GC.INVENTORY_SOURCE_PATH_KEY,
                                                   os.path.join(self.lakehouse_files_root_path, GC.INVENTORY_FOLDER, GC.MEDICAL_IMAGING_FOLDER, GC.DICOM_FOLDER))
            elif self.ingestion_pattern == C.IngestionPattern.BYOS.value:
                self.base_source_path = self.parameter_service.get_activity_config_value(GC.EXTERNAL_SOURCE_PATH_KEY,
                                                   os.path.join(self.lakehouse_files_root_path, GC.EXTERNAL_FOLDER, GC.MEDICAL_IMAGING_FOLDER, GC.DICOM_FOLDER))
            else:
                self.base_source_path = self.parameter_service.get_activity_config_value(GC.PROCESS_SOURCE_PATH_KEY,
                                                   os.path.join(self.lakehouse_files_root_path, GC.PROCESS_FOLDER, GC.MEDICAL_IMAGING_FOLDER, GC.DICOM_FOLDER))
            
            self.inventory_folder_name = self.parameter_service.get_activity_config_value(GC.INVENTORY_FOLDER_NAME_KEY, C.DEFAULT_INVENTORY_FOLDER_NAME)
            self.namespace = self.parameter_service.get_activity_config_value(GC.NAMESPACE_KEY, None)
            
            self.failed_files_path = os.path.join(
                self.lakehouse_files_root_path, 
                C.FAILED_FILES_FOLDER,             
                GC.MEDICAL_IMAGING_FOLDER, 
                GC.DICOM_FOLDER
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
            
            self.table_schema_file_path = self.parameter_service.get_foundation_config_value(
                GC.IMAGING_TABLE_SCHEMA_PATH_KEY,
                f"{self.config_files_root_path}/{GC.DEFAULT_DICOM_CONFIGS_PATH}/{C.DICOM_TABLES_SCHEMA_FILE_NAME}"
            )
            
            self.table_schema = json.loads(
                self.spark.sparkContext.wholeTextFiles(
                    self.table_schema_file_path
                ).collect()[0][1])

            self.regular_field_by_name, self.complex_field_by_name  = Utils.get_fields_by_keys(self.table_schema, 
                                                                                C.METADATA_TABLE_NAME,
                                                                                C.ME_TRANSFORMATION_COLUMNS) 
                
            self.base_checkpoint_path = self.parameter_service.get_activity_config_value(
                GC.BASE_CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                    root_path=self.config_files_root_path,
                    checkpoint_folder_name=f"{GC.MEDICAL_IMAGING_CONFIG_FOLDER}/{C.METADATA_EXTRACT_CHECKPOINT_FOLDER}"
                )
            )
            
            self.checkpoint_path = Utils.get_chkpt_path_based_on_source(self.base_checkpoint_path, self.base_source_path)
            
            self.is_byos_enabled = (self.ingestion_pattern == C.IngestionPattern.BYOS.value or 
                                    self.ingestion_pattern == C.IngestionPattern.INVENTORY.value)
            self.move_failed_files = CommonUtils.to_bool(self.parameter_service.get_activity_config_value(GC.MOVE_FAILED_FILES_KEY, not self.is_byos_enabled))
            self.compression_enabled = CommonUtils.to_bool(self.parameter_service.get_activity_config_value(GC.COMPRESSION_ENABLED_KEY, not self.is_byos_enabled))
            self.max_files_per_trigger = int(self.parameter_service.get_activity_config_value(GC.MAX_FILES_PER_TRIGGER_KEY, C.ME_MAX_FILES_PER_TRIGGER))
            self.max_bytes_per_trigger = int(self.parameter_service.get_activity_config_value(GC.MAX_BYTES_PER_TRIGGER_KEY, C.ME_MAX_BYTES_PER_TRIGGER))
            
            self.mssparkutils_client.fs_mount(
                self.base_source_path, 
                C.META_EXTRACT_MOUNT_LOCATION, 
                {"fileCacheTimeout": C.MOUNT_FILE_CACHE_TIMEOUT, "timeout": C.MOUNT_TIMEOUT})
            self.source_mount_path = self.mssparkutils_client.fs_get_mount_path(C.META_EXTRACT_MOUNT_LOCATION)
        
            if self.compression_enabled:
                self.spark.conf.set("spark.sql.files.ignoreMissingFiles", "true")
                self._file_compressor = FileCompressor(self.spark, self.base_source_path, self.source_mount_path)
            
            self.retries = int(self.parameter_service.get_activity_config_value(GC.NUM_RETRIES_KEY, C.FAILED_NUM_RETRIES))
            
            self.azure_blob_storage_inventory = CommonUtils.to_bool(self.parameter_service.get_activity_config_value(GC.AZURE_BLOB_STORAGE_INVENTORY_KEY, True))
            self.rows_per_partition = int(self.parameter_service.get_activity_config_value(GC.ROWS_PER_PARTITION_KEY, C.ME_DEFAULT_ROWS_PER_PARTITION))

            self.dicom_extract_lib_params = ast.literal_eval(self.parameter_service.get_activity_config_value(GC.DICOM_EXTRACT_LIB_PARAMS_KEY, C.DICOM_EXTRACT_LIB_PARAMS))
            self.stop_before_pixels = bool(self.dicom_extract_lib_params.get(C.STOP_BEFORE_PIXELS_KEY))
            self.suppress_validation_tags = bool(self.dicom_extract_lib_params.get(C.SUPPRESS_VALIDATION_TAGS_KEY))
        except Exception as ex:
            self._logger.error(message=str(ex))

            # Insert a row into Business Events table
            business_events_row_init_failed = self.business_events_ingestion_service.create_new_business_event_row(
                id =str(uuid.uuid4())
                , activityName =    C.IMAGING_NOTEBOOK_ME
                , sourceLakehouseName= f"{self.lakehouse_name}"
                , targetLakehouseName= f"{self.lakehouse_name}" 
                , runId =           self.pipeline_run_id
                , severity =        GC.ERROR
                , eventType=        C.BE_EVENT_TYPE_ME_INIT_FAILED
                , message=          str(ex)   
                , exception=        str(ex)                
            )
            self.business_events_ingestion_service.insert_business_events([business_events_row_init_failed])            
            raise 
    
    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.file,
            sourcePath=self.base_source_path,
            sourceLakehouseName= self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("id"),
            targetType=ExecutionDataType.deltaTable,
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("id"),
            targetPath=self.target_table_path
        )
    
    def _get_internal_activity_name(self) -> str:
        return GC.IMAGING_METADATA_EXTRACTION_ACTIVITY_NAME
    
    def _execute(self, **kwargs) -> None:
        """
        Executes the Process function to start the MetadataExtraction
        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.        
        """
        self.process()
          
    def process(self):
        """
        This method is used to process dicom files present inside the folder structure as defined by source_path
        and save the metadata output into delta table.

        """         
        for namespace in Utils.get_namespaces(self.mssparkutils_client, self.base_source_path, self.namespace):
            source_path = os.path.join(self.base_source_path, namespace)
            self.inventory_path = os.path.join(self.base_source_path, namespace, self.inventory_folder_name)
            checkpoint_path = os.path.join(self.checkpoint_path, namespace)
            
            self._logger.info(LC.PROCESSING_STATE_INFO_MSG.format(
                state= C.STATE_STARTED, 
                process_name=C.METADATA_EXTRACTION_PROCESS_NAME, 
                timestamp=datetime.now(), 
                dcm_files_path=source_path))
        
            if self.ingestion_pattern == C.IngestionPattern.INVENTORY.value:
                df_stream = Utils.read_files_metadata_from_inventory(
                    spark= self.spark,
                    files_to_process_path=source_path,
                    inventory_files_path=self.inventory_path,
                    azure_blob_storage_inventory= self.azure_blob_storage_inventory,
                    max_files_per_trigger=self.max_files_per_trigger,
                    max_bytes_per_trigger= self.max_bytes_per_trigger
                )
            else:
                df_stream = Utils.read_files_to_df_stream(
                spark=self.spark, 
                files_to_process_path=source_path, 
                max_files_per_trigger=self.max_files_per_trigger)
        
            self.spark.sparkContext.setJobGroup(f"{self.__class__.__module__}.{self.__class__.__qualname__}", "Processing DICOM files")
            query = (df_stream.writeStream.format("delta")
                .trigger(availableNow=True)
                .option("checkpointLocation", checkpoint_path)
                .foreachBatch(lambda df, epoch_id: self._process_dcm_files(df, self.retries, namespace))
                .start())
 
            query.awaitTermination()
            
            self._logger.info(LC.PROCESSING_STATE_INFO_MSG.format(
                state= C.STATE_COMPLETED, 
                process_name=C.METADATA_EXTRACTION_PROCESS_NAME, 
                timestamp=datetime.now(), 
                dcm_files_path=source_path))
        
        if self.compression_enabled:
            self.spark.conf.set("spark.sql.files.ignoreMissingFiles", "false")
        if self.source_mount_path is not None:
            self.mssparkutils_client.fs_unmount(C.META_EXTRACT_MOUNT_LOCATION)
      
    def _process_dcm_files(self, df:DataFrame, num_retries: int, namespace: str):
        
        """
        This method is used recursively to process dcm files until either 
        we exceed number of retries or do not have any failed files.

        Args:
            df (dataframe): contains dcm files content and file path
            num_retries (int): number of retries
            namespace (str): namespace/source system name
        """  

        if self.ingestion_pattern == C.IngestionPattern.INVENTORY.value:
            if not df.isEmpty():
                # Updated regex (supports nested folders)
                pattern = self.inventory_path + r"[\\/].*?(\d{4}[\\/]\d{2}[\\/]\d{2})"
                                
                # Extract date from file path
                df = df.withColumn(
                    "inventory_file_date",
                    F.regexp_extract(F.col(C.INVENTORY_FILE_PATH_COLUMN_NAME), pattern, 1)
                )

                # Convert to timestamp
                df = df.withColumn(
                    "inventory_file_date",
                    F.to_timestamp("inventory_file_date", "yyyy/MM/dd")
                )

                # Validate → exactly ONE unique date must exist                        
                inventory_file_max_date_row = df.select(F.max("inventory_file_date").alias("inventory_file_max_date")).first()
                
                inventory_file_max_date = inventory_file_max_date_row["inventory_file_max_date"]
                
                if inventory_file_max_date is None:
                    raise ValueError(LC.INVENTORY_FILES_NOT_ORGANIZED_ERR_MSG.format(inventory_path=self.inventory_path))
                
                # Filter dataset (incremental logic)
                df = df.filter(F.col("inventory_file_date") >= F.lit(inventory_file_max_date))
                df = df.drop("inventory_file_date")
                
                max_processed_date = Utils.get_max_date_col_val(spark=self.spark, 
                                                                delta_table_path=os.path.join(self.target_table_path, C.METADATA_TABLE_NAME), 
                                                                col_name=C.SOURCE_MODIFIED_COLUMN_NAME,
                                                                namespace=namespace,
                                                                current_dataframe=df)
            
                df = df.filter(col(C.SOURCE_MODIFIED_COLUMN_NAME) > max_processed_date)
                self._logger.info(LC.INVENTORY_NS_MAXDATE_INFO_MSG.format(
                namespace=namespace,
                max_processed_date=max_processed_date))
                
                        
        self.spark.sparkContext.setJobGroup(
            f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            f"Counting total DICOM files for namespace: {namespace}"
        )
        
        total_count = df.count()
        if(num_retries < 0):
            #moving files for which processing failed to failed folder
            if df and total_count > 0 and self.move_failed_files:
                try:
                    for row in df.collect():
                        Utils.move_files(row.filePath, 
                                         os.path.join(self.failed_files_path, 
                                                      namespace, 
                                                      Utils.get_current_date_in_utc(), 
                                                      os.path.basename(row.filePath))
                                         , self.mssparkutils_client, True)
                except Exception as e:
                    self._logger.error(LC.FAILED_FILES_NOT_MOVED_ERR_MSG.format(
                        error_msg=str(e)
                    ))
                    
                    # call business events, problem in moving files for which processing failed to failed folder
                    business_events_row__failed_files_not_moved = self.business_events_ingestion_service.create_new_business_event_row(
                        id =str(uuid.uuid4())
                        , activityName =    C.IMAGING_NOTEBOOK_ME
                        , targetFilePath=   os.path.join(self.failed_files_path, namespace, Utils.get_current_date_in_utc(),os.path.basename(row.filePath))
                        , sourceLakehouseName= f"{self.lakehouse_name}"
                        , targetLakehouseName= f"{self.lakehouse_name}" 
                        , sourceFilePath=   row.filePath
                        , runId =           self.pipeline_run_id    
                        , severity =        GC.ERROR
                        , eventType=        C.BE_EVENT_TYPE_FAILED_FILES_NOT_MOVED
                        , message=          LC.FAILED_FILES_NOT_MOVED_ERR_MSG.format(error_msg=str(e))
                        , exception=        str(e)                    
                    )
                    self.business_events_ingestion_service.insert_business_events([business_events_row__failed_files_not_moved])
                     
            return
        
        if total_count > 0:
            self._logger.info(LC.RETRY_INFO_MSG.format(
                process_name=C.METADATA_EXTRACTION_PROCESS_NAME, 
                retry_attempt=abs(num_retries-self.retries)+1))
            
            if self.ingestion_pattern == C.IngestionPattern.INVENTORY.value:
                df = Utils.repartition_df(df, total_count, self.rows_per_partition)
            
            df = df.withColumn(C.EXTRACTED_METADATA_ATTR_NAME, extract_metadata(col(C.FILE_PATH_COLUMN_NAME), lit(self.base_source_path), lit(self.source_mount_path),lit(self.stop_before_pixels),lit(self.suppress_validation_tags))).cache()
            
            df_success = df.filter(col(f"{C.EXTRACTED_METADATA_ATTR_NAME}.{C.ERROR_ATTR_NAME}").isNull())
            
            df_failed = df.filter(col(f"{C.EXTRACTED_METADATA_ATTR_NAME}.{C.ERROR_ATTR_NAME}").isNotNull()).cache()
            
            try:
                self.spark.sparkContext.setJobGroup(f"{self.__class__.__module__}.{self.__class__.__qualname__}", f"Counting failed rows for namespace: {namespace}")
                failed_rows = df_failed.collect()
                failed_count = len(failed_rows)
                success_count = total_count - failed_count
            except ValueError as e:
                self._logger.error(
                    LC.FAILED_FILES_INFO_COLLECT_ERR_MSG.format(
                        error_msg=str(e)
                    )
                )
                failed_rows = []
                success_count = df_success.count()
                failed_count = total_count - success_count
                # Insert record into Business events table. Problem in processing statistics of the failed and success count.
                business_events_row_count_collection = self.business_events_ingestion_service.create_new_business_event_row(
                    id =str(uuid.uuid4())
                    , activityName =    C.IMAGING_NOTEBOOK_ME
                    , targetTableName = C.METADATA_TABLE_NAME # ImagingDicom table
                    , sourceLakehouseName= f"{self.lakehouse_name}"
                    , targetLakehouseName= f"{self.lakehouse_name}" 
                    , runId =           self.pipeline_run_id  
                    , severity =        GC.ERROR
                    , eventType=        C.BE_EVENT_TYPE_FAILED_FILES_INFO_COLLECT
                    , message=          LC.FAILED_FILES_INFO_COLLECT_ERR_MSG.format(error_msg=str(e))   
                    , exception=        str(e)                    
                )
                self.business_events_ingestion_service.insert_business_events([business_events_row_count_collection])
        
                
                    
            if self.compression_enabled :
                df_success = self._file_compressor.run_compression_from_df(df_success, success_count)           
            
            if success_count > 0:
                df_success = self._transform_metadata_to_df(df_success, namespace)    
                append_to_delta_table_using_path(
                    df_to_process=df_success,
                    delta_table_path=os.path.join(self.target_table_path, C.METADATA_TABLE_NAME),
                    logger=self._logger,
                    collect_metrics_fn = self.collect_target_delta_table_operation_summary_metrics
                    )
                
            business_events = []
            non_retriable_failed_files_count = 0
            for row in failed_rows:
                error_mssg=row.metadataExtracted[C.ERROR_ATTR_NAME]
                self._logger.error(LC.PROCESSING_FAILED_ERR_MSG.format(
                        process_name= C.METADATA_EXTRACTION_PROCESS_NAME, 
                        dcm_file_name= os.path.basename(row.filePath), 
                        error_mssg=error_mssg))
                
                # Insert record into Business events table.
                business_events_row_filed_rows = self.business_events_ingestion_service.create_new_business_event_row(
                    id =str(uuid.uuid4())
                    , activityName =    C.IMAGING_NOTEBOOK_ME
                    , targetTableName = C.METADATA_TABLE_NAME # Imaging dicom table
                    , sourceLakehouseName= f"{self.lakehouse_name}"
                    , targetLakehouseName= f"{self.lakehouse_name}" 
                    , sourceFilePath= row.filePath
                    , runId =           self.pipeline_run_id  
                    , severity =        GC.ERROR
                    , eventType=        C.BE_EVENT_TYPE_FAILED_FILES
                    , message= LC.PROCESSING_FAILED_ERR_MSG.format( process_name= C.METADATA_EXTRACTION_PROCESS_NAME, dcm_file_name= os.path.basename(row.filePath), error_mssg=error_mssg)   
                    , exception = error_mssg
                )
                business_events.append(business_events_row_filed_rows)               
                  
                if error_mssg in C.NON_RETRIABLE_ERRORS:
                    non_retriable_failed_files_count += 1
                    if self.move_failed_files:
                        try:
                            Utils.move_files(row.filePath, 
                                             os.path.join(self.failed_files_path, 
                                                          namespace, 
                                                          Utils.get_current_date_in_utc(), 
                                                          os.path.basename(row.filePath)), 
                                             self.mssparkutils_client, True)
                        except Exception as e:
                            self._logger.error(LC.FAILED_FILES_NOT_MOVED_ERR_MSG.format(
                                error_msg=str(e)
                            ))
                            # Insert record into Business events table. Problem in processing of the failed files and error is NON_RETRIABLE_ERRORS                            
                            business_events_row_except = self.business_events_ingestion_service.create_new_business_event_row(
                                id =str(uuid.uuid4())
                                , activityName =    C.IMAGING_NOTEBOOK_ME
                                , targetFilePath=   os.path.join(self.failed_files_path, namespace, Utils.get_current_date_in_utc(), os.path.basename(row.filePath))
                                , sourceLakehouseName= f"{self.lakehouse_name}"
                                , targetLakehouseName= f"{self.lakehouse_name}" 
                                , sourceFilePath= row.filePath  # we are processing failed files here, so will point towards failed files folder as source
                                , runId =           self.pipeline_run_id
                                , severity =        GC.ERROR
                                , eventType=        C.BE_EVENT_TYPE_FAILED_FILES_NON_RETRIABLE_ERRORS
                                , message=          LC.FAILED_FILES_NOT_MOVED_ERR_MSG.format(error_msg=str(e))
                                , exception=        str(e)
                                
                            )
                            business_events.append(business_events_row_except)                            
            
            #collecting the business events for all the failed files and inserting them into the business events table once
            if len(business_events) > 0:
                self.business_events_ingestion_service.insert_business_events(business_events)                      
            
            retriable_failed_files_count = failed_count-non_retriable_failed_files_count
            self._logger.info(LC.PROCESSING_STATUS_INFO_MSG.format(
                total_dcm_files=total_count,
                success_files_count=success_count,
                failed_files_count=failed_count,
                non_retriable_failed_files_count=non_retriable_failed_files_count,
                retriable_failed_files_count=retriable_failed_files_count
            ))

            # Collect the execution metrics for logging purposes
            self.execution_metrics_collector.accumulate(
                accumulator_activity_id=self.get_execution_metrics_accumulator_activity_id(),
                metrics={                    
                    "numSourceFiles": total_count,                    
                    "activityAttributes": {"successCount": success_count,
                                           "failedCount": failed_count,
                                           "retriableFailedCount": retriable_failed_files_count,
                                           "nonRetriableFailedCount": non_retriable_failed_files_count}
                }
            )
            
            if retriable_failed_files_count:
                retriable_failed_files = df_failed.filter(~col(f"{C.EXTRACTED_METADATA_ATTR_NAME}.{C.ERROR_ATTR_NAME}").isin(C.NON_RETRIABLE_ERRORS)).cache()
                self._process_dcm_files(
                    retriable_failed_files.drop(C.EXTRACTED_METADATA_ATTR_NAME),
                    num_retries-1,
                    namespace)
        
    def _transform_metadata_to_df (self, meta_store_df: DataFrame, namespace: str) -> DataFrame:
        """
        This method is used to transform metadata dictionary to data_frame and return the data frame.

        Args:
            meta_store_df (DataFrame): The DataFrame containing the metadata dictionary. 
            namespace (str): namespace/source system name          

        Returns:
            DataFrame: The transformed metadata DataFrame.
        """
        for tag_key, tag_info in self.regular_field_by_name.items():
            meta_store_df = meta_store_df.withColumn(tag_info.metadata['columnName'], col(f'{C.EXTRACTED_METADATA_ATTR_NAME}.{tag_key.lower()}').cast(tag_info.dataType))

        for tag_key, tag_info in self.complex_field_by_name.items():
            meta_store_df = meta_store_df.withColumn(f"{tag_info.metadata['columnName']}_string", col(f"{C.EXTRACTED_METADATA_ATTR_NAME}.{tag_key.lower()}")) \
                                        .withColumn(tag_info.metadata['columnName'], from_json(col(f'{C.EXTRACTED_METADATA_ATTR_NAME}.{tag_key.lower()}'), tag_info.dataType))

        meta_store_df = meta_store_df.drop(C.EXTRACTED_METADATA_ATTR_NAME)
        meta_store_df = meta_store_df.withColumn(C.SOURCE_SYSTEM_COLUMN_NAME, lit(namespace)) \
                                    .withColumn(C.OPERATION, lit(None).cast(StringType()))
        return meta_store_df
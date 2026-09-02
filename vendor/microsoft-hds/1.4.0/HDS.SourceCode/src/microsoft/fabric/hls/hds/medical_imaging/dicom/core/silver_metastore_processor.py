# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
This module contains a class responsible for orchestrating the processing and merging of DICOM metadata from the ImagingDicom table into a metastore Delta table within HDS SILVER.
"""
import json, os, uuid
from datetime import datetime
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.window import Window
from pyspark.sql.types import *
from pyspark.sql.functions import *
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.constants import ImagingStudyConstants as C
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.structured_stream.delta_table_stream_reader import DeltaTableStreamReader
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType
from microsoft.fabric.hls.hds.utils.dataframe_utils import update_unique_to_delta_managed, upsert_unique_to_delta_managed, find_managed_delta_table_using_path
from microsoft.fabric.hls.hds.flatten.normalization.normalization_manager import FlattenNormalization
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants as FC

class MetastoreProcessor(BaseRunnableService):
    """
    MetastoreProcessor is a service class responsible for orchestrating the processing and 
    merging of DICOM metadata from the ImagingDicom table into a metastore Delta table in HDS SILVER. 
    It supports both standard DICOM and patch-based processing modes, handling streaming ingestion, 
    transformation, deduplication, and upsert operations.
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
        The setup method for initializing the Silver MetastoreProcessor variables
        """
        self.lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
        
        self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            solution_name=self.solution_name
        )
        
        self.config_file_path = self.parameter_service.get_activity_config_value(
            GC.DICOM_TO_FHIR_CONFIG_PATH_KEY,
            f"{self.config_files_root_path}/{GC.DEFAULT_DICOM_CONFIGS_PATH}/{C.DICOM_TO_FHIR_MAPPING_FILE_NAME}"
        )

        self.mapping_config = json.loads(
            self.spark.sparkContext.wholeTextFiles(
                self.config_file_path
            ).collect()[0][1]
        )
        
        self.process_type = self.parameter_service.get_activity_config_value(
            GC.DICOM_PATCH_PROCESS_TYPE_KEY,
            C.DEFAULT_DICOM_PATCH_PROCESS_TYPE
        )
        
        checkpoint_path = self.parameter_service.get_activity_config_value(
            GC.CHECKPOINT_PATH_KEY,
            FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                root_path=self.config_files_root_path,
                checkpoint_folder_name=f"{GC.MEDICAL_IMAGING_CONFIG_FOLDER}/{C.IMAGING_META_STORE}")
        )
                
        self.checkpoint_process_type_path = os.path.join(
            checkpoint_path,
            self.process_type.lower()
        )
        
        self.lakehouse_files_root_path = FolderPath.get_fabric_files_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.lakehouse_name
        )
        
        self.imagingdicom_table_path = self.parameter_service.get_foundation_config_value(
            GC.IMAGING_DELTA_TABLE_PATH_KEY,
            FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.lakehouse_name
            )
        )
                
        self.metastore_table_path = self.parameter_service.get_activity_config_value(
                GC.TARGET_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.lakehouse_name
                ),
            )
          
        self.max_files_per_trigger = int(self.parameter_service.get_activity_config_value(
                GC.MAX_FILES_PER_TRIGGER_KEY, C.ME_MAX_FILES_PER_TRIGGER))
        self.max_bytes_per_trigger = int(self.parameter_service.get_activity_config_value(
                GC.MAX_BYTES_PER_TRIGGER_KEY, C.ME_MAX_BYTES_PER_TRIGGER))
        
        self.business_events_ingestion_service = BusinessEventsIngestion(
            spark = self.spark,
            workspace_name = self.workspace_name,
            one_lake_endpoint = self.one_lake_endpoint,
            lakehouse_name = self.admin_lakehouse_name,
            solution_name = self.solution_name,
            parameter_service = self.parameter_service
        )
        
        def __check_udf_registered(udf_name: str) -> bool:
            """
            Check if UDF is registered in spark session
            """
            # Use SQL to check if the UDF exists (works if it's globally registered)
            try:
                result = self.spark.sql(f"SHOW FUNCTIONS LIKE '{udf_name}'").collect()
                return len(result) > 0
            except Exception as e:
                print(f"Error checking UDF registration: {e}")
            return False
        
        if not __check_udf_registered(FC.NORM_UDF_NORM_DATE):
            self.spark.udf.register(
                FC.NORM_UDF_NORM_DATE,
                FlattenNormalization.normalize_date,
                TimestampType(),
            )
    
    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourcePath=self.imagingdicom_table_path,
            sourceLakehouseName= self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("id"),
            targetType=ExecutionDataType.deltaTable,
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.lakehouse_name).get("id"),
            targetPath =self.metastore_table_path
        )
    
    def _get_internal_activity_name(self) -> str:
        return GC.IMAGING_METASTORE_PROCESSING_ACTIVITY_NAME
    
    def _execute(self, **kwargs) -> None:
        """ This method is used to execute the metastore merge process """      
        self._start_metastore_merge()
            
    def _start_metastore_merge(self):
        """
        This method is used to execute the metastore merge process        
        """        
        try:
            stream_reader = DeltaTableStreamReader(self.spark,
                                    maxFilesPerTrigger= self.max_files_per_trigger,
                                    maxBytesPerTrigger= self.max_bytes_per_trigger)            
            df : DataFrame = stream_reader.set_up_streaming(
                f"{self.imagingdicom_table_path}/{C.METADATA_TABLE_NAME}"
            )
            query = (df.writeStream.format("delta")
                .trigger(availableNow=True)
                .option("checkpointLocation", self.checkpoint_process_type_path)
                .foreachBatch(lambda df, epoch_id: self._process(df,epoch_id))
                .start())
        
            query.awaitTermination()
        except Exception as e:
            self._logger.error(
                LC.SPARK_STREAM_READ_ERR_MSG.format(
                    table_path = self.imagingdicom_table_path,
                    error_msg = str(e)
                )
            )            
            # Insert a row into Business Events table
            business_events_failed_row = self.business_events_ingestion_service.create_new_business_event_row(
                id =str(uuid.uuid4())
                , activityName =    C.SILVER_IMAGING_METASTORE_SERVICE
                , targetFilePath=   self.metastore_table_path
                , sourceTableName = C.METADATA_TABLE_NAME
                , sourceLakehouseName= f"{self.lakehouse_name}"
                , targetLakehouseName= f"{self.lakehouse_name}" 
                , sourceFilePath=   f"{self.imagingdicom_table_path}/{C.METADATA_TABLE_NAME}"  
                , runId =           self.pipeline_run_id
                , severity =        GC.ERROR
                , eventType=        C.BE_EVENT_TYPE_D2F_EXECUTE_NDJSON_GENERATION
                , message=   LC.SPARK_STREAM_READ_ERR_MSG.format(table_path = self.imagingdicom_table_path,error_msg = str(e))
                , exception= str(e)                
            )
            self.business_events_ingestion_service.insert_business_events([business_events_failed_row])
           
            raise
    
    def _process(self, df: DataFrame, epoch_id: str) -> None:        
        
        self._logger.info(LC.IMAGING_METASTORE_PROCESSING_STATE_INFO_MSG.format(
            process_name = C.SILVER_METASTORE_PROCESS_NAME,
            state = C.STATE_STARTED,
            timestamp = datetime.now(),
            process_type = self.process_type
        ))     
        self.spark.conf.set("spark.sql.mapKeyDedupPolicy", "LAST_WIN")
        
        if self.process_type and self.process_type.lower() == C.ProcessType.DICOM.value:
            self._process_dicom(df)
        elif self.process_type and self.process_type.lower() ==  C.ProcessType.PATCH.value:
            self._process_patch(df)
        else:
            self._logger.error(
                LC.IMAGING_INVALID_PROCESS_TYPE_ERR_MSG.format(process_type = self.process_type)
            )
            raise ValueError(LC.IMAGING_INVALID_PROCESS_TYPE_ERR_MSG.format(
                process_type = self.process_type
            ))
           
        self._logger.info(LC.IMAGING_METASTORE_PROCESSING_STATE_INFO_MSG.format(
                    process_name = C.SILVER_METASTORE_PROCESS_NAME,
                    state = C.STATE_COMPLETED,
                    timestamp = datetime.now(),
                    process_type = self.process_type
                ))
    
    def _process_dicom(self, df: DataFrame) -> None:
        """
        This method processes the DICOM data and generates ndjson files for fhir resource data from dicom tags
        Args:
            df (DataFrame): The input DataFrame containing DICOM metadata.
        """
        df = df.filter(col(C.OPERATION).isNull())
        if df.isEmpty():
            self._logger.info(LC.NO_NEW_DATA_FOUND_WITH_OPERATION_INFO_MSG.format(
                operation = C.ProcessType.DICOM.value.upper()))
            return
        df = df.withColumn(C.METASTORE_DELETED_COLUMN_NAME, lit(False))
        df = self._generate_id(df).drop(C.OPERATION)
        self._merge_metastore_data(df, C.SOURCE_MODIFIED_COLUMN_NAME, C.ProcessType.DICOM.value)

    def _process_patch(self, df: DataFrame) -> None:
        """Processes DICOM metadata DataFrame to handle PATCH and DELETE operations.
        This method filters the input DataFrame for PATCH and DELETE operations, processes the corresponding records, 
        and merges the results into the metastore.
        """        
        patch_df = df.filter(col(C.OPERATION) == lit(C.PATCH_OPERATION.lower()))
        if patch_df.isEmpty():
            self._logger.info(LC.NO_NEW_DATA_FOUND_WITH_OPERATION_INFO_MSG.format(
                operation = C.PATCH_OPERATION.upper()))        
        else:
            metastore_df = self._pre_process_patch(patch_df)
            self._merge_metastore_data(metastore_df, C.SOURCE_MODIFIED_COLUMN_NAME, C.PATCH_OPERATION)
        
        delete_df = df.filter(col(C.OPERATION) == lit(C.DELETE_OPERATION.lower()))
        if delete_df.isEmpty():
            self._logger.info(LC.NO_NEW_DATA_FOUND_WITH_OPERATION_INFO_MSG.format(
                operation = C.DELETE_OPERATION.upper()))
        else:
            metastore_df = self._pre_process_delete(delete_df)
            self._merge_metastore_data(metastore_df, C.SOURCE_MODIFIED_COLUMN_NAME, C.DELETE_OPERATION)
    
    def _merge_metastore_data(self, df: DataFrame, modified_on_column : str, operation: str) -> None:
        """
        This method is used to transform the data to the target lakehouse.

        """   
        try: 
            self._logger.info(
                LC.IMAGING_METASTORE_SAVE_STATE_INFO_MSG.format(
                    state = C.STATE_STARTED,
                    process_type = self.process_type,
                    operation = operation))      
            
            if self.process_type and self.process_type.lower() == C.ProcessType.DICOM.value:
                upsert_unique_to_delta_managed(spark_session=self.spark,
                                                        data_manager_logger=self._logger,
                                                        df_to_process=df,
                                                        unique_columns=C.IMAGING_META_STORE_UNIQUE_COLUMNS,
                                                        delta_table_path=f"{self.metastore_table_path}/{C.IMAGING_META_STORE}",
                                                        source_modified_on_column= modified_on_column,
                                                        collect_metrics_fn =self.collect_target_delta_table_operation_summary_metrics
                                                        )                    
            elif self.process_type and self.process_type.lower() ==  C.ProcessType.PATCH.value:                
                update_unique_to_delta_managed(spark_session=self.spark,
                                                        data_manager_logger=self._logger,
                                                        df_to_process=df,
                                                        unique_columns=C.IMAGING_META_STORE_UNIQUE_COLUMNS,
                                                        delta_table_path=f"{self.metastore_table_path}/{C.IMAGING_META_STORE}",
                                                        source_modified_on_column= modified_on_column,
                                                        collect_metrics_fn =self.collect_target_delta_table_operation_summary_metrics
                                                        )
           
            self._logger.info(
                LC.IMAGING_METASTORE_SAVE_STATE_INFO_MSG.format(
                    state = C.STATE_COMPLETED,
                    process_type = self.process_type,
                    operation = operation))
            
        except Exception as e:
            self._logger.error(
                LC.SAVING_RESOURCE_ERR_MSG.format(
                    table_path = self.metastore_table_path,
                    error_msg = str(e)
                )
            )            
            # Insert a row into Business Events table
            be_upsert_failed = self.business_events_ingestion_service.create_new_business_event_row(
                id =str(uuid.uuid4())
                , activityName =    C.SILVER_IMAGING_METASTORE_SERVICE
                , sourceLakehouseName= f"{self.lakehouse_name}"
                , targetLakehouseName= f"{self.lakehouse_name}" 
                , sourceTableName= C.METADATA_TABLE_NAME
                , targetTableName= C.IMAGING_META_STORE
                , runId =           self.pipeline_run_id
                , severity =        GC.ERROR
                , eventType=        C.BE_EVENT_TYPE_MS_UPSERT_FAILED
                , message=          str(e)   
                , exception=        str(e)                
            )
            self.business_events_ingestion_service.insert_business_events([be_upsert_failed])            
            raise
        
    def _generate_id(self, df : DataFrame)-> DataFrame:
        """
        This method is used to process the dataframe read from the source table.

        Args:
            df (DataFrame): The DataFrame containing the data from the source table.            

        Returns:
            DataFrame: The processed DataFrame.
        """        
        df = df[C.IMAGING_META_STORE_COLUMNS]
        
        # Read expression string ("calc") for field "id" from config mappings
        expr_str = ""
        if C.ID_COLUMN_NAME in self.mapping_config and C.CALC_FIELD in self.mapping_config[C.ID_COLUMN_NAME]:
            expr_str = f"{self.mapping_config[C.ID_COLUMN_NAME][C.CALC_FIELD]}"
        else:
            self._logger.error( 
                LC.CONFIG_MAPPING_ERROR_MSG.format(
                    config_file_path=self.config_file_path
                )
            )
            raise KeyError(LC.CONFIG_MAPPING_ERROR_MSG.format(
                config_file_path=self.config_file_path
            ))
        
        # Creating udf for normalize_resource_id() function for datatype compatibility. normalize_resource_id() accepts source_system as Union[str, None] instead of type column.
        df = df.withColumn(C.ID_COLUMN_NAME,  udf(
                lambda orig_id, source_system: FlattenNormalization.normalize_resource_id(f"{orig_id}", C.FHIR_IMAGING_STUDY_RES_NAME, f"{source_system}"),
                StringType()
            )(
                eval(expr_str).cast(StringType()),
                col(C.SOURCE_SYSTEM_COLUMN_NAME)
            )
        )       
        #renaming sourceSystem column to msftSourceSystem
        df = df.withColumnRenamed(C.SOURCE_SYSTEM_COLUMN_NAME, C.SILVER_SOURCE_SYSTEM_COLUMN_NAME) 
        self._logger.info(LC.IMAGING_METASTORE_ID_GENERATION_COMPLETED_INFO_MSG)
        return df
    
    def _pre_process_delete(self, df: DataFrame) -> DataFrame:
        """
        - The hierarchical join is an inner join: only existing metastore records that match the
            provided study (and optionally series/instance) will be produced for deletion.
        - The code treats null incremental series/sop UIDs as wildcards, allowing study-level or
            series-level deletes to expand to multiple metastore rows.
        """
        self._logger.info(
            LC.IMAGING_METASTORE_PRE_PROCESSING_STATE_INFO_MSG.format(
                operation="SOFT-DELETE",
                state= C.STATE_STARTED,
                timestamp=datetime.now()             
            )
        )
        
        # Records for all UIDs are present
        unique_ids_not_null_df = df.filter(
            col(C.STUDY_INSTANCE_UID).isNotNull() &
            col(C.SERIES_INSTANCE_UID).isNotNull() &
            col(C.SOP_INSTANCE_UID).isNotNull()
        ).select(
            col(C.STUDY_INSTANCE_UID),
            col(C.SERIES_INSTANCE_UID),
            col(C.SOP_INSTANCE_UID),
            col(C.SOURCE_SYSTEM_COLUMN_NAME).alias(C.SILVER_SOURCE_SYSTEM_COLUMN_NAME),
            col(C.SOURCE_MODIFIED_COLUMN_NAME),
            lit(True).alias(C.METASTORE_DELETED_COLUMN_NAME)
        )

        # Records for series/instance level delete (at least one UID is null)
        series_or_instance_null_df = df.filter(
            col(C.SERIES_INSTANCE_UID).isNull() |
            col(C.SOP_INSTANCE_UID).isNull()
        )

        # Records for series/instance level delete (at least one UID is null)
        if not series_or_instance_null_df.isEmpty():
            
            df_incremental =series_or_instance_null_df.select(
            col(C.STUDY_INSTANCE_UID).alias(C.INCR_STUDY_INSTANCE_UID),
            col(C.SERIES_INSTANCE_UID).alias(C.INCR_SERIES_INSTANCE_UID),
            col(C.SOP_INSTANCE_UID).alias(C.INCR_SOP_INSTANCE_UID),
            col(C.SOURCE_SYSTEM_COLUMN_NAME),         
            col(C.SOURCE_MODIFIED_COLUMN_NAME).alias(C.INCR_SOURCE_MODIFIED)
            )

            metastore_df = find_managed_delta_table_using_path(self.spark, 
                                                    f"{self.metastore_table_path}/{C.IMAGING_META_STORE}").toDF()\
                                    .drop(C.TAGS_METADATA_STRING,C.METADATA_COLUMN_NAME)

            # Joining with the full metastore DataFrame to find matching records with the incremental DataFrame using inner join, in case of study level delete, ignore matching series/instance ID's
            joined_df = metastore_df.join(
                df_incremental,
                (metastore_df[C.STUDY_INSTANCE_UID] == df_incremental[C.INCR_STUDY_INSTANCE_UID]) &
                (metastore_df[C.SILVER_SOURCE_SYSTEM_COLUMN_NAME] == df_incremental[C.SOURCE_SYSTEM_COLUMN_NAME]) &
                (
                    (df_incremental[C.INCR_SERIES_INSTANCE_UID].isNull() | (metastore_df[C.SERIES_INSTANCE_UID] == df_incremental[C.INCR_SERIES_INSTANCE_UID])) &
                    (df_incremental[C.INCR_SOP_INSTANCE_UID].isNull() | (metastore_df[C.SOP_INSTANCE_UID] == df_incremental[C.INCR_SOP_INSTANCE_UID]))
                ),
                how="inner"
            )
            
            final_consolidated_df = joined_df.select(
                col(C.STUDY_INSTANCE_UID),
                col(C.SERIES_INSTANCE_UID),
                col(C.SOP_INSTANCE_UID),
                col(C.SILVER_SOURCE_SYSTEM_COLUMN_NAME),
                col(C.INCR_SOURCE_MODIFIED).alias(C.SOURCE_MODIFIED_COLUMN_NAME),
                lit(True).alias(C.METASTORE_DELETED_COLUMN_NAME)  # Mark as deleted                
            )
                        
            # Union the two types of deletes
            final_consolidated_df = final_consolidated_df.unionByName(unique_ids_not_null_df)

        else:
          final_consolidated_df = unique_ids_not_null_df

        self._logger.info(
            LC.IMAGING_METASTORE_PRE_PROCESSING_STATE_INFO_MSG.format(
                operation="SOFT-DELETE",
                state= C.STATE_COMPLETED,
                timestamp=datetime.now()             
            )
        )
        return final_consolidated_df

    def _pre_process_patch(self, df: DataFrame) -> DataFrame:    
        """
        This method is used to pre-process the dataframe read from the source table.
        Processing steps
        - Explode the metadata into (tag, meta_entry) pairs so tags can be processed individually.
        - For each unique (studyInstanceUid, seriesInstanceUid, sopInstanceUid, sourceSystem, tag) keep only the most
            recent tag entry according to C.SOURCE_MODIFIED_COLUMN_NAME (row_number over a descending window).
        - Reconstruct an "incremental" per-identifier metadata map and incremental source-modified timestamp.
        - Inner-join the metastore and the incremental metadata on study UID and sourceSystem and, where provided,
            matching series and SOP UIDs; this produces matches that may be 0, 1 or >1 rows per incremental identifier.
        - If multiple matched metastore rows exist for the same identifying key (duplicates),
            - isolate the duplicate groups,
            - merge the existing metadata map and the incremental metadata map (map_concat) preferring incremental entries,
            - derive an effective_lastUpdated as the coalesced max of incremental and existing source-modified timestamps,
            - explode and re-deduplicate tags within each duplicate group by the effective_lastUpdated ordering,
            - rebuild a single merged metadata map per identifying key with the correct effective_lastUpdated.
        - For rows that had a single match, compute merged_metadata similarly (map_concat of existing and incremental),
            and compute effective_lastUpdated (coalesce of incremental and existing timestamps).
        - Union the processed unique and resolved-duplicate groups to form a single consolidated DataFrame.
        
        """        
        self._logger.info(
                LC.IMAGING_METASTORE_PRE_PROCESSING_STATE_INFO_MSG.format(
                    operation="PATCH",
                    state= C.STATE_STARTED,
                    timestamp=datetime.now()             
                )
            )
        
        IMAGING_DICOM_UNIQUE_COLUMNS = ['studyInstanceUid','seriesInstanceUid','sopInstanceUid', 'sourceSystem']
                
        df_exploded = df.select(
            *C.IMAGING_PATCH_META_STORE_COLUMNS,
            explode(C.METADATA_COLUMN_NAME).alias("tag", "meta_entry")
        ).drop(C.METADATA_COLUMN_NAME)
        
        window_spec_tag_incremental = Window.partitionBy(*IMAGING_DICOM_UNIQUE_COLUMNS, "tag").orderBy(col(C.SOURCE_MODIFIED_COLUMN_NAME).desc())

        df_latest_tags_incremental = df_exploded.withColumn("rn", row_number().over(window_spec_tag_incremental)).filter(col("rn") == 1).drop("rn")

        # Reconstruct consolidated incremental metadata
        incremental_df = df_latest_tags_incremental.groupBy(*IMAGING_DICOM_UNIQUE_COLUMNS).agg(
            map_from_entries(collect_list(struct(col("tag"), col("meta_entry")))).alias(C.INCR_METADATA),
            max(col(C.SOURCE_MODIFIED_COLUMN_NAME)).alias(C.INCR_SOURCE_MODIFIED)        
        ).select(
            col(C.STUDY_INSTANCE_UID).alias(C.INCR_STUDY_INSTANCE_UID),
            col(C.SERIES_INSTANCE_UID).alias(C.INCR_SERIES_INSTANCE_UID),
            col(C.SOP_INSTANCE_UID).alias(C.INCR_SOP_INSTANCE_UID),
            col(C.SOURCE_SYSTEM_COLUMN_NAME),
            C.INCR_METADATA,            
            C.INCR_SOURCE_MODIFIED)
        
        metastore_df = find_managed_delta_table_using_path(self.spark, 
                                                 f"{self.metastore_table_path}/{C.IMAGING_META_STORE}").toDF().drop(C.TAGS_METADATA_STRING)
                  
        joined_df = metastore_df.join(
            incremental_df,
            (metastore_df[C.STUDY_INSTANCE_UID] == incremental_df[C.INCR_STUDY_INSTANCE_UID]) &
            (metastore_df[C.SILVER_SOURCE_SYSTEM_COLUMN_NAME] == incremental_df[C.SOURCE_SYSTEM_COLUMN_NAME]) &
            (
                (incremental_df[C.INCR_SERIES_INSTANCE_UID].isNull() | (metastore_df[C.SERIES_INSTANCE_UID] == incremental_df[C.INCR_SERIES_INSTANCE_UID])) &
                (incremental_df[C.INCR_SOP_INSTANCE_UID].isNull() | (metastore_df[C.SOP_INSTANCE_UID] == incremental_df[C.INCR_SOP_INSTANCE_UID]))
            ),
            how="inner"
        )            
        # Group by the identifying columns and count occurrences
        duplicate_check_df = joined_df.groupBy(*IMAGING_DICOM_UNIQUE_COLUMNS).count()

        duplicate_ids = duplicate_check_df.filter(col("count") > 1).select(*IMAGING_DICOM_UNIQUE_COLUMNS)
        
        if not duplicate_ids.isEmpty():
            
            # Join back to joined_df to get the full duplicate records
            duplicate_records_df = joined_df.join(duplicate_ids, on=IMAGING_DICOM_UNIQUE_COLUMNS, how="inner")
    
            # Get the unique records (those not in the duplicate_ids list)
            unique_records_df = joined_df.join(duplicate_ids, on=IMAGING_DICOM_UNIQUE_COLUMNS, how="left_anti")
            
            duplicate_records_merged_df = duplicate_records_df.withColumn(
            "merged_metadata",
            when(col(C.INCR_METADATA).isNotNull() & col(C.METADATA_COLUMN_NAME).isNotNull(),
                map_concat(col(C.METADATA_COLUMN_NAME), col(C.INCR_METADATA)))
            .when(col(C.INCR_METADATA).isNotNull(), col(C.INCR_METADATA))
            .when(col(C.METADATA_COLUMN_NAME).isNotNull(), col(C.METADATA_COLUMN_NAME))
            .otherwise(lit(None).cast(C.METADATA_SCHEMA)) # Cast to the correct map type if both are null
            )

            duplicate_records_merged_df = duplicate_records_merged_df.select(*IMAGING_DICOM_UNIQUE_COLUMNS,
                col("merged_metadata"),            
                coalesce(col(C.INCR_SOURCE_MODIFIED), col(C.SOURCE_MODIFIED_COLUMN_NAME)).alias("effective_lastUpdated"))
               
            df_exploded_final_dedup = duplicate_records_merged_df.select(*IMAGING_DICOM_UNIQUE_COLUMNS,
                explode(col("merged_metadata")).alias("tag", "meta_entry"),
                "effective_lastUpdated").drop("merged_metadata")
            
            window_spec_final_tag_dedup = Window.partitionBy(*IMAGING_DICOM_UNIQUE_COLUMNS, "tag").orderBy(col("effective_lastUpdated").desc())            
            
            df_deduplicated_tags = df_exploded_final_dedup.withColumn("rn", row_number().over(window_spec_final_tag_dedup))\
                                              .filter(col("rn") == 1).drop("rn")

            #Group back by the unique IDs and reconstruct the metadata map
            final_duplicates_df = df_deduplicated_tags.groupBy(*IMAGING_DICOM_UNIQUE_COLUMNS).agg(
                map_from_entries(collect_list(struct(col("tag"), col("meta_entry")))).alias("merged_metadata"),
                max(col("effective_lastUpdated")).alias("effective_lastUpdated")
            )
            
            unique_records_merged_df = unique_records_df.withColumn(
            "merged_metadata",
            when(col(C.INCR_METADATA).isNotNull() & col(C.METADATA_COLUMN_NAME).isNotNull(),
                map_concat(col(C.METADATA_COLUMN_NAME), col(C.INCR_METADATA)))
            .when(col(C.INCR_METADATA).isNotNull(), col(C.INCR_METADATA))
            .when(col(C.METADATA_COLUMN_NAME).isNotNull(), col(C.METADATA_COLUMN_NAME))
            .otherwise(lit(None).cast(C.METADATA_SCHEMA)) # Cast to the correct map type if both are null
            )

            unique_records_merged_df = unique_records_merged_df.select(*IMAGING_DICOM_UNIQUE_COLUMNS,
                col("merged_metadata"),            
                coalesce(col(C.INCR_SOURCE_MODIFIED), col(C.SOURCE_MODIFIED_COLUMN_NAME)).alias("effective_lastUpdated"))
            
            # Union the processed unique and duplicate DataFrames ---
            final_consolidated_df = unique_records_merged_df.unionByName(final_duplicates_df)        
        else:            
            unique_records_merged_df = joined_df.withColumn(
            "merged_metadata",
            when(col(C.INCR_METADATA).isNotNull() & col(C.METADATA_COLUMN_NAME).isNotNull(),
                map_concat(col(C.METADATA_COLUMN_NAME), col(C.INCR_METADATA)))
            .when(col(C.INCR_METADATA).isNotNull(), col(C.INCR_METADATA))
            .when(col(C.METADATA_COLUMN_NAME).isNotNull(), col(C.METADATA_COLUMN_NAME))
            .otherwise(lit(None).cast(C.METADATA_SCHEMA)) # Cast to the correct map type if both are null
            )

            final_consolidated_df = unique_records_merged_df.select(*IMAGING_DICOM_UNIQUE_COLUMNS,
                col("merged_metadata"),            
                coalesce(col(C.INCR_SOURCE_MODIFIED), col(C.SOURCE_MODIFIED_COLUMN_NAME)).alias("effective_lastUpdated"))
            
        # Final selection and renaming of columns            
        final_consolidated_df = final_consolidated_df.select(
            *IMAGING_DICOM_UNIQUE_COLUMNS,
            col("merged_metadata").alias(C.METADATA_COLUMN_NAME),
            col("effective_lastUpdated").alias(C.SOURCE_MODIFIED_COLUMN_NAME)
        ).withColumn(C.TAGS_METADATA_STRING, to_json(col(C.METADATA_COLUMN_NAME))
        ).withColumnRenamed(C.SOURCE_SYSTEM_COLUMN_NAME, C.SILVER_SOURCE_SYSTEM_COLUMN_NAME)  
        
        self._logger.info(
                LC.IMAGING_METASTORE_PRE_PROCESSING_STATE_INFO_MSG.format(
                    operation="PATCH",
                    state= C.STATE_COMPLETED,
                    timestamp=datetime.now()
                )
            )        
        return final_consolidated_df
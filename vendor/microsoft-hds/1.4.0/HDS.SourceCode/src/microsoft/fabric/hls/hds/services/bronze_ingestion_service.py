# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from functools import partial
import json
import hashlib
from typing import Union, Callable
from pyspark import StorageLevel
from pyspark.sql import DataFrame, SparkSession, functions as f, types as T
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_to_delta_table_using_path, \
    update_or_extract_namespace
from microsoft.fabric.hls.hds.structured_stream.file_stream_reader import FileStreamReader
from microsoft.fabric.hls.hds.structured_stream.stream_orchestrator import StreamOrchestrator, StreamingQueryInfo
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.validation_service import ValidationService
from microsoft.fabric.hls.hds.orchestrate.file_movement.file_compressor import FileCompressor  
from microsoft.fabric.hls.hds.errors.validation_failed_error import ValidationFailedError
from microsoft.fabric.hls.hds.errors.bronze_ingestion_failed_error import BronzeIngestionFailedError
from microsoft.fabric.hls.hds.errors.streaming_queries_failed_error import StreamingQueriesFailedError
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType

class BronzeIngestionService(BaseRunnableService):
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
            - solution_name: Name of the HDS-Healthcare data solutions OneLake workload solution
            - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
            - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
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
        Setup method for the BronzeIngestionService
        """
        try:
            self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
            
            Utils.validate_required_parameters({
                GC.BRONZE_LAKEHOUSE_ID_KEY: self.target_lakehouse_name
            })
            
            self.lakehouse_files_base_path = FolderPath.get_fabric_files_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name
            )
            
            self.source_path_pattern = self.parameter_service.get_activity_config_value(
                GC.SOURCE_PATH_PATTERN_KEY,
                f"{self.lakehouse_files_base_path}/{GC.DEFAULT_LANDINGZONE_SOURCE_PATTERN}"
            )
            self.target_table_name = self.parameter_service.get_activity_config_value(GC.TARGET_TABLE_NAME_KEY, GC.DEFAULT_BRONZE_FHIR_TABLE_NAME)
            self.target_tables_path = self.parameter_service.get_activity_config_value(
                GC.TARGET_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.target_lakehouse_name
                )
            )
            self.checkpoint_path = self.parameter_service.get_activity_config_value(
                GC.CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(root_path=self.config_files_root_path, checkpoint_folder_name=self.target_lakehouse_name)
            )
            self.schema_dir_path = self.parameter_service.get_activity_config_value(
                GC.SCHEMA_DIR_PATH_KEY,
                f"{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GC.DEFAULT_BRONZE_LAKEHOUSE_NAME}"
            )
            self.move_failed_files_enabled = self.parameter_service.get_activity_config_value(GC.MOVE_FAILED_FILES_ENABLED_KEY, True, "bool")
            self.compression_enabled = self.parameter_service.get_activity_config_value(GC.COMPRESSION_ENABLED_KEY, True, "bool")
            
            self.log_retention_duration = self.parameter_service.get_activity_config_value(
                GC.DELTA_LOG_RETENTION_DURATION_KEY, 
                GC.DEFAULT_DELTA_LOG_RETENTION_DURATION
            )
            self.deleted_file_retention_duration = self.parameter_service.get_activity_config_value(
                GC.DELTA_DELETED_FILE_RETENTION_DURATION_KEY, 
                GC.DEFAULT_DELTA_DELETED_FILE_RETENTION_DURATION
            )
            
            self.validation_config_key = self.parameter_service.get_activity_config_value(GC.VALIDATION_CONFIG_KEY, GC.VALIDATION_CONFIG_BRONZE_KEY)
            self.business_events_table_path = self.parameter_service.get_activity_config_value(
                GC.BUSINESS_EVENTS_TABLE_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.admin_lakehouse_name
                )
            )
            self.business_events_schema_dir_path = self.parameter_service.get_activity_config_value(
                GC.BUSINESS_EVENTS_SCHEMA_DIR_PATH_KEY,
                f"{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GC.BUSINESS_EVENTS_SCHEMA_ROOT_FOLDER}"
            )
            
            self.max_bytes_per_trigger = self.parameter_service.get_activity_config_value(GC.MAX_BYTES_PER_TRIGGER_KEY, GC.DEFAULT_NUMBER_OF_BYTES_PER_TRIGGER_BRONZE, "int")
            self.max_files_per_trigger = self.parameter_service.get_activity_config_value(GC.MAX_FILES_PER_TRIGGER_KEY, GC.DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_BRONZE, "int")
            self.max_structured_streaming_queries = self.parameter_service.get_activity_config_value(GC.MAX_STRUCTURED_STREAMING_QUERIES_KEY, GC.DEFAULT_NUMBER_OF_MAX_STREAMING_QUERIES_BRONZE, "int")
            self.file_extensions = self.parameter_service.get_activity_config_value(GC.FILE_EXTENSION_KEY, GC.DEFAULT_FHIR_NDJSON_FILE_EXTENSION)
            
            self.source_mount_path = Utils.mount_and_create(self.source_path_pattern, GC.CLINICAL_FHIR_NDJSON_SOURCE_MOUNT_LOCATION, self.mssparkutils_client)
            
            if self.compression_enabled or self.move_failed_files_enabled:
                self._file_compressor = FileCompressor(self.spark, self.source_path_pattern, self.source_mount_path)
            
            self.business_events_schema_path = f"{self.business_events_schema_dir_path}/{GC.BUSINESS_EVENTS_TABLE}.avsc"
            self.source_root_path = Utils.get_root_path_from_source_path_pattern(self.source_path_pattern)
            self.failed_root_path = f"{self.lakehouse_files_base_path}/{GC.FAILED_FOLDER}"
            
            self.validation_service = ValidationService(
                spark=self.spark,
                workspace_name=self.workspace_name,
                validation_config_path=self.validation_config_path,
                business_events_table_path=self.business_events_table_path,
                business_events_lakehouse_name=self.admin_lakehouse_name,
                business_events_schema_path=self.business_events_schema_path,
                validation_config_key=self.validation_config_key,
                activity_name=self.notebook_name,
                run_id=self.run_id,
                source_file_path=GC.DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL,
                target_lakehouse_name=self.target_lakehouse_name,
                move_failed_files_enabled=self.move_failed_files_enabled,
                source_root_path = self.source_root_path,
                failed_root_path = self.failed_root_path,
                mssparkutils_client=self.mssparkutils_client
            )
            
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        target_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name)
        return ExecutionMetadata(
            sourceType=ExecutionDataType.file,
            sourcePath=self.source_path_pattern,
            targetType=ExecutionDataType.deltaTable,
            targetLakehouseName=target_lakehouse_properties.get("displayName"),
            targetLakehouseIdentifier=target_lakehouse_properties.get("id"),
            targetPath=self.target_tables_path
        )
        
    def _register_custom_accumulators(self) -> None:
        self.execution_metrics_collector.register_accumulator(
            accumulator_activity_id=self._get_validation_metrics_accumulator_activity_id(),
            initial_state=self._get_validation_metrics_initial_state()
        )
        
    def _get_internal_activity_name(self) -> str:
        return GC.BRONZE_INGESTION_ACTIVITY_NAME
    
    def _execute(self, **kwargs) -> None:
        """
        Executes the BronzeIngestionService    
        
        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.
        """
        self.ingest()

    def ingest(self) -> None:
        """
        Ingests data from the specified source path, ensuring it is partitioned by resourceType and stored into a Delta Lake table. 
        This process specifically targets files with any ndjson formatted for any file extensions.
        Returns: The execution result of the process.
        """
        self.spark.conf.set("spark.sql.files.ignoreMissingFiles", "true")
        
        # Set Delta table retention properties at the start of ingestion using configured values
        target_table_path = f"{self.target_tables_path}/{self.target_table_name}"
        try:
            Utils.set_delta_table_retention_properties(
                self.spark,
                target_table_path, 
                self.log_retention_duration, 
                self.deleted_file_retention_duration
            )
        except Exception as ex:
            self._logger.error(f"Could not set Delta table retention properties for {target_table_path}. Table may not exist yet. Error: {str(ex)}")
        
        stream_orchestrator = StreamOrchestrator(self.spark, self.max_structured_streaming_queries)
        
        extension_list = [ext.strip() for ext in self.file_extensions.split(',')]
        file_extension_pattern = f"*.{{{','.join(extension_list)}}}"
        
        file_stream_reader = FileStreamReader(self.spark,
                                            maxFilesPerTrigger=self.max_files_per_trigger,
                                            recursiveFileLookup="true",
                                            pathGlobFilter=file_extension_pattern)
        
        streaming_path = self.source_path_pattern
        
        self._logger.info(
        f"{LC.SET_STRUCTURED_STREAMING_INFO_MSG.format(streaming_path)}"
        )
        streaming_dataframe = file_stream_reader.set_up_streaming_ndjson_string(
            streaming_path,
        )
        
        batch_fn=partial(self._preprocess_and_append_to_delta_using_path)
        
        source_path_hash = self._hash_source_path(self.source_path_pattern)
            
        streaming_query_info = StreamingQueryInfo(
            query_name=f"{self.target_tables_path}/{self.target_table_name}",
            checkpoint_path=f"{self.checkpoint_path}/{self.target_table_name}/{source_path_hash}",
            streaming_dataframe=streaming_dataframe,
            batch_fn=batch_fn,
            data_format="delta")
            
        stream_orchestrator.enqueue_streaming_query(streaming_query_info)
        
        streaming_exception = None
        exceptions = []
        try:
            stream_orchestrator.await_all()
        except Exception as ex:
            streaming_exception = ex

        streaming_metrics = stream_orchestrator.get_streaming_metrics()
        self._logger.info(f"Streaming metrics: {json.dumps(streaming_metrics, indent=2)}")
        
        if self.source_mount_path is not None:
            self.mssparkutils_client.fs_unmount(GC.CLINICAL_FHIR_NDJSON_SOURCE_MOUNT_LOCATION)
            
        if self.move_failed_files_enabled:
            self.validation_service.unmount()

        try:
            self._logger.info(f"Bronze Ingestion Metrics: {json.dumps(self.execution_metrics_collector.get_summary(self._get_validation_metrics_accumulator_activity_id()), indent=2)}")
        except Exception as ex:
            self._logger.error("Failed to log validation metrics")
        
        self.spark.conf.set("spark.sql.files.ignoreMissingFiles", "false")
        
        if self.has_validation_errors:
            validation_error_msg = LC.BRONZE_INGESTION_VALIDATION_ERROR_FAILURE_MSG.format(run_id=self.run_id)
            self._logger.error(validation_error_msg)
            validation_exception = ValidationFailedError(validation_error_msg)
            exceptions.append(validation_exception)
            
        if streaming_exception:
            streaming_error_msg = LC.STREAMING_FAILED_ERROR_MSG.format(streaming_exception)
            self._logger.error(streaming_error_msg)
            streaming_exception = StreamingQueriesFailedError(streaming_error_msg)
            exceptions.append(streaming_exception)
        
        if len(exceptions) > 0:
            raise BronzeIngestionFailedError(exceptions=exceptions)
    
    def _load_avro_schema_file(self, schema_fullpath: str):
        """
        Given the path to a schema, load the schema and return the resource type and schema object

        Args:
            schema_fullpath (str): the path to the schema
        """
        self._logger.info(
            f"{LC.BRONZE_INGESTION_START_LOAD_INFO_MSG.format(path=schema_fullpath)}"
        )
        schema_content = self.spark.sparkContext.wholeTextFiles(
            schema_fullpath
        ).collect()[0][1]
        parsed_schema = self.spark._jvm.org.apache.avro.Schema.Parser().parse(
            str(schema_content)
        )

        java_schema_type = (
            self.spark._jvm.org.apache.spark.sql.avro.SchemaConverters.toSqlType(
                parsed_schema
            )
        )  # type: ignore

        json_schema = json.loads(java_schema_type.dataType().json())
        
        return T.StructType.fromJson(json_schema)
    
    def _preprocess_and_append_to_delta_using_path(self, df: DataFrame, batch_id: int):
        """
        The function to pre-process the data and append to the delta table

        Args:
            df (DataFrame): the DataFrame passed from the initial ingest call
        """
        delta_table_path=f"{self.target_tables_path}/{self.target_table_name}"
        
        fhir_resource_schema = self._load_avro_schema_file(f"{self.schema_dir_path}/{self.target_table_name}.avsc")
        
        df_to_process = self._preprocess_streamed_dataframe(df, fhir_resource_schema)
        
        df_to_process.persist(StorageLevel.MEMORY_AND_DISK)
        
        df_to_process = df_to_process.withColumn(GC.BRONZE_ORIGINAL_SRC_PATH_COL_NAME, f.col(GC.DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL))
        
        validated_dict_dfs = self.validation_service.validate_df(
            df=df_to_process, 
            table_name=self.target_table_name,
            run_id=self.run_id,
            delete_enabled=True
        )
        
        final_df = validated_dict_dfs[GC.VALIDATION_DF_SUCCESSES_KEY]
        if validated_dict_dfs[GC.VALIDATION_DF_WARNINGS_KEY]:
            final_df = validated_dict_dfs[GC.VALIDATION_DF_SUCCESSES_KEY].union(validated_dict_dfs[GC.VALIDATION_DF_WARNINGS_KEY])

        failed_files_count = validated_dict_dfs[GC.VALIDATION_DF_ERRORS_KEY].select(GC.DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL).distinct().count()
        final_files_count = final_df.select(GC.DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL).distinct().count()
        
        if self.compression_enabled :     
            compressed_df = self._file_compressor.run_compression_from_df(
                compression_df = final_df, 
                row_count = final_files_count,
                file_path_column = GC.DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL
            )
                
            final_df = compressed_df
                
        append_to_delta_table_using_path(
            df_to_process=final_df.drop(GC.BRONZE_ORIGINAL_SRC_PATH_COL_NAME),
            delta_table_path=delta_table_path,
            logger=self._logger,
            partition_cols=GC.DEFAULT_BRONZE_FHIR_TABLE_PARTITION_COLS,
            collect_metrics_fn = self.collect_target_delta_table_operation_summary_metrics
        )
        
        validation_success_count = validated_dict_dfs[GC.VALIDATION_DF_SUCCESSES_KEY].count()
        validation_errors_count = 0
        validation_warnings_count = 0
        
        if validated_dict_dfs[GC.VALIDATION_DF_ERRORS_KEY]:
            validation_errors_count = validated_dict_dfs[GC.VALIDATION_DF_ERRORS_KEY].count()
            
        if validated_dict_dfs[GC.VALIDATION_DF_WARNINGS_KEY]:
            validation_warnings_count = validated_dict_dfs[GC.VALIDATION_DF_WARNINGS_KEY].count()
    
        self._logger.info(LC.MICRO_BATCH_APPEND_TO_DELTA_MANAGED_INFO_MSG.format(
            delta_table_path=delta_table_path, 
            num_records_persisted=validation_success_count,
            num_validation_errors=validation_errors_count,
            batch_id=batch_id
        ))

        # Update the validation error and warning flags
        self.has_validation_errors = validation_errors_count > 0
        self.has_validations_warnings = validation_warnings_count > 0
            
        total_records = validation_success_count + validation_errors_count + validation_warnings_count
        
        try:
            source_file_count = final_files_count + failed_files_count
            
            # Collect the source file count and record count
            self.execution_metrics_collector.accumulate(
                accumulator_activity_id=self.get_execution_metrics_accumulator_activity_id(),
                metrics={
                    "numSourceRecords": total_records,
                    "numSourceFiles": source_file_count
                }
            )
            
            # Collect the validation metrics for logging purposes
            self.execution_metrics_collector.accumulate(
                accumulator_activity_id=self._get_validation_metrics_accumulator_activity_id(),
                metrics={
                    GC.VALIDATION_DF_TOTAL_KEY: total_records,
                    GC.VALIDATION_DF_SUCCESSES_KEY: validation_success_count,
                    GC.VALIDATION_DF_ERRORS_KEY: validation_errors_count,
                    GC.VALIDATION_DF_WARNINGS_KEY: validation_warnings_count
                }
            )            
    
        except Exception as ex:
            self._logger.error(f"Error updating {self._get_activity_display_name()} metrics: Error details: {str(ex)}")
             
        df_to_process.unpersist()
        
    def _preprocess_streamed_dataframe(self, df: DataFrame, schema_obj: T.StructType):
        """
        Processes streamed DataFrame to extract columns required for the bronze table

        Args:
            df (DataFrame): The streamed DataFrame to process.
            schema_obj (StructType): The schema object to apply to the 'value' column.

        Returns:
            DataFrame: The processed DataFrame with 'id', 'resourceType', 'sourceSystem', 'lastUpdated', 'fhirContent', and 'filePath' columns.
        """
        # Convert the 'value' column into a JSON object according to the provided schema
        processed_json_df = df.select(f.from_json(f.col("value"), schema_obj).alias("data"),\
            f.col("value").alias(GC.DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_CONTENT_COL))

        # Extract the required columns from the JSON object
        extracted_columns_df = processed_json_df. \
            select(
                f"data.{GC.DEFAULT_BRONZE_FHIR_TABLE_ID_COL}", \
                f"data.{GC.DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_TYPE_COL}", \
                f.col(f"data.{GC.DEFAULT_BRONZE_FHIR_SOURCE_META_LASTUPDATED_COL}"). \
                    alias(GC.DEFAULT_BRONZE_FHIR_TABLE_SOURCE_MODIFIED_ON_COL), \
                GC.DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_CONTENT_COL
            ). \
            withColumn(GC.DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL, f.input_file_name())
    
        # Extract the sourceSystem from the file path
        final_df = update_or_extract_namespace(
            df=extracted_columns_df,
            target_column=GC.DEFAULT_BRONZE_FHIR_TABLE_SOURCE_SYSTEM_COL,
            file_path_column=GC.DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL)
        
        return final_df

    def _hash_source_path(self,source_path: str) -> Union[str,None]:
        """
        Hash the source path for uniqueness when creating the checkpoint location
        """
        if not isinstance(source_path, str) or source_path is None:
            return None
        
        link_encoded = source_path.encode()
        hash_object = hashlib.sha256(link_encoded)
        return hash_object.hexdigest()

    
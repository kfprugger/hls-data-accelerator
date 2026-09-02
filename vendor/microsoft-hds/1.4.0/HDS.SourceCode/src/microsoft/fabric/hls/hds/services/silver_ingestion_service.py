# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import re
import uuid
import concurrent.futures
from functools import partial
import json
from typing import Dict, Callable, Union
from delta.tables import DeltaTable
from pyspark.sql import SparkSession, DataFrame, types as T, functions as F
from microsoft.fabric.hls.hds.errors.silver_ingestion_failed_error import SilverIngestionFailedError
from microsoft.fabric.hls.hds.structured_stream.delta_table_stream_reader import DeltaTableStreamReader
from microsoft.fabric.hls.hds.structured_stream.stream_orchestrator import StreamOrchestrator, StreamingQueryInfo
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants
from microsoft.fabric.hls.hds.flatten.constants import FlattenConstants
from microsoft.fabric.hls.hds.utils.thread_pool_manager import ThreadPoolManager
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.extension_parser import ExtensionParser
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.constants import ImagingStudyConstants as C
from microsoft.fabric.hls.hds.medical_imaging.dicom.core.imaging_silver_metastore_creator import ImagingSilverMetaStoreCreator
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType
from microsoft.fabric.hls.hds.flatten.flatten_manager import FlattenManager

class SilverIngestionService(BaseRunnableService):
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
        Setup method for the SilverIngestionService
        """
        ExtensionParser.register(self.spark)
        
        self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
        self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)
        
        Utils.validate_required_parameters({
            GC.BRONZE_LAKEHOUSE_ID_KEY: self.source_lakehouse_name,
            GC.SILVER_LAKEHOUSE_ID_KEY: self.target_lakehouse_name
        })
        try:
            self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                solution_name=self.solution_name
            )
            
            self.source_table_name = self.parameter_service.get_activity_config_value(GC.SOURCE_TABLE_NAME_KEY)
            self.main_config_path = self.parameter_service.get_activity_config_value(
                GC.CONFIG_PATH_KEY,
                FolderPath.get_fabric_workload_files_flatten_config_folder_path(root_path=self.config_files_root_path)
            )
            self.source_tables_path = self.parameter_service.get_activity_config_value(
                GC.SOURCE_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.source_lakehouse_name
                )
            )
            self.target_tables_path = self.parameter_service.get_activity_config_value(
                GC.TARGET_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.target_lakehouse_name
                ),
            )
            self.checkpoint_path_prefix = self.parameter_service.get_activity_config_value(
                GC.CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(root_path=self.config_files_root_path,
                                                                            checkpoint_folder_name=self.target_lakehouse_name),
            )
            self.schema_dir_path = self.parameter_service.get_activity_config_value(
                GC.SCHEMA_DIR_PATH_KEY,
                f"{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GC.DEFAULT_SILVER_LAKEHOUSE_NAME}",
            )
            self.max_files_per_trigger = self.parameter_service.get_activity_config_value(
                GC.MAX_FILES_PER_TRIGGER_KEY,
                GC.DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_SILVER,
                "int"  
            )
            self.max_bytes_per_trigger = self.parameter_service.get_activity_config_value(
                GC.MAX_BYTES_PER_TRIGGER_KEY,
                GC.DEFAULT_NUMBER_OF_BYTES_PER_TRIGGER_SILVER,
                "int"
            )
            self.max_structured_streaming_queries = self.parameter_service.get_activity_config_value(
                GC.MAX_STRUCTURED_STREAMING_QUERIES_KEY,
                GC.DEFAULT_NUMBER_OF_MAX_STREAMING_QUERIES_SILVER,
                "int"
            )
            
            self.skip_change_commits = "true"
            
            activity_key_to_spark_property_dict = {
                GC.OPTIMIZED_WRITE_BIN_SIZE_KEY: "spark.databricks.delta.optimizeWrite.binSize",
                GC.SHUFFLE_PARTITIONS_KEY: "spark.sql.shuffle.partitions",
                GC.MAX_PARTITION_BYTES_KEY: "spark.sql.files.maxPartitionBytes"
            }
            
            self.parameter_service.update_spark_properties(activity_key_to_spark_property_dict)

        except Exception as ex:
            self._logger.error(message=str(ex))
            raise
        
        self.config_entities = {}
        self.__load_config()

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        source_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name)
        target_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name)
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourceLakehouseName=source_lakehouse_properties.get("displayName"),
            sourceLakehouseIdentifier=source_lakehouse_properties.get("id"),
            sourcePath=self.source_tables_path,
            targetType=ExecutionDataType.deltaTable,
            targetLakehouseName=target_lakehouse_properties.get("displayName"),
            targetLakehouseIdentifier=target_lakehouse_properties.get("id"),
            targetPath=self.target_tables_path
        )

    def _get_internal_activity_name(self) -> str:
        return GC.SILVER_INGESTION_ACTIVITY_NAME
    
    def _default_transformation_fn(self) -> Callable:
        flatten_manager = FlattenManager(spark=self.spark, 
                                         workspace_name=self.workspace_name, 
                                         solution_name=self.solution_name, 
                                         one_lake_endpoint=self.one_lake_endpoint)
        
        return flatten_manager.process_resource
    
    def _execute(self, **kwargs) -> None:
        """
        Execute the SilverIngestionService
    
        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.
        """
        silver_transformation_fn = kwargs.get("transformation_fn", self._default_transformation_fn())
        self.ingest_from_partitioned_single_table(silver_transformation_fn=silver_transformation_fn)          
        
    def ingest_from_partitioned_single_table(self, silver_transformation_fn: Callable) -> None:
        """
        Ingest data from a partitioned single source table and apply the silver transformation function.

        This method sets up streaming on a single source table that is already partitioned by resource type,
        and applies the provided silver transformation function to each partition.
        
        Args:
            silver_transformation_fn (Callable): A function that accepts a dataframe as an argument and returns the resulting 
                                                dataframe name and dataframe to save under target_table_path_prefix
        """
        source_table_path = f"{self.source_tables_path}/{self.source_table_name}"
            
        resources_with_no_source_data = []
        if not DeltaTable.isDeltaTable(
                self.spark, source_table_path
        ) or self.__is_delta_table_empty(delta_table_path=source_table_path):
            self._logger.info(
                LoggingConstants.SILVER_INGESTION_SOURCE_TABLE_DOES_NOT_EXIST_OR_EMPTY.format(source_table_path=source_table_path)
            )
        else:
            # Set up streaming on all source tables
            self._logger.info(f"The max_structured_streaming_queries is set to {self.max_structured_streaming_queries}")
            
            # Set up streaming on all source tables
            stream_orchestrator = StreamOrchestrator(
                spark=self.spark, 
                max_structured_streaming_queries=self.max_structured_streaming_queries,
                logger=self._logger
            )
            
            delta_table_stream_reader = self.__get_delta_table_stream_reader()
        
            streaming_dataframe = delta_table_stream_reader.set_up_streaming(
                    delta_table_path=source_table_path
                )
            
            # Load all distinct resourceType values once
            source_table_resource_types = self.__load_resource_type_values_from_partitioned_table(source_table_path)
            
            for resource, resource_config in self.config_entities.items():
                target_table_path = f"{self.target_tables_path}/{resource}"
                
                if resource not in source_table_resource_types:
                    if not DeltaTable.isDeltaTable(self.spark, target_table_path):
                        self._logger.info(
                        LoggingConstants.SILVER_INGESTION_SOURCE_AND_TARGET_TABLES_DO_NOT_EXIST_OR_EMPTY.format(
                            source_table_path=source_table_path, 
                            target_table_path=target_table_path)
                        )
                        resources_with_no_source_data.append(resource_config)
                    else:
                        self._logger.info(
                        LoggingConstants.SILVER_INGESTION_TRANSFORMATION_SKIPPED.format(
                            resource_name=resource,
                            source_table_path=source_table_path)
                        )
                        
                    continue
                checkpoint_path = f"{self.checkpoint_path_prefix}/{resource}/{self.source_table_name}"
                self.__validate_checkpoint(f"{self.target_tables_path}/{resource}", checkpoint_path)
                
                streaming_df_resource = streaming_dataframe.filter(
                    streaming_dataframe[GC.DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_TYPE_COL] == resource
                    )
                
                batch_fn = partial(
                            self._process_by_resource_type,
                            silver_transformation_fn=silver_transformation_fn,
                            resource=resource,
                            resource_config=resource_config)
                
                streaming_query_info = StreamingQueryInfo(
                        query_name = f"{self.source_tables_path}_{self.target_tables_path}_{resource}",
                        checkpoint_path = checkpoint_path,
                        streaming_dataframe=streaming_df_resource,
                        batch_fn=batch_fn,
                        data_format="delta")
                
                stream_orchestrator.enqueue_streaming_query(streaming_query_info)
                    
            streaming_exception = None
            try:
                stream_orchestrator.await_all()
            except Exception as ex:
                streaming_exception = ex
            
            # Call silver_transformation_fn with None Dataframe for resource that do not have source data and the target table does not exist
            self._process_resources_with_no_target_tables_or_source_data(
                resources_with_no_source_data=resources_with_no_source_data, 
                silver_transformation_fn=silver_transformation_fn
            )
            
            streaming_metrics = stream_orchestrator.get_streaming_metrics()
            self._logger.info(f"Streaming metrics: {json.dumps(streaming_metrics, indent=2)}")

            if streaming_exception:
                self._logger.error(LoggingConstants.STREAMING_FAILED_ERROR_MSG.format(streaming_exception))
                raise SilverIngestionFailedError(str(streaming_exception))

            # if stream_orchestrator.check_stream_success(f"{self.source_tables_path}_{self.target_tables_path}_{C.FHIR_IMAGING_STUDY_RES_NAME}"):
            #     self.__create_imaging_silver_meta_store()

    def ingest_from_multiple_tables(self, silver_transformation_fn: Callable) -> None:
        """
        Ingest data from multiple source tables and apply the silver transformation function.

        This method sets up streaming on multiple source tables as specified in the configuration,
        and applies the provided silver transformation function to each table.
        
        Args:
            silver_transformation_fn (Callable): A function that accepts a dataframe as an argument and returns the resulting dataframe name 
                                                and dataframe to save under silver_table_path_prefix

        """
        # Generate a unique run id for each execution run
        self.run_id = str(uuid.uuid4())
        self._logger.set_run_id(run_id=self.run_id)
        
        # Set up streaming on all source tables
        self._logger.info(f"The max_structured_streaming_queries is set to {self.max_structured_streaming_queries}")
        
        self._logger.info(f"{LoggingConstants.SILVER_INGESTION_MULTIPLE_TABLES_START_INFO_MSG}")
        # Set up streaming on all source tables
        stream_orchestrator = StreamOrchestrator(
            spark=self.spark, 
            max_structured_streaming_queries=self.max_structured_streaming_queries,
            logger=self._logger
        )
        delta_table_stream_reader = self.__get_delta_table_stream_reader()
        resources_with_no_source_data = []
        
        for resource, resource_config in self.config_entities.items():
            source_table_path = f"{self.source_tables_path}/{resource}"
            target_table_path = f"{self.target_tables_path}/{resource}"
            # Check if the source table is not a Delta table or is empty
            if not DeltaTable.isDeltaTable(
                self.spark, source_table_path
            ) or self.__is_delta_table_empty(delta_table_path=source_table_path):
                # For resources with no source data, mark only those whose target
                # table's in Silver does not exist for Silver transformation.
                # This ensures we only run Silver transformations for Empty tables only during the initial load
                # Schema evolution is only handled when there is data to be ingested for the Silver transformation
                # For downstream dependencies, it's paramount to run Silver table setup function which handles creating of
                # tables required required downstream as well as schema evolution when there is no source data.
                # Note: Schema evolution is already handled when persisting the data using Delta auto schema evolution feature
                if not DeltaTable.isDeltaTable(self.spark, target_table_path):
                    self._logger.info(
                    f"{LoggingConstants.SILVER_INGESTION_SOURCE_AND_TARGET_TABLES_DO_NOT_EXIST_OR_EMPTY.format(source_table_path=source_table_path, target_table_path=target_table_path)}"
                    )
                    resources_with_no_source_data.append(resource_config)
                else:
                    self._logger.info(
                    f"{LoggingConstants.SILVER_INGESTION_TRANSFORMATION_SKIPPED.format(source_table_path=source_table_path, target_table_path=target_table_path)}"
                    )
                
                continue
            else:
                checkpoint_path = f"{self.checkpoint_path_prefix}/{resource}"
                self.__validate_checkpoint(f"{self.target_tables_path}/{resource}", checkpoint_path)
    
                streaming_dataframe = delta_table_stream_reader.set_up_streaming(delta_table_path=source_table_path)
                
                batch_fn = partial(
                    silver_transformation_fn,
                    config=resource_config,
                    target_tables_path=self.target_tables_path
                )

                streaming_query_info = StreamingQueryInfo(
                    query_name = f"{self.source_tables_path}_{self.target_tables_path}_{resource}",
                    checkpoint_path = f"{self.checkpoint_path_prefix}/{resource}",
                    streaming_dataframe=streaming_dataframe,
                    batch_fn=batch_fn
                )
                
                stream_orchestrator.enqueue_streaming_query(streaming_query_info)
                
                
        streaming_exception = None
        try:
            stream_orchestrator.await_all()
        except Exception as ex:
            streaming_exception = ex
            
        # Call silver_transformation_fn with None Dataframe for resource that do not have source data and the target table does not exist
        self._process_resources_with_no_target_tables_or_source_data(
            resources_with_no_source_data=resources_with_no_source_data, 
            silver_transformation_fn=silver_transformation_fn
        )

        streaming_metrics = stream_orchestrator.get_streaming_metrics()
        self._logger.info(f"Streaming metrics: {json.dumps(streaming_metrics, indent=2)}")

        if streaming_exception:
            self._logger.error(LoggingConstants.STREAMING_FAILED_ERROR_MSG.format(streaming_exception))
            raise SilverIngestionFailedError(str(streaming_exception))

        self._logger.info(f"{LoggingConstants.SILVER_INGESTION_MULTIPLE_TABLES_COMPLETED_INFO_MSG}")
        
    def __create_imaging_silver_meta_store(self):
        """
        Create silver imaging meta store table
        """
        imagingstudy_table_path = f"{self.target_tables_path}/{C.FHIR_IMAGING_STUDY_RES_NAME}"
        dicommetastore_table_path = f"{self.source_tables_path}/{C.METADATA_TABLE_NAME}"
        if DeltaTable.isDeltaTable(self.spark, imagingstudy_table_path) and DeltaTable.isDeltaTable(self.spark, dicommetastore_table_path):
                service = ImagingSilverMetaStoreCreator(self.spark,
                        workspace_name=self.workspace_name,
                        solution_name=self.solution_name,
                        one_lake_endpoint=self.one_lake_endpoint,
                        parameter_service= self.parameter_service,
                        collect_metrics_fn = self.collect_target_delta_table_operation_summary_metrics
                )
                service.process()
               
    def __validate_checkpoint(self, target_table_path: str, checkpoint_path: str) -> None:
        """
        Validate the checkpoint path before streaming. Remove the checkpoint metadata when conditions are met.
        
        Args:
            target_table_path (str): The target table path
            checkpoint_path (str): The checkpoint path
        """
        resource_name = ""
        try:
            resource_name = target_table_path.split("/")[-1]
            if not DeltaTable.isDeltaTable(self.spark, target_table_path) and self.__delta_table_has_checkpoint(checkpoint_path):
                self._logger.info(LoggingConstants.SILVER_INGESTION_VALIDATE_CHECKPOINT_NO_DELTA_TABLE_MSG.format(resource_name=resource_name))
                self.__remove_checkpoint_metadata(checkpoint_path)
            
            if DeltaTable.isDeltaTable(self.spark, target_table_path) and self.__is_delta_table_empty(target_table_path) and self.__delta_table_has_checkpoint(checkpoint_path):
                self._logger.info(LoggingConstants.SILVER_INGESTION_VALIDATE_CHECKPOINT_NO_DATA_MSG.format(resource_name=resource_name))
                self.__remove_checkpoint_metadata(checkpoint_path)
        
        except Exception as e:
            error_message = LoggingConstants.SILVER_INGESTION_VALIDATE_CHECKPOINT_FAILED_ERROR_MSG.format(resource_name=resource_name)
            self._logger.error(error_message)

    def __is_delta_table_empty(self, delta_table_path) -> bool:
        try:
            delta_table = DeltaTable.forPath(self.spark, delta_table_path)
            table_details_df = delta_table.detail()
            
            # Use DataFrame operations to check if the table is empty
            is_empty = table_details_df.filter((F.col("numFiles") == 0) & (F.col("sizeInBytes") == 0)).count() > 0
            
            return is_empty
        except Exception as e:
            self._logger.error(LoggingConstants.SILVER_INGESTION_DELTA_TABLE_EMPTY_CHECK_ERROR_MSG.format(error_message=str(e)))
            return False

    def __delta_table_has_checkpoint(self, checkpoint_path) -> bool:
        return self.mssparkutils_client.fs_exists(checkpoint_path)
    
    def __remove_checkpoint_metadata(self, checkpoint_path) -> None:
        return self.mssparkutils_client.fs_rm(checkpoint_path, recursive=True) 
    
    def __load_resource_type_values_from_partitioned_table(self, delta_table_path: str) -> list:
        """
        Load all distinct resourceType values from the Delta log files.
        Args:
            delta_table_path (str): Path to the Delta table.
        Returns:
            list: A list of distinct resourceType values.
        """
        resource_types = []
        try:
            
            # Discover resourceType partitions by listing the physical folder structure following the pattern "resourceType=Value".

            files = self.mssparkutils_client.fs_ls(delta_table_path)
            resource_types = [
                re.search(r'resourceType=(.+)', f.name).group(1)
                for f in files
                if f.name.startswith("resourceType=")
                and GC.RESOURCE_TYPE_HIVE_DEFAULT_PARTITION not in f.name
            ]

        except Exception as e:
            # Log the exception
            self._logger.error(LoggingConstants.SILVER_INGESTION_FAILED_TO_LOAD_RESOURCE_TYPES_ERROR_MSG.format(delta_table_path=delta_table_path, exception_details=str(e)))
        
        return resource_types

    def __load_config(self):
        """
        Load main configuration and initialize internal list with supported resources
        """
        config_content = self.spark.sparkContext.wholeTextFiles(
            self.main_config_path
        ).collect()[0][1]

        self.main_config_json = json.loads(str(config_content))
        for entry in self.main_config_json[GC.SILVER_CONFIG_RESOURCES_KEY]:
            self.config_entities[entry[GC.SILVER_CONFIG_NAME_KEY]] = entry
            
    def __get_delta_table_stream_reader(self) -> DeltaTableStreamReader:

        stream_reader_kwargs = {}
        
        self._logger.info(f"The maxBytesPerTrigger is set to {self.max_bytes_per_trigger}.The maxFilesPerTrigger is set to {self.max_files_per_trigger}.")
        if self.max_bytes_per_trigger:
            stream_reader_kwargs["maxBytesPerTrigger"] = self.max_bytes_per_trigger
            
        if self.max_files_per_trigger:
            stream_reader_kwargs["maxFilesPerTrigger"] = self.max_files_per_trigger
        
        if self.skip_change_commits:
            stream_reader_kwargs["skipChangeCommits"] = self.skip_change_commits

        return DeltaTableStreamReader(self.spark, **stream_reader_kwargs)
    
    def _get_avro_schema(self, resource_config: Dict) -> Union[T.StructType,None]:
        """
        Returns avro schema for specified resource config

        Args:
        - resource_config: dict - The configuration for the resource. It contains the relative source schema path for the resource 
        """
    
        # find resource configuration
        if resource_config:
            schema_conf = resource_config[FlattenConstants.MAIN_CONFIG_SECT_SCHEMA]
            schema_path = schema_conf[FlattenConstants.SCHEMA_CONFIG_ATTR_PATH]
            # loading file(s) specified in path with schema specified
            schema_content = Utils.load_config_file(self.spark, f'{self.schema_dir_path}/{schema_path}')
            return Utils.load_schema_from_avro_schema(self.spark, schema_content)
        
        return None

    def _parse_resource_data_column(self, df: DataFrame, resource_config: Dict, resource: str) -> DataFrame:
        """
        Returns the DataFrame with all columns extracted from the parsed resource column

        Args:
        - df: DataFrame - The streamed DataFrame to parse
        - resource_config: dict - The configuration for the resource. It contains the relative source schema path for the resource 
        - resource : str - The name of the resource being streamed
        """
        # Validation for resource_config
        if not resource_config:
            error_message = LoggingConstants.SILVER_INGESTION_PARSING_DF_NO_CONFIG_FOUND_ERROR_MSG.format(
                resource=resource,
                config_path=self.main_config_path,
                source_table_path=self.source_tables_path
            )
            self._logger.error(error_message)
            raise SilverIngestionFailedError(error_message)
        
        # Get the schema for the resource
        resource_schema = self._get_avro_schema(resource_config)
        
        # Validation for resource_schema
        if not resource_schema:
            error_message = LoggingConstants.SILVER_INGESTION_FAILED_TO_LOAD_SCHEMA_ERROR_MSG.format(
                resource=resource, 
                config_path=self.main_config_path
            )
            self._logger.error(error_message)
            raise SilverIngestionFailedError(error_message)
        
        try:
            # Select only the columns that are needed and rename them
            df = df.select(GC.DEFAULT_BRONZE_FHIR_TABLE_ID_COL, 
                           GC.DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_TYPE_COL,
                           GC.DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_CONTENT_COL,
                           F.col(GC.DEFAULT_BRONZE_FHIR_TABLE_SOURCE_SYSTEM_COL) \
                               .alias(GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_SOURCE_SYSTEM_COL),
                           F.col(GC.DEFAULT_BRONZE_FHIR_TABLE_FILE_PATH_COL) \
                               .alias(GC.DEFAULT_SILVER_FHIR_TABLE_MSFT_FILE_PATH_COL)
                           )
            
            # Get the list of original columns
            original_columns = df.columns
            
            # Parse the resource column into a new struct column
            parsed_df = df.withColumn(
                GC.BRONZE_PARSED_RESOURCE_COL_NAME,
                F.from_json(
                    GC.DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_CONTENT_COL, 
                    resource_schema
                )
            )

            # Select all columns from the original DataFrame and only the fields from the new struct column that are not already in the original DataFrame
            final_df = parsed_df.select("*", *(F.col(f"{GC.BRONZE_PARSED_RESOURCE_COL_NAME}." + col).alias(col) for col in parsed_df.select(f"{GC.BRONZE_PARSED_RESOURCE_COL_NAME}.*").columns if col not in original_columns))

            # Drop the new struct column and the fhir resource content column
            final_df = final_df.drop(GC.BRONZE_PARSED_RESOURCE_COL_NAME, 
                                     GC.DEFAULT_BRONZE_FHIR_TABLE_RESOURCE_CONTENT_COL)

            return final_df
        
        except Exception as e:
            error_message = LoggingConstants.SILVER_INGESTION_FAILED_TO_PARSE_RESOURCE_ERROR_MSG.format(
                resource = resource,
                exception_details = str(e)
                )
            
            self._logger.error(error_message)
            raise SilverIngestionFailedError(error_message)
        
    def _process_by_resource_type(self,
                                  df: DataFrame,
                                  epochId: int,
                                  silver_transformation_fn: Callable,
                                  resource: str,
                                  resource_config: Dict
        ) -> DataFrame:
        """
        Filter the DataFrame by the resourceType column and process the data

        Args:
        - df: DataFrame - The streamed DataFrame to ingest
        - epochId: int - The epochId of the batch
        - silver_transformation_fn: Callable - The transformation function to apply on the DataFrame
        - resource: str - The streamed resource to be ingested
        - resource_config: dict - The configuration for the resource. It contains the relative source schema path for the resource 
        """ 
        try:        
            if df.isEmpty():
                self._logger.info(LoggingConstants.SILVER_INGESTION_SKIPPED_NO_RECORDS_INFO_MSG.format(
                    resource=resource,
                    source_table_path=self.source_tables_path,
                    )
                )
                return
            
            _df = self._parse_resource_data_column(
                df=df, 
                resource_config=resource_config, 
                resource=resource
            )
            
            silver_transformation_fn(
                df = _df, 
                batchid = epochId, 
                config = resource_config, 
                target_tables_path = self.target_tables_path,
                collect_metrics_fn = self.collect_target_delta_table_operation_summary_metrics
            )
            
        except Exception as e:
            error_message = LoggingConstants.SILVER_INGESTION_TRANSFORMATION_ERROR_MSG.format(
                resource = resource,
                source_path = self.source_tables_path,
                exception_details = str(e)
                )
            
            self._logger.error(error_message)
            raise SilverIngestionFailedError(error_message)
        
    def _process_resources_with_no_target_tables_or_source_data(self, resources_with_no_source_data: list, silver_transformation_fn: Callable):
        """
        Process resources with no target tables or source data
        
        Args:
        - resources_with_no_source_data: list - The list of resources with no source data
        - silver_transformation_fn: Callable - The transformation function to apply on the DataFrame
        """
        # Call silver_transformation_fn with None Dataframe for resource that do not have source data
        if resources_with_no_source_data:
            self._logger.info(LoggingConstants.FLATTENING_SOURCE_RESOURCES_WITH_NO_DATA.format(resources_with_no_source_data=resources_with_no_source_data))
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(resources_with_no_source_data)) as executor:
                self._logger.info(f"{LoggingConstants.CREATE_SILVER_TABLES_INFO_MSG}")
                none_dataframe_tasks = {executor.submit(silver_transformation_fn,None,0, resource_config, self.target_tables_path): resource_config for resource_config in resources_with_no_source_data}

                # Call Threadpool manager to await till all threads execute
                thread_pool_manager = ThreadPoolManager(spark=self.spark)
                thread_pool_manager.await_all_termination(futures=none_dataframe_tasks)
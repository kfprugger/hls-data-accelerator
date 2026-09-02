# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import os
import glob
from functools import partial
from typing import List

from delta import DeltaTable
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col,
    regexp_extract,
    input_file_name,
    lower,
    from_json,
)
from pyspark.sql.types import StringType
from microsoft.fabric.hls.hds.structured_stream.file_stream_reader import (
    FileStreamReader,
)
from microsoft.fabric.hls.hds.structured_stream.stream_orchestrator import (
    StreamOrchestrator,
    StreamingQueryInfo,
)
from microsoft.fabric.hls.hds.utils.dataframe_utils import (
    append_to_delta_table_using_path,
    validate_checkpoint,
)
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_logging_constants import (
    AIEnrichmentsLoggingConstants as ELC,
)
from microsoft.fabric.hls.hds.global_constants.global_constants import (
    GlobalConstants as GC,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.constants.ai_enrichments_constants import (
    AIEnrichmentsConstants as EC,
)
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import (
    MSSparkUtilsClientBase,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.utils.ai_enrichments_ingestion_utils import (
    AIEnrichmentIngestionUtils as IngestionUtils,
)
from microsoft.fabric.hls.hds.ai_enrichments.core.utils.fhir_resource_extractor import FHIRResourceExtractor
from microsoft.fabric.hls.hds.utils.validation_service import ValidationService
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType

class AIEnrichmentsBronzeIngestionService(BaseRunnableService):
    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        inline_params: dict = None,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        mssparkutils_client: MSSparkUtilsClientBase = None,
    ) -> None:
        """
        Args:
            - spark: spark session
            - workspace_name: Name of the Fabric Workspace
            - solution_name: Name of the HDS-Healthcare data solutions OneLake workload solution
            - admin_lakehouse_name: The lakehouse name of where configuration is located
            - inline_params: Inline parameters that overwrite the administration lakehouse configuration
            - one_lake_endpoint: Default is `onelake.dfs.fabric.microsoft.com`
            - mssparkutils_client: The mssparkutils client
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
        Setup method for the AIEnrichmentsBronzeIngestionService class.
        """
        try:
            
            self._init_configs()
            self._init_paths()
            self._initialize_validation_service()

        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

    def _initialize_validation_service(self):

        self.business_events_lakehouse_name = self.admin_lakehouse_name
        self.validation_config_key = self.parameter_service.get_activity_config_value(GC.VALIDATION_CONFIG_KEY, GC.VALIDATION_CONFIG_BRONZE_KEY)
        self.notebook_name = self.mssparkutils_client.get_runtime_context().get('currentNotebookName')
        self.validation_config_path = self.parameter_service.get_foundation_config_value(
            GC.DATA_VALIDATION_CONFIG_PATH_KEY,
            f"{FolderPath.get_fabric_files_path(workspace_name=self.workspace_name, one_lake_endpoint=self.one_lake_endpoint,lakehouse_name=self.admin_lakehouse_name)}/{GC.PARAMETERS_CONFIGS_FOLDER}/{GC.VALIDATION_CONFIG_FILE}"
        )
        
        
        self.business_events_table_path = self.parameter_service.get_activity_config_value(
            GC.BUSINESS_EVENTS_TABLE_PATH_KEY,
            FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.business_events_lakehouse_name
            )
        )
        
        self.business_events_schema_dir_path = self.parameter_service.get_activity_config_value(
            GC.BUSINESS_EVENTS_SCHEMA_DIR_PATH_KEY,
            f"{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GC.BUSINESS_EVENTS_SCHEMA_ROOT_FOLDER}"
        )
        self.business_events_schema_path = f"{self.business_events_schema_dir_path}/{GC.BUSINESS_EVENTS_TABLE}.avsc"
        
        self.validation_service = ValidationService(
            spark=self.spark,
            workspace_name=self.workspace_name,
            validation_config_path=self.validation_config_path,
            business_events_table_path=self.business_events_table_path,
            business_events_lakehouse_name=self.business_events_lakehouse_name,
            business_events_schema_path=self.business_events_schema_path,
            validation_config_key=self.validation_config_key,
            activity_name=self.notebook_name,
            run_id=self.run_id,
            source_file_path=EC.ENRICHMENT_BRONZE_FULL_FILE_PATH_COLUMN,
            target_lakehouse_name=self.target_lakehouse_name,
            move_failed_files_enabled=True,
            partial_file_movement_enabled= True,
            source_root_path = f"{self.processed_folder_path}/{EC.AI_ENRICHMENTS_MODALITY_NAME}",
            failed_root_path = self.failed_folder_path,
            modality_name = EC.AI_ENRICHMENTS_MODALITY_NAME,
            data_column_name = EC.ENRICHMENT_BRONZE_DATA_COLUMN,
            mssparkutils_client=self.mssparkutils_client
        )

        self.fhir_resource_extractor = FHIRResourceExtractor(
            spark=self.spark,
            mssparkutils_client=self.mssparkutils_client,
            logger=self._logger,
            target_lakehouse_name=self.target_lakehouse_name,
            target_tables_path=self.target_tables_path,
            checkpoint_path=self.checkpoint_path,
            max_structured_streaming_queries=self.max_structured_streaming_queries,
            max_files_per_trigger=self.max_files_per_trigger,
        )
            
    def _init_configs(self):
        self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(
            GC.BRONZE_LAKEHOUSE_ID_KEY
        )
        self.landing_zone_lakehouse_id = self.parameter_service.get_activity_config_value(
            EC.ENRICHMENT_LANDING_ZONE_LAKEHOUSE_ID_KEY, self.target_lakehouse_name
        )
        self.max_files_per_trigger = self.parameter_service.get_activity_config_value(
            GC.MAX_FILES_PER_TRIGGER_KEY,
            GC.DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_BRONZE,
            "int",
        )
        self.target_bronze_table_name = self.parameter_service.get_activity_config_value(
            EC.ENRICHMENT_TARGET_BRONZE_TABLE_NAME_KEY,
            EC.DEFAULT_ENRICHMENT_TARGET_BRONZE_TABLE_NAME,
        )
        
        self.max_structured_streaming_queries = (
            self.parameter_service.get_activity_config_value(
                GC.MAX_STRUCTURED_STREAMING_QUERIES_KEY,
                GC.DEFAULT_NUMBER_OF_MAX_STREAMING_QUERIES_BRONZE,
                "int",
            )
        )

        self.flatten_fhir_resource_lakehouse_id = self.parameter_service.get_foundation_config_value(
            GC.BRONZE_LAKEHOUSE_ID_KEY
        )

        self.extract_fhir_resources_from_object_enrichments =  self.parameter_service.get_activity_config_value(GC.AI_ENRICHMENT_EXTRACT_FHIR_RESOURCES_FROM_ENRICHMENT_OBJECT_KEY, False, value_type="bool")
        
    def _init_paths(self):
        
        self.source_root_path = self.parameter_service.get_activity_config_value(GC.SOURCE_PATH_PATTERN_KEY,
        FolderPath.get_fabric_files_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.landing_zone_lakehouse_id,
        ))

        self.config_files_root_path = (
            FolderPath.get_fabric_workload_files_root_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                solution_name=self.solution_name,
            )
        )
        self.ai_enrichment_resource_schema_path = (
            self.parameter_service.get_activity_config_value(
                GC.AI_ENRICHMENT_RESOURCE_SCHEMA_PATH_KEY,
                FolderPath.get_fabric_workload_files_ai_enrichment_resource_types_folder_path(
                    root_path=self.config_files_root_path
                ),
            )
        )
        self.target_tables_path = self.parameter_service.get_activity_config_value(
            GC.TARGET_TABLES_PATH_KEY,
            FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name,
            ),
        )
        self.target_table_path = (
            f"{self.target_tables_path}/{self.target_bronze_table_name}"
        )
        self.checkpoint_path = self.parameter_service.get_activity_config_value(
            GC.CHECKPOINT_PATH_KEY,
            FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                root_path=self.config_files_root_path,
                checkpoint_folder_name=self.target_lakehouse_name,
            ),
        )

        self.processed_folder_path = f"{self.source_root_path}/{GC.PROCESS_FOLDER}"
        self.failed_folder_path = f"{self.source_root_path}/{GC.FAILED_FOLDER}"   

    def _execute(self, **kwargs) -> None:
        """
        Executes the AI Enrichments bronze ingestion service.       
        """
        if self.extract_fhir_resources_from_object_enrichments:
            self._logger.info(f"Starting FHIR resource extraction from object enrichments")
            self.fhir_resource_extractor.extract_fhir_resources(run_id=self.run_id)
        
        self.__ingest()

    def __ingest(self) -> None:
        """
        Ingests JSON files from the source path pattern as a streaming DataFrame 
        and writes valid data to Delta Lake.
        """
        try:
            # This is needed to support seamless file movement while validating the files.
            self.spark.conf.set("spark.sql.files.ignoreMissingFiles", "true")
                    
            # Load the common schema for enrichment data to validate against
            common_schema_path = (
                f"{self.ai_enrichment_resource_schema_path}"
                f"/{EC.ENRICHMENT_COMMON_SCHEMA_NAME}.json"
            )
            self.common_json_schema = IngestionUtils.get_schema_from_json_file(
                self.spark, common_schema_path
            )
            stream_orchestrator = StreamOrchestrator(
                self.spark, self.max_structured_streaming_queries
            )

            batch_fn = partial(self._process_batch)
            checkpoint_path = f"{self.checkpoint_path}/{EC.ENRICHMENT_BRONZE_CHECKPOINT_FOLDER}/{self.target_bronze_table_name}"

            validate_checkpoint(
                spark=self.spark,
                logger=self._logger,
                target_table_path=self.target_table_path,
                checkpoint_path=checkpoint_path,
                mssparkutils_client=self.mssparkutils_client,
                resource_name=self.target_bronze_table_name,
            )

            for file_type in EC.AI_ENRICHMENTS_SUPPORTED_FILE_TYPES:
                file_extension = f".{file_type}"
                path_glob_filter = f"*.{file_type}"

                file_stream_reader = FileStreamReader(
                    self.spark,
                    maxFilesPerTrigger=self.max_files_per_trigger,
                    recursiveFileLookup="true",
                    pathGlobFilter=path_glob_filter,
                )

                resource_streaming_df = (
                    file_stream_reader.set_up_streaming_text_file(
                        streaming_path=self.processed_folder_path
                    )
                    .filter(input_file_name().endswith(file_extension))
                )

                streaming_query_info = StreamingQueryInfo(
                    query_name=(
                        f"ai_enrichment_processing.{self.target_bronze_table_name}-{file_type}"
                    ),
                    checkpoint_path=checkpoint_path,
                    streaming_dataframe=resource_streaming_df,
                    batch_fn=batch_fn,
                    data_format="delta",
                )
                stream_orchestrator.enqueue_streaming_query(streaming_query_info)

            stream_orchestrator.await_all()
            
        except Exception as ex:
                message = ELC.AI_ENRICHMENT_BRONZE_INGESTION_EXECUTION_ERROR.format(error=ex)
                self._logger.error(message)
                raise ex
        finally:  
            self.spark.conf.set("spark.sql.files.ignoreMissingFiles", "false")

    def _process_batch(self, df: DataFrame, batch_id: int):
        """Processes each DataFrame batch, separating valid and invalid rows."""
        
        df = self._add_metadata_columns(df)

        validated_dict_dfs = self.validation_service.validate_df(df= df, table_name= self.target_bronze_table_name)
        
        valid_df = validated_dict_dfs[GC.VALIDATION_DF_SUCCESSES_KEY]
        error_df = validated_dict_dfs[GC.VALIDATION_DF_ERRORS_KEY]
        
        valid_df = valid_df.select(
            EC.ENRICHMENT_BRONZE_PATIENT_ID_COLUMN,
            EC.ENRICHMENT_BRONZE_DATA_COLUMN,
            EC.ENRICHMENT_BRONZE_ENRICHMENT_TYPE_COLUMN,
            EC.ENRICHMENT_BRONZE_FULL_FILE_PATH_COLUMN,
        )

        append_to_delta_table_using_path(
            df_to_process=valid_df,
            delta_table_path=self.target_table_path,
            logger=self._logger,
        )
        
        total_processed_source_files = df.select(EC.ENRICHMENT_BRONZE_FULL_FILE_PATH_COLUMN).distinct().count()
        total_records_count = df.count()       
        valid_records_count = valid_df.count()
        failed_records_count = error_df.count()
        self.execution_metrics_collector.accumulate(
            accumulator_activity_id = self.get_execution_metrics_accumulator_activity_id(),
            metrics = {"numSourceFiles": total_processed_source_files,
                       "numTargetRecords": total_records_count,
                       "activityAttributes": {"successCount": valid_records_count,
                                              "failedCount": failed_records_count}
            }
        )       
        
        if(error_df.count() > 0):
            self.validation_service.partial_file_movement_from_df(error_df)
        
    def _add_metadata_columns(self, df: DataFrame) -> DataFrame:
        df = df.withColumn(
            EC.ENRICHMENT_BRONZE_FULL_FILE_PATH_COLUMN, input_file_name()
        )
        df = df.withColumn(
            EC.ENRICHMENT_BRONZE_ENRICHMENT_TYPE_COLUMN,
            lower(
                regexp_extract(
                    col(EC.ENRICHMENT_BRONZE_FULL_FILE_PATH_COLUMN),
                    EC.ENRICHMENT_BRONZE_PARENT_FOLDER_REGEX,
                    1,
                )
            ),
        )
        df = df.withColumn(
            EC.ENRICHMENT_BRONZE_DATA_COLUMN,
            col(EC.ENRICHMENT_BRONZE_VALUE_COLUMN).cast(StringType()),
        )
        
        df = df.withColumn(
            EC.ENRICHMENT_BRONZE_PARSED_DATA_COLUMN,
            from_json(col(EC.ENRICHMENT_BRONZE_DATA_COLUMN), self.common_json_schema)
        )
        
        df = df.withColumn(
            EC.ENRICHMENT_BRONZE_CONTEXT_COLUMN,
            col(EC.ENRICHMENT_BRONZE_PARSED_CONTEXT_COLUMN)
        )
        
        df = df.withColumn(
            EC.ENRICHMENT_BRONZE_PATIENT_ID_COLUMN,
            col(EC.ENRICHMENT_BRONZE_PARSED_PATIENT_ID_COLUMN),
        )
        
        return df
    
    def _setup_execution_metadata(self) -> ExecutionMetadata:
        target_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name)
        return ExecutionMetadata(
            sourceType=ExecutionDataType.file,
            sourcePath=self.source_root_path,
            targetType=ExecutionDataType.deltaTable,
            targetLakehouseName=target_lakehouse_properties.get("displayName"),
            targetLakehouseIdentifier=target_lakehouse_properties.get("id"),
            targetPath=self.target_tables_path
        )
        
    def _get_internal_activity_name(self) -> str:
        return EC.ENRICHMENT_BRONZE_INGESTION_ACTIVITY_NAME


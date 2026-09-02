# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

from functools import partial
from tabnanny import check
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import  StringType
from microsoft.fabric.hls.hds.structured_stream.file_stream_reader import FileStreamReader
from microsoft.fabric.hls.hds.structured_stream.stream_orchestrator import StreamOrchestrator, StreamingQueryInfo
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_to_delta_table_using_path, validate_checkpoint
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType

class DaxBronzeIngestionService(BaseRunnableService):
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
        
        super().__init__(
                spark=spark,
                workspace_name=workspace_name,
                solution_name=solution_name,
                admin_lakehouse_name=admin_lakehouse_name,
                inline_params=inline_params,
                one_lake_endpoint=one_lake_endpoint,
                mssparkutils_client=mssparkutils_client)

    def _setup(self):
        self._initialize_parameters()
        self._initialize_paths()
    
    def _initialize_parameters(self):
        self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(
            GC.BRONZE_LAKEHOUSE_ID_KEY)

        self.max_files_per_trigger = self.parameter_service.get_activity_config_value(
            GC.MAX_FILES_PER_TRIGGER_KEY,
            GC.DEFAULT_NUMBER_OF_FILES_PER_TRIGGER_BRONZE,
            "int"
        )

        self.target_table_name = self.parameter_service.get_activity_config_value(
            GC.DAX_TARGET_TABLE_NAME_KEY,
            GC.DEFAULT_DAX_TARGET_BRONZE_TABLE_NAME
        )

        self.max_structured_streaming_queries = self.parameter_service.get_activity_config_value(
            GC.MAX_STRUCTURED_STREAMING_QUERIES_KEY,
            GC.DEFAULT_NUMBER_OF_MAX_STREAMING_QUERIES_BRONZE,
            "int"
        )

    def _initialize_paths(self):
        try:
            
            self.source_path = self.parameter_service.get_activity_config_value(
                GC.SOURCE_PATH_KEY,
                FolderPath.get_fabric_files_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name
                )
            )

            self.source_path_pattern = f"{self.source_path}/{GC.DEFAULT_DAX_COPILOT_DATA_FOLDER}"

            self.target_tables_path = self.parameter_service.get_activity_config_value(
                GC.TARGET_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.target_lakehouse_name,
                )
            )

            self.target_table_path = f"{self.target_tables_path}/{self.target_table_name}"

            self.checkpoint_path = self.parameter_service.get_activity_config_value(
                GC.CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(root_path=self.config_files_root_path,
                                                                            checkpoint_folder_name=self.target_lakehouse_name)
            )
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

    def __ingest(self) -> None:
        """
        Ingests JSON files from the source path pattern as a streaming DataFrame and writes to Delta Lake.
        """
        stream_orchestrator = StreamOrchestrator(
            self.spark, self.max_structured_streaming_queries)

        dax_file_extension = GC.DEFAULT_DAX_FILES_PATTERN
        # initializes the FileStreamReader
        file_stream_reader = FileStreamReader(self.spark,
                                              maxFilesPerTrigger=self.max_files_per_trigger,
                                              recursiveFileLookup="true",
                                              pathGlobFilter=dax_file_extension)

        streaming_dataframe = file_stream_reader.set_up_streaming_text_file(
            streaming_path=self.source_path_pattern
        )

        streaming_dataframe = self._enrich_dax_input_data(streaming_dataframe)
        batch_fn = partial(self._append_to_delta_table)

        checkpoint_path = f"{self.checkpoint_path}/{self.target_table_name}"
        validate_checkpoint(spark=self.spark,
                            logger=self._logger,
                            target_table_path=self.target_table_path,
                            checkpoint_path=checkpoint_path,
                            mssparkutils_client=self.mssparkutils_client,
                            resource_name=self.target_table_name)

        streaming_query_info = StreamingQueryInfo(
            query_name=f"DAX-{self.target_table_name}",
            checkpoint_path=checkpoint_path,
            streaming_dataframe=streaming_dataframe,
            batch_fn=batch_fn,
            data_format="delta"
        )
        stream_orchestrator.enqueue_streaming_query(streaming_query_info)
        stream_orchestrator.await_all()

    def _enrich_dax_input_data(self, df: DataFrame) -> DataFrame:
        """
        Adds necessary metadata columns to the DataFrame.
        Args:
            df (DataFrame): The DataFrame to enrich.
        Returns:
            DataFrame: The enriched DataFrame.
        """
        df = df.withColumn(GC.DAX_BRONZE_FILE_CONTENT_COLUMN, col(
            GC.DAX_BRONZE_VALUE_COLUMN).cast(StringType()))
        
        df = df.withColumn(
            GC.DAX_BRONZE_FULL_FILE_PATH_COLUMN, input_file_name())
        
        df = df.withColumn(GC.DAX_BRONZE_FILE_TYPE_COLUMN, regexp_extract(
            col(GC.DAX_BRONZE_FULL_FILE_PATH_COLUMN), GC.DAX_BRONZE_FILE_TYPE_REGEX, 1))
        
        df = df.withColumn(GC.DAX_BRONZE_SOURCE_SYSTEM_COLUMN, regexp_extract(
            col(GC.DAX_BRONZE_FULL_FILE_PATH_COLUMN), GC.DAX_BRONZE_SOURCE_SYSTEM_REGEX, 1))
        
        df = df.select(
            GC.DAX_BRONZE_FILE_CONTENT_COLUMN,
            GC.DAX_BRONZE_FULL_FILE_PATH_COLUMN,
            GC.DAX_BRONZE_SOURCE_SYSTEM_COLUMN,
            GC.DAX_BRONZE_FILE_TYPE_COLUMN)

        return df

    def _append_to_delta_table(
        self, df: DataFrame, batchid: int
    ):
        """
        Appends data to the appropriate Delta table.
        Args:
            df (DataFrame): The DataFrame to append.
            batch_id: The batch id.
        """
        self._logger.info(LC.BEGAN_EXECUTION_INFO_MSG)

        # Append  data to the original table
        append_to_delta_table_using_path(
            df_to_process=df,
            delta_table_path=f"{self.target_table_path}",
            logger=self._logger,
        )
        
        total_processed_source_files = df.select(GC.DAX_BRONZE_FULL_FILE_PATH_COLUMN).distinct().count()
        total_target_records = df.count()
        self.execution_metrics_collector.accumulate(
            accumulator_activity_id = self.get_execution_metrics_accumulator_activity_id(),
            metrics = {"numSourceFiles": total_processed_source_files,
                        "numTargetRecords": total_target_records}
        )

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        target_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name)
        return ExecutionMetadata(
            sourceType=ExecutionDataType.file,
            sourcePath=self.source_path_pattern,
            sourceLakehouseName="",
            sourceLakehouseIdentifier="",
            targetType=ExecutionDataType.deltaTable,
            targetPath=self.target_table_path,
            targetLakehouseName=target_lakehouse_properties.get("displayName"),
            targetLakehouseIdentifier=target_lakehouse_properties.get("id")
        )
        
    def _get_internal_activity_name(self) -> str:
        return GC.DAX_BRONZE_INGESTION_ACTIVITY_NAME
    
    def _execute(self, **kwargs):
        self.__ingest()
        
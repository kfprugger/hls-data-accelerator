# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import os
import pandas as pd
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.orchestrator import Orchestrator
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.global_constants.logging_constants import (
    LoggingConstants as LC,
)
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType
from microsoft.fabric.hls.hds.errors.sdoh_bronze_ingestion_failed_error import SDOHBronzeIngestionFailedError

class SDOHBronzeIngestionService(BaseRunnableService):

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
            - admin_lakehouse_name (str): The lakehouse name where the administration configurations are located
            - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
            - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
            - mssparkutils_client: MSSpark client instance or test instance
        """
        super().__init__(
            spark=spark,
            workspace_name=workspace_name,
            solution_name=solution_name,
            admin_lakehouse_name=admin_lakehouse_name,
            inline_params=inline_params,
            one_lake_endpoint=one_lake_endpoint,
            mssparkutils_client=mssparkutils_client
        )

    def _setup(self) -> None:
        try:
            self.source_lakehouse_name = self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
            self.target_tables_path = FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.target_lakehouse_name
                )
            self.fabric_files_path = FolderPath.get_fabric_files_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name
            )
            self.sdoh_drop_folder_path = os.path.join(self.fabric_files_path, GC.DROP_FOLDER, GC.SDOH_DEFAULT_BRONZE_INGESTION_PATH)
            self.sdoh_process_folder_path =self.parameter_service.get_activity_config_value(
                GC.SDOH_PROCESS_FOLDER_PATH_KEY,
                os.path.join(self.fabric_files_path, GC.PROCESS_FOLDER, GC.SDOH_DEFAULT_BRONZE_INGESTION_PATH)
            )
            self.sdoh_failed_folder_path = os.path.join(self.fabric_files_path, GC.FAILED_FOLDER, GC.SDOH_DEFAULT_BRONZE_INGESTION_PATH)

            self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                solution_name=self.solution_name)
            self.checkpoint_path = self.parameter_service.get_activity_config_value(
                GC.CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                    root_path=self.config_files_root_path,
                    checkpoint_folder_name=f"{GC.SDOH_FOLDER}/{GC.STREAMING_CHECKPOINT_FOLDER}"
                )
            )
            self.business_events_ingestion_service = BusinessEventsIngestion(
                spark = self.spark,
                workspace_name = self.workspace_name,
                one_lake_endpoint = self.one_lake_endpoint,
                lakehouse_name = self.admin_lakehouse_name,
                solution_name = self.solution_name,
                parameter_service = self.parameter_service
                )
            
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.file,
            sourcePath=self.sdoh_process_folder_path,
            targetType=ExecutionDataType.deltaTable,
            targetPath=self.target_tables_path,
            sourceLakehouseName=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("id"),
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("id"),
        )

    def _get_internal_activity_name(self) -> str:
        return GC.SDOH_BRONZE_INGESTION_ACTIVITY_NAME

    def _execute(self, **kwargs) -> None:
        try:
            self._ingest_logic()
        except Exception as ex:
            raise SDOHBronzeIngestionFailedError(str(ex))
    
    def collect_source_and_target_metrics_fn(self, metrics: dict, delta_table_path: str) -> None:
        """
        This function is used to collect source and target metrics for the SDOH bronze ingestion process.
        Args:
            - metrics (dict): These metics are collected from the source and used to log the source operation summary metrics
            - delta_table_path (str): These metics are collected from the target and used to log the target operation summary metrics
        """
        if metrics is not None:
            """
            To collect the source metrics only
            """
            self.execution_metrics_collector.accumulate(
                accumulator_activity_id=self.get_execution_metrics_accumulator_activity_id(),
                metrics=metrics
            )
            
        if delta_table_path is not None:
            """        
            To collect the target metrics only
            """
            self.collect_target_delta_table_operation_summary_metrics(target_table_path=delta_table_path)

    def _ingest_logic(self) -> None:
        """
        Entry point for SDOH bronze ingestion.

        This method builds necessary paths and calls the orchestrator for the bronze ingestion process.      
        """
        orchestrator = Orchestrator(
                            self.spark,
                            self.source_lakehouse_name,
                            self.target_lakehouse_name,
                            self.target_tables_path,
                            self.sdoh_drop_folder_path,
                            self.sdoh_process_folder_path,
                            self.sdoh_failed_folder_path,
                            self.business_events_ingestion_service,
                            self.checkpoint_path,
                            self.mssparkutils_client,
                            self.collect_source_and_target_metrics_fn
                            )        
        orchestrator.start_ingestion()
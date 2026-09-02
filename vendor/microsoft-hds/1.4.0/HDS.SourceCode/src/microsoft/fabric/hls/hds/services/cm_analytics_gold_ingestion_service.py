# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import traceback, uuid
from typing import Callable
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.services.dtt_workflow_service import DTTWorkflowService
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType
from microsoft.fabric.hls.hds.errors.cma_gold_ingestion_failed_error import CMAGoldIngestionFailedError
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion

class CMAnalyticsGoldIngestionService(BaseRunnableService):
    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        mssparkutils_client: MSSparkUtilsClientBase = None,
        inline_params: dict = None) -> None:
        """
        Uses DTT library to transform and ingest data into CMA(Gold tables)
        Args:
        - spark: spark session
        - workspace_name - str: Name of the Fabric Workspace
        - solution_name: Name of the DMH OneLake workload solution
        - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
        - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
        - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
        - mssparkutils_client: MSSparkUtilsClientBase, spark utils client
        """
        super().__init__(spark=spark,
                         workspace_name=workspace_name,
                         solution_name=solution_name,
                         admin_lakehouse_name=admin_lakehouse_name,
                         inline_params=inline_params,
                         one_lake_endpoint=one_lake_endpoint,
                         mssparkutils_client=mssparkutils_client)

        self._setup()    
    
    def _setup(self) -> None:
        """
        Initializes parameters, paths, and configurations for the ingestion process.
        """
        # Disable metrics poller as we are collecting metrics at the end of the activity
        self.metrics_polling_interval_min = 0 
        
        self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)
        self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.CM_ANALYTICS_LAKEHOUSE_ID_KEY)
        
        try:    
            self.config_files_root_path = (
                FolderPath.get_fabric_workload_files_root_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    solution_name=self.solution_name,
                )
            )
            self.source_tables_path = FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.source_lakehouse_name,
            )

            self.cma_tables_path = FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name,
            )
            
            self.cma_gold_config_path = self.parameter_service.get_activity_config_value(
                GC.CMA_GOLD_CONFIG_PATH_KEY,
                FolderPath.get_fabric_workload_files_cma_config_folder_path(
                    root_path=self.config_files_root_path
                ),
            )
            
            # Validate required parameters
            if not self.source_tables_path or not self.cma_tables_path:
                error_msg = "Missing required lakehouse paths for ingestion."
                self._logger.error(error_msg)
                raise CMAGoldIngestionFailedError(error_msg)

            self.dtt_secondary_lake_path = (
                FolderPath.get_fabric_workload_files_cma_dtt_secondary_lake_folder_path(
                    root_path=self.config_files_root_path
                )
            )

            self.dtt_dir = FolderPath.get_fabric_workload_cma_dtt_file_path(
                root_path=self.config_files_root_path
            )
            
            self.dmf_config_path = f"{self.dtt_dir}/{GC.DMF_CONFIG_PATH}"
            self.env_config_path = f"{self.dtt_dir}/{GC.ENV_CONFIG_PATH}"
            self.rmt_config_path = f"{self.dtt_dir}/{GC.RMT_CONFIG_PATH}"
            
            self.rmt_mapping_input_dir = FolderPath.get_fabric_workload_files_cma_rmt_mapping_folder_path(
                root_path=self.config_files_root_path
            )
            
            self.business_events_ingestion_service = BusinessEventsIngestion(
                spark = self.spark,
                workspace_name = self.workspace_name,
                one_lake_endpoint = self.one_lake_endpoint,
                lakehouse_name = self.admin_lakehouse_name,
                solution_name = self.solution_name,
                parameter_service = self.parameter_service
                )
            
            # db config to read src storage, check if it exists
            self.dtt_env_config = f"""{{
                "storage": {{
                    "source": {{
                        "entities": {{
                            "default": {{
                                "location": "{self.source_tables_path}",
                                "format": "delta"
                            }}
                        }}
                    }},
                    "target": {{
                        "entities": {{
                            "default": {{
                                "location": "{self.cma_tables_path}",
                                "format": "delta"
                            }}
                        }}
                    }},
                    "secondary_lake": {{
                        "location": "{self.dtt_secondary_lake_path}"
                    }}
                }}
            }}"""

        except Exception as ex:
            self._logger.error(f"Error during setup: {str(ex)}")
            raise CMAGoldIngestionFailedError(f"Setup failed: {str(ex)}")

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        """
        Sets up execution metadata for tracking and monitoring ingestion.
        """
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
            targetPath=self.cma_tables_path
        )

    def _get_internal_activity_name(self) -> str:
        return GC.CM_ANALYTICS_GOLD_INGESTION_ACTIVITY_NAME
    
    def _execute(self, **kwargs) -> None:
        """
        Executes the GoldIngestionService    
        Args:
            transformation_fn (Callable, optional): The transformation function to be executed. Defaults to None.
        """
        try:
            self.__ingest()
        except  Exception as ex:
            message = f"{LC.CMA_TRANSFORMATION_EXCEPTION_ERROR_MSG.format(str(ex), traceback.print_exc())}"
            self._logger.error(message)
            new_row = self.business_events_ingestion_service.create_new_business_event_row(
                id=str(uuid.uuid4()), 
                activityName=GC.CMA_GOLD_INGESTION_ACTIVITY_NOTEBOOK,
                targetFilePath=self.cma_tables_path, 
                sourceFilePath=self.source_tables_path,                 
                targetLakehouseName=self.target_lakehouse_name,
                sourceLakehouseName=self.source_lakehouse_name, 
                severity=GC.ERROR, 
                eventType=GC.CMA_TRANSORMATION_AND_INGESTION_TO_GOLD_USING_DTT, 
                message=message, 
                active=True
            )
            self.business_events_ingestion_service.insert_business_events([new_row])
            raise CMAGoldIngestionFailedError(message)
        
    def __ingest(self):
        """Using DTT ingest source data into CMA tables"""

        try:
            self.__dtt_workflow()
            target_tables = Utils.get_target_anchor_tables_from_dtt_config(
                spark=self.spark,
                dtt_config_path=f"{self.cma_gold_config_path}/{GC.CM_ANALYTICS_DTT_ADAPTER_FILE}"
            )
            self.collect_all_target_tables_metrics(
                table_names=target_tables, 
                target_tables_root_path=self.cma_tables_path
            )
            
        except Exception as ex:
            self._logger.error(
                f"{LC.CMA_TRANSFORMATION_EXCEPTION_ERROR_MSG.format(str(ex), traceback.print_exc())}"
            )
            raise CMAGoldIngestionFailedError(f"CMA Gold ingestion failed: {str(ex)}")

    def __dtt_workflow(self):
        """Invokes the dtt workflow"""
        rmt_mapping_input_file_path = f"{self.rmt_mapping_input_dir}/concept.json"
        rmt_mapping_folder_path = [f"{self.rmt_mapping_input_dir}"]

        self.mssparkutils_client.fs_put(self.env_config_path, self.dtt_env_config, overwrite=True)

        
        dtt_adapter = f"{self.cma_gold_config_path}/{GC.CM_ANALYTICS_DTT_ADAPTER_FILE}"
        db_target_schema = f"{self.cma_gold_config_path}/{GC.DB_TARGET_SCHEMA}"
        db_target_schema_config = (
            f"{self.cma_gold_config_path}/{GC.DB_TARGET_SCHEMA_CONFIG}"
        )
        db_semantics = f"{self.cma_gold_config_path}/{GC.DB_SEMANTICS}"
        db_semantics_config = (
            f"{self.cma_gold_config_path}/{GC.DB_SEMANTICS_CONFIG}"
        )
        
        config_files = {
            "adaptor_file_location": dtt_adapter,
            "target_db_semantics_file_location": db_semantics,
            "env_config_file_location": self.env_config_path,
            "target_db_schema_file_location": db_target_schema,
            "db_schema_config_location": db_target_schema_config,           
            "target_db_semantics_config_file_location": db_semantics_config,
        }
        
        dtt_workflow = DTTWorkflowService( 
            spark=self.spark,   
            rmt_out_path=self.rmt_config_path,
            dtt_out_path=self.dmf_config_path,
            config_files=config_files,
            mssparkutils_client=self.mssparkutils_client,
        )
        dtt_workflow.execute_dtt_workflow()
# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import traceback, uuid
from pyspark.sql import SparkSession
from typing import Dict
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import (
    LoggingConstants as LC,
)
from microsoft.fabric.hls.hds.sdoh.bronze_ingestion.constants import SdohConstants
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.services.dtt_workflow_service import (
    DTTWorkflowService,
)
from microsoft.fabric.hls.hds.sdoh.generate_dtt_configurations.generate_dtt_adapter_configuration import DTTAdapterConfigurationGenerator
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType
from microsoft.fabric.hls.hds.errors.sdoh_silver_ingestion_failed_error import SDOHSilverIngestionFailedError
from microsoft.fabric.hls.hds.utils.extension_parser import ExtensionParser

class SDOHSilverIngestionService(BaseRunnableService):

    def __init__(self,
            spark: SparkSession,
            workspace_name: str,
            solution_name: str,
            admin_lakehouse_name: str,
            inline_params: dict = None,
            one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
            mssparkutils_client: MSSparkUtilsClientBase = None) -> None:
        """
        Initializes the SDOHSilverIngestionService.

        Args:
        - spark (SparkSession): The Spark session.
        - workspace_name (str): Name of the Fabric Workspace.
        - solution_name (str): Name of the DMH OneLake workload solution.
        - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
        - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
        - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`.
        - mssparkutils_client: MSSpark client instance or test instance

        Raises:
        - Exception: If there is an error initializing the SDOHSilverIngestionService.

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
        """Sets up the SDOHSilverIngestionService.""" 
        # Disable metrics poller as we are collecting metrics at the end of the activity
        self.metrics_polling_interval_min = 0 
        ExtensionParser.register(self.spark)
        
        try:
            self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
            self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)
            self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                solution_name=self.solution_name
            )
            self.source_tables_path = FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.source_lakehouse_name
            )
            self.sdoh_tables_path = FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name)
            self.sdoh_files_path=FolderPath.get_fabric_files_path( 
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name)
            self.sdoh_config_path = self.parameter_service.get_activity_config_value(
                GC.SDOH_CONFIG_PATH_KEY,
                FolderPath.get_fabric_workload_files_sdoh_config_folder_path(root_path=self.config_files_root_path),
            )
            self.dtt_secondary_lake_path = (
                FolderPath.get_fabric_workload_files_sdoh_dtt_secondary_lake_folder_path(
                    root_path=self.config_files_root_path
                )
            )
            self.dmf_config_path = FolderPath.get_sdoh_dmf_configuration_files(root_path=self.config_files_root_path)
            self.rmt_config_path = FolderPath.get_sdoh_rmt_configuration_files(root_path=self.config_files_root_path)
            self.env_config_path = FolderPath.get_sdoh_environment_configuration_file(root_path=self.config_files_root_path)
            self.rmt_reference_tables_dir = FolderPath.get_sdoh_fabric_workload_files_rmt_mapping_folder_path(root_path=self.config_files_root_path)     
            self.dmf_adapter_config_path = FolderPath.get_sdoh_dmf_adapter_configuration_files(root_path=self.config_files_root_path)
            
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
            raise SDOHSilverIngestionFailedError(str(ex))
        
        self.dtt_env_config = f"""{{
            "storage": {{
                "target": {{
                    "entities": {{
                        "default": {{
                            "location": "{self.sdoh_tables_path}",
                            "format": "delta"
                        }}
                    }}
                }},
                "secondary_lake": {{
                    "location": "{self.dtt_secondary_lake_path}"
                }}    
            }}
        }}"""
        self.mssparkutils_client.fs_put(self.env_config_path, self.dtt_env_config, overwrite=True)
        self.placeholder_values: Dict = {
            "{{dtt_source}}": f"`{self.source_lakehouse_name}`"
        }
   
    def _setup_execution_metadata(self) -> ExecutionMetadata:
        """Sets up execution metadata for metrics collection."""
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourcePath=self.source_tables_path,
            targetType=ExecutionDataType.deltaTable, 
            targetPath=self.sdoh_tables_path,
            sourceLakehouseName=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("id"),
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("id")
        )

    def _get_internal_activity_name(self) -> str:
        """Returns the internal activity name."""
        return GC.SDOH_SILVER_INGESTION_ACTIVITY_NAME

    def _execute(self, **kwargs) -> None:
        """Executes the SDOH silver ingestion process."""
        try:
            self.ingest()
        except Exception as ex:
            message = f"{LC.SDOH_TRANSFORMATION_EXCEPTION_ERROR_MSG.format(str(ex), traceback.print_exc())}"
            self._logger.error(message)
            new_row = self.business_events_ingestion_service.create_new_business_event_row(
                id=str(uuid.uuid4()), 
                activityName=GC.SDOH_SILVER_INGESTION_ACTIVITY_NOTEBOOK,
                targetFilePath=self.sdoh_tables_path, 
                sourceFilePath=self.source_tables_path,                 
                targetLakehouseName=self.target_lakehouse_name,
                sourceLakehouseName=self.source_lakehouse_name, 
                severity=GC.ERROR, 
                eventType=GC.SDOH_PROCESS_TABLES_FROM_BRONZE_TO_SILVER, 
                message=message, 
                active=True
            )
            self.business_events_ingestion_service.insert_business_events([new_row])
            raise SDOHSilverIngestionFailedError(message)

    def ingest(self):
        """Using DTT ingest source data into SDOH tables"""
        try:
            self.__dtt_workflow()
            self.collect_all_target_tables_metrics(
                table_names=SdohConstants.SDOH_TARGET_TABLES_LIST, 
                target_tables_root_path=self.sdoh_tables_path
            )
        except Exception as ex:
            raise SDOHSilverIngestionFailedError(str(ex))
    
    def __dtt_workflow(self):
        """Invokes the dtt workflow"""
        rmt_mapping_folder_paths=[f"{self.rmt_reference_tables_dir}"]
        rmt_data_folder_paths=[f"{self.rmt_reference_tables_dir}"]

        adapter = f"{self.sdoh_config_path}/{GC.SDOH_DMF_ADAPTER_FILE}"
        db_target_schema = f"{self.sdoh_config_path}/{GC.SDOH_DB_TARGET_SCHEMA}"
        db_target_schema_config = (
            f"{self.sdoh_config_path}/{GC.SDOH_DB_TARGET_SCHEMA_CONFIG}"
        )
        db_semantics = f"{self.sdoh_config_path}/{GC.SDOH_DB_SEMANTICS}"
        db_semantics_config = (
            f"{self.sdoh_config_path}/{GC.SDOH_DB_SEMANTICS_CONFIG}"
        )
        dtt_adapter = self.spark.read.text(adapter, wholetext=True).collect()[0][0]
        generate_dtt_adapter_configuration = DTTAdapterConfigurationGenerator(
            spark=self.spark,
            source_lakehouse_name=self.source_lakehouse_name,
            target_lakehouse_name=self.target_lakehouse_name,
            bronze_database_name=self.source_lakehouse_name,
            sdoh_config_file_path=f"{self.sdoh_config_path}",
            adapterContent=dtt_adapter,
            business_events_ingestion_service=self.business_events_ingestion_service,
            )
        adapterContent=generate_dtt_adapter_configuration.finalize()
        for placeholder in self.placeholder_values:
            adapterContent = adapterContent.replace(
                placeholder, self.placeholder_values[placeholder])
      
        self.mssparkutils_client.fs_put(self.dmf_adapter_config_path, adapterContent, overwrite=True)
        
        config_files = {
            "adaptor_file_content": adapterContent,
            "target_db_semantics_file_location": db_semantics,
            "env_config_file_location": self.env_config_path,
            "target_db_schema_file_location": db_target_schema,
            "db_schema_config_location": db_target_schema_config,           
            "target_db_semantics_config_file_location": db_semantics_config,
            "rmt_target_path":self.sdoh_tables_path,
        }
        
        
        dtt_workflow = DTTWorkflowService( 
            spark=self.spark,   
            rmt_out_path=self.rmt_config_path,
            dtt_out_path=self.dmf_config_path,
            config_files=config_files,
            rmt_ordered_mapping_definitions_folders=rmt_mapping_folder_paths,
            rmt_reference_tables_folders_paths=rmt_data_folder_paths,
            executeRMTReferenceTable=False,
            mssparkutils_client=self.mssparkutils_client,
        )
        dtt_workflow.execute_dtt_workflow()
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
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType
from microsoft.fabric.hls.hds.errors.idm_silver_ingestion_service_failed_error import IDMSilverIngestionFailedError
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.services.dtt_workflow_service import (
    DTTWorkflowService,
)
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion

class IDMSilverIngestionService(BaseRunnableService):
    def __init__(self,
                 spark: SparkSession,
                 workspace_name: str,
                 solution_name: str,
                 admin_lakehouse_name: str,
                 inline_params: dict = None,
                 one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
                 mssparkutils_client: MSSparkUtilsClientBase = None):
        """
        Uses DTT library to transform and ingest marketing data into Silver Lake
        Args:
        - spark: spark session
        - workspace_name - str: Name of the Fabric Workspace
        - solution_name: Name of the DMH OneLake workload solution
        - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
        - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
        - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
         
        """
        super().__init__(
            spark = spark,
            workspace_name = workspace_name,
            solution_name = solution_name,
            admin_lakehouse_name = admin_lakehouse_name,
            inline_params=inline_params,
            one_lake_endpoint = one_lake_endpoint,
            mssparkutils_client = mssparkutils_client
        )
                
    def _setup(self) -> None:
        try:
            self.metrics_polling_interval_min = 0 
            self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
            self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)
            self.ci_profile_id = self.parameter_service.get_activity_config_value(GC.CI_PROFILE_ID_KEY, GC.CI_DEFAULT_PROFILE_ID)
            self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(workspace_name=self.workspace_name,
                                                                                        one_lake_endpoint=self.one_lake_endpoint,
                                                                                        solution_name=self.solution_name)
            self.source_tables_path = FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.source_lakehouse_name)
            
            self.idm_tables_path = FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name)
            self.idm_files_path=FolderPath.get_fabric_files_path( 
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name)
            self.idm_config_path=self.parameter_service.get_activity_config_value(
                GC.IDM_CONFIG_PATH_KEY,
                FolderPath.get_fabric_workload_files_idm_config_folder_path(root_path=self.config_files_root_path)
            )
            self.dtt_secondary_lake_path = (
                FolderPath.get_fabric_workload_files_idm_dtt_secondary_lake_folder_path(
                    root_path=self.config_files_root_path
                )
            )
            self.dmf_config_path = FolderPath.get_idm_dmf_configuration_files(root_path=self.config_files_root_path)
            self.rmt_config_path = FolderPath.get_idm_rmt_configuration_files(root_path=self.config_files_root_path)
            self.env_config_path = FolderPath.get_idm_environment_configuration_file(root_path=self.config_files_root_path)
            self.rmt_reference_tables_dir = FolderPath.get_idm_fabric_workload_files_rmt_mapping_folder_path(root_path=self.config_files_root_path)     
            self._logger.info(self.dmf_config_path)
            self._logger.info(self.rmt_config_path)
            self.business_events_ingestion_service = BusinessEventsIngestion(
                spark = self.spark,
                workspace_name = self.workspace_name,
                one_lake_endpoint = self.one_lake_endpoint,
                lakehouse_name = self.admin_lakehouse_name,
                solution_name = self.solution_name,
                parameter_service = self.parameter_service
                )
            
            self.dtt_env_config = f"""{{
                "storage": {{
                    "target": {{
                        "entities": {{
                            "default": {{
                                "location": "{self.idm_tables_path}",
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
            self._logger.info(self.env_config_path)
            self.placeholder_values: Dict = {
                "{{dtt_source}}": f"`{self.source_lakehouse_name}`",
                "{{ci_profile_id}}": f"{self.ci_profile_id}"
            }
            
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourcePath=self.source_tables_path,
            targetType=ExecutionDataType.deltaTable,
            targetPath=self.idm_tables_path,
            sourceLakehouseName=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("id"),
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("id"),
        )
    
    def _ingest_logic(self) -> None:
        """Using DTT ingest source data into IDM tables"""

        try:
            # Call DTT to transform Data
            self.__dtt_workflow()
            target_tables = Utils.get_target_anchor_tables_from_dtt_config(
                spark=self.spark,
                dtt_config_path=f"{self.idm_config_path}/{GC.IDM_DMF_ADAPTER_FILE}"
            )
            self.collect_all_target_tables_metrics(
                table_names=target_tables, 
                target_tables_root_path=self.idm_tables_path
            )
        except Exception as ex:
            message = f"{LC.IDM_TRANSFORMATION_EXCEPTION_ERROR_MSG.format(str(ex), traceback.print_exc())}"
            self._logger.error(message)
            
            new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GC.PATIENT_OUTREACH_SILVER_INGESTION_ACTIVITY_NAME, 
                targetFilePath= self.idm_tables_path, targetLakehouseName= GC.DEFAULT_SILVER_LAKEHOUSE_NAME, 
                sourceFilePath= self.source_tables_path, sourceLakehouseName= GC.DEFAULT_BRONZE_LAKEHOUSE_NAME, severity= GC.ERROR, 
                eventType= GC.PATIENT_OUTREACH_BRONZE_TO_SILVER_TRANSFORMATION, message= message, exception= str(ex), active=True)
            self.business_events_ingestion_service.insert_business_events(records=[new_row])
            
            raise Exception(message)

    def _get_internal_activity_name(self) -> str:
        return GC.PATIENT_OUTREACH_SILVER_INGESTION_ACTIVITY_NAME

    def _execute(self, **kwargs) -> None:
        try:
            self._ingest_logic()
        except Exception as ex:
            raise IDMSilverIngestionFailedError(str(ex))

    def __dtt_workflow(self):
        """Invokes the dtt workflow"""
        rmt_mapping_folder_paths=[f"{self.rmt_reference_tables_dir}/{GC.IDM_RMT_REFERENCE_TABLES_MAPPING_FOLDER}/{GC.IDM_RMT_REFERENCE_TABLES_DATA_HEALTHCARE_FOLDER}/{GC.IDM_RMT_REFERENCE_TABLES_DOMAIN_FOLDER}"]
        self._logger.info(f"{rmt_mapping_folder_paths[0]}")
        self._logger.info(f"{self.rmt_reference_tables_dir}")
        rmt_data_folder_paths=[f"{self.rmt_reference_tables_dir}/{GC.IDM_RMT_REFERENCE_TABLES_DATA_FOLDER}/{GC.IDM_RMT_REFERENCE_TABLES_DATA_COMMON_FOLDER}",f"{self.rmt_reference_tables_dir}/{GC.IDM_RMT_REFERENCE_TABLES_DATA_FOLDER}/{GC.IDM_RMT_REFERENCE_TABLES_DATA_HEALTHCARE_FOLDER}"]
       
        self._logger.info(rmt_data_folder_paths[0])
        adapter = f"{self.idm_config_path}/{GC.IDM_DMF_ADAPTER_FILE}"
        db_target_schema = f"{self.idm_config_path}/{GC.IDM_DB_TARGET_SCHEMA}"
        db_target_schema_config = (
            f"{self.idm_config_path}/{GC.IDM_DB_TARGET_SCHEMA_CONFIG}"
        )
        db_semantics = f"{self.idm_config_path}/{GC.IDM_DB_SEMANTICS}"
        db_semantics_config = (
            f"{self.idm_config_path}/{GC.IDM_DB_SEMANTICS_CONFIG}"
        )
        
        dtt_adapter = self.spark.read.text(adapter, wholetext=True).collect()[0][0]
        for placeholder in self.placeholder_values:
            dtt_adapter = dtt_adapter.replace(
                placeholder, self.placeholder_values[placeholder])
      
        config_files = {
            "adaptor_file_content": dtt_adapter,
            "target_db_semantics_file_location": db_semantics,
            "env_config_file_location": self.env_config_path,
            "target_db_schema_file_location": db_target_schema,
            "db_schema_config_location": db_target_schema_config,           
            "target_db_semantics_config_file_location": db_semantics_config,
            "rmt_target_path":self.idm_tables_path,
        }
        
        
        dtt_workflow = DTTWorkflowService( 
            spark=self.spark,   
            rmt_out_path=self.rmt_config_path,
            dtt_out_path=self.dmf_config_path,
            config_files=config_files,
            rmt_ordered_mapping_definitions_folders=rmt_mapping_folder_paths,
            executeRMTReferenceTable=True,
            rmt_reference_tables_folders_paths=rmt_data_folder_paths,
            mssparkutils_client=self.mssparkutils_client,
        )
        dtt_workflow.execute_dtt_workflow()
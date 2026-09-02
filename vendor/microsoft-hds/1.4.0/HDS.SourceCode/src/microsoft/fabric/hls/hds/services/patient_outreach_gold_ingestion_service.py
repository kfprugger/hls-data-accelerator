# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import traceback, uuid
from typing import Dict
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionDataType, ExecutionMetadata
from microsoft.fabric.hls.hds.ddl_helper.ddl_helper import DDLHelper
from microsoft.fabric.hls.hds.errors.poa_gold_ingestion_service_failed_error import PatientOutreachGoldIngestionServiceFailedError
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import (
    LoggingConstants as LC,
)
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.services.dtt_workflow_service import DTTWorkflowService
from microsoft.fabric.hls.hds.services.vocabulary_ingestion_service import (
    VocabularyIngestionService,
)
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.extension_parser import ExtensionParser
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.services.dtt_workflow_service import (
    DTTWorkflowService,
)
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion

class PatientOutreachGoldIngestionService(BaseRunnableService):
    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        inline_params: dict = None,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        mssparkutils_client: MSSparkUtilsClientBase = None) -> None:
        """
        Uses DTT library to transform and ingest data into Gold shape for Patient Outreach Reporting (Gold tables)
        Args:
        - spark: spark session
        - workspace_name - str: Name of the Fabric Workspace
        - solution_name: Name of the DMH OneLake workload solution
        - admin_lakehouse_name: The lakehouse name of where the administration configurations are located
        - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
        - mssparkutils_client: MSSparkUtilsClientBase, spark utils client
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
            ExtensionParser.register(self.spark)
            self.metrics_polling_interval_min = 0 
            self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.SILVER_LAKEHOUSE_ID_KEY)
            self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.PATIENT_OUTREACH_LAKEHOUSE_ID_KEY)
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

            self.poagold_tables_path = FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name,
            )
            
            self.poagold_config_path = self.parameter_service.get_activity_config_value(
                GC.POA_GOLD_CONFIG_PATH_KEY,
                f"{self.config_files_root_path}/{GC.DATA_MANAGER_INTERNAL_FOLDER_PATH}/{GC.PATIENT_OUTREACH_GOLD_CONFIG_PATH}"
            )
            # should be fine to use dtt_secondary_lake_path as the checkpoint path
            # we are creating in poa gold layer unique table names (ending with 'fact' or 'dim')
            self.dtt_secondary_lake_path = (
                FolderPath.get_fabric_workload_files_poa_dtt_secondary_lake_folder_path(
                    root_path=self.config_files_root_path
                )
            )
            
            self.poagold_checkpoint_path = f"{self.config_files_root_path}/{GC.DATA_MANAGER_CHECKPOINT_FOLDER_ROOT}/{GC.PATIENT_OUTREACH_FOLDER}/{GC.DTT_CONFIG_FOLDER}"
           
            self.dmf_config_path = f"{self.poagold_checkpoint_path}/{GC.DMF_CONFIG_PATH}"
            self.rmt_config_path = f"{self.poagold_checkpoint_path}/{GC.RMT_CONFIG_PATH}"
            self.env_config_path = f"{self.poagold_checkpoint_path}/{GC.ENV_CONFIG_PATH}"
           
            self.rmt_mapping_dir = f"{self.poagold_config_path}/{GC.PATIENT_OUTREACH_RMT_REFERENCE_FOLDER}/{GC.PATIENT_OUTREACH_RMT_REFERENCE_MAPPING_FOLDER}"
            self.rmt_data_dir = f"{self.poagold_config_path}/{GC.PATIENT_OUTREACH_RMT_REFERENCE_FOLDER}/{GC.PATIENT_OUTREACH_RMT_REFERENCE_DATA_FOLDER}"
            
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
                                "location": "{self.poagold_tables_path}",
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
            self._logger.error(message=str(ex))
            raise
    
    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourcePath=self.source_tables_path,
            targetType=ExecutionDataType.deltaTable,
            targetPath=self.poagold_tables_path,
            sourceLakehouseName=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("id"),
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("id"),
        )
    
    def _ingest_logic(self):
        """Using DTT ingest source data into Patient Outreach Gold shape tables"""

        try:
            # Call DTT to transform Data
            self.__dtt_workflow()
            target_tables = Utils.get_target_anchor_tables_from_dtt_config(
                spark=self.spark,
                dtt_config_path=f"{self.poagold_config_path}/{GC.PATIENT_OUTREACH_DTT_ADAPTER_FILE}"
            )
            self.collect_all_target_tables_metrics(
                table_names=target_tables, 
                target_tables_root_path=self.poagold_tables_path
            )
        except Exception as ex:
            message = f"{LC.POAGOLD_TRANSFORMATION_EXCEPTION_ERROR_MSG.format(str(ex), traceback.format_exc())}"
            self._logger.error(message)
            new_row = self.business_events_ingestion_service.create_new_business_event_row(id=str(uuid.uuid4()), activityName=GC.PATIENT_OUTREACH_GOLD_INGESTION_ACTIVITY_NAME, 
                targetFilePath= self.poagold_tables_path, targetLakehouseName= self.target_lakehouse_name, 
                sourceFilePath= self.source_tables_path, sourceLakehouseName= self.source_lakehouse_name, severity= GC.ERROR, 
                eventType= GC.PATIENT_OUTREACH_SILVER_TO_GOLD_TRANSFORMATION, message= message, exception= str(ex), active=True)
            self.business_events_ingestion_service.insert_business_events(records=[new_row])
            raise Exception(message)

    def _get_internal_activity_name(self) -> str:
        return GC.PATIENT_OUTREACH_GOLD_INGESTION_ACTIVITY_NAME

    def _execute(self, **kwargs) -> None:
        try:
            self._ingest_logic()
        except Exception as ex:
            raise PatientOutreachGoldIngestionServiceFailedError(str(ex))
    
    def __dtt_workflow(self):
        """Invokes the dtt workflow"""
        rmt_mapping_folder_path = [f"{self.rmt_mapping_dir}"]
        rmt_data_folder_path = [f"{self.rmt_data_dir}"]

        # todo: rmt being updated to take file contents vs. path, once ready remove logic below
        self.mssparkutils_client.fs_put(self.env_config_path, self.dtt_env_config, overwrite=True)

        dtt_adapter = f"{self.poagold_config_path}/{GC.PATIENT_OUTREACH_DTT_ADAPTER_FILE}"
        db_target_schema = f"{self.poagold_config_path}/{GC.DB_TARGET_SCHEMA}"
        db_target_schema_config = (
            f"{self.poagold_config_path}/{GC.DB_TARGET_SCHEMA_CONFIG}"
        )
        db_semantics = f"{self.poagold_config_path}/{GC.DB_SEMANTICS}"
        db_semantics_config = (
            f"{self.poagold_config_path}/{GC.DB_SEMANTICS_CONFIG}"
        )
        
        config_files = {
            "adaptor_file_location": dtt_adapter,
            "target_db_semantics_file_location": db_semantics,
            "env_config_file_location": self.env_config_path,
            "target_db_schema_file_location": db_target_schema,
            "db_schema_config_location": db_target_schema_config,           
            "target_db_semantics_config_file_location": db_semantics_config,
            "rmt_target_path": self.poagold_tables_path,
        }
        
        dtt_workflow = DTTWorkflowService( 
            spark=self.spark,   
            rmt_out_path=self.rmt_config_path,
            dtt_out_path=self.dmf_config_path,
            config_files=config_files,
            executeRMTReferenceTable=True,
            rmt_ordered_mapping_definitions_folders=rmt_mapping_folder_path,
            rmt_reference_tables_folders_paths=rmt_data_folder_path,
            mssparkutils_client=self.mssparkutils_client,
        )
        
        dtt_workflow.execute_dtt_workflow()
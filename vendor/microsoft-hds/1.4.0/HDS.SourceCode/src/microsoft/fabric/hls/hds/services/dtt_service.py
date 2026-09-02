# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import traceback, uuid
from typing import Dict
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import (
    LoggingConstants as LC,
)
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.extension_parser import ExtensionParser
from microsoft.fabric.hls.hds.services.dtt_workflow_service import DTTWorkflowService
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType

class DTTService(BaseRunnableService):
    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        inline_params: dict = None,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        mssparkutils_client: MSSparkUtilsClientBase = None
    ):
        """
        Uses DTT library to transform and ingest data into custom(Silver/Gold tables)
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

    def _setup(self) -> None:
        """
        Setup method for the DTTService class.
        """
        # Disable metrics poller as we are collecting metrics at the end of the activity
        self.metrics_polling_interval_min = 0 
        
        ExtensionParser.register(self.spark)       
        
        try:
            self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.DTT_SOURCE_LAKEHOUSE_ID_KEY)         
            if not self.source_lakehouse_name:
                source_lakehouse_err_msg = f"{LC.GENERIC_DTT_TRANSFORMATION_INLINE_PARAM_ERROR_MSG.format(GC.DTT_SOURCE_LAKEHOUSE_ID_KEY)}"             
                self._logger.error(source_lakehouse_err_msg)
                raise ValueError(source_lakehouse_err_msg)

            self.target_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.DTT_TARGET_LAKEHOUSE_ID_KEY)
            
            if not self.target_lakehouse_name:
                target_lakehouse_err_msg = f"{LC.GENERIC_DTT_TRANSFORMATION_INLINE_PARAM_ERROR_MSG.format(GC.DTT_TARGET_LAKEHOUSE_ID_KEY)}"
                self._logger.error(target_lakehouse_err_msg)
                raise ValueError(target_lakehouse_err_msg)

            self.config_files_root_path = (
                FolderPath.get_fabric_workload_files_root_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    solution_name=self.solution_name,
                )
            )
            
            self.dtt_service_config_path = self.parameter_service.get_activity_config_value(
                GC.DTT_SERVICE_CONFIG_PATH_KEY,
                None
            )
            
            if not self.dtt_service_config_path:
                service_config_path_err_msg = f"{LC.GENERIC_DTT_TRANSFORMATION_INLINE_PARAM_ERROR_MSG.format(GC.DTT_SERVICE_CONFIG_PATH_KEY)}"
                self._logger.error(service_config_path_err_msg)
                raise ValueError(service_config_path_err_msg)

            self.source_tables_path = self.parameter_service.get_activity_config_value(
                GC.SOURCE_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.source_lakehouse_name,
                )
            ) 
            
            self.target_tables_path = self.parameter_service.get_activity_config_value(
                GC.TARGET_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.target_lakehouse_name,
                )
            )

            self.rmt_target_path = FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.target_lakehouse_name
            )
            
            self.dtt_rmt_mapping_input_dir = self.parameter_service.get_activity_config_value(
                GC.DTT_RMT_MAPPING_INPUT_DIR_PATH_KEY,
                None
            )
            
            self.mssparkutils_client.fs_mkdirs(str(f"{self.dtt_service_config_path}/{GC.DTT_STATE_DB}"))

            self.dtt_secondary_lake_path = self.parameter_service.get_activity_config_value(
                GC.DTT_SECONDARY_LAKE_PATH_KEY,
                f"{self.dtt_service_config_path}/{GC.DTT_STATE_DB}"
            )     
            
            self.dmf_config_path = self.parameter_service.get_activity_config_value(
                GC.DMF_CONFIG_PATH_KEY,
                f"{self.dtt_service_config_path}/{GC.DMF_CONFIG_PATH}"
            )
            
            self.rmt_config_path = self.parameter_service.get_activity_config_value(
                GC.RMT_CONFIG_PATH_KEY,
                f"{self.dtt_service_config_path}/{GC.RMT_CONFIG_PATH}"
            )
                        
            self.env_config_path = f"{self.dtt_service_config_path}/{GC.ENV_CONFIG_PATH}"
            
            self.rmt_reference_tables_dir = self.parameter_service.get_activity_config_value(
                GC.DTT_RMT_REFERENCE_TABLES_DIR_PATH_KEY,
                None
            )
            
            self.rmt_mapping_input_dir = self.parameter_service.get_activity_config_value(
                GC.RMT_MAPPING_INPUT_DIR_PATH_KEY,
                self.dtt_service_config_path
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
                            "location": "{self.target_tables_path}",
                            "format": "delta"
                        }}
                    }}
                }},
                "secondary_lake": {{
                    "location": "{self.dtt_secondary_lake_path}"
                }}
            }}
        }}"""
        
    def _setup_execution_metadata(self) -> ExecutionMetadata:
        source_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name) if self.source_lakehouse_name is not None else None
        target_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name) if self.target_lakehouse_name is not None else None
        return ExecutionMetadata(
            sourceType=ExecutionDataType.deltaTable,
            sourcePath=self.source_tables_path,
            sourceLakehouseName=source_lakehouse_properties.get("displayName"),
            sourceLakehouseIdentifier=source_lakehouse_properties.get("id"),
            targetType=ExecutionDataType.deltaTable,
            targetPath=self.target_tables_path,
            targetLakehouseName=target_lakehouse_properties.get("displayName"),
            targetLakehouseIdentifier=target_lakehouse_properties.get("id")
        )        

    def _get_internal_activity_name(self) -> str:
        return GC.DTT_GENERIC_INGESTION_ACTIVITY_NAME

    def _execute(self, **kwargs) -> None:
        """
        Executes the DTTService class.

        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.
        """
        self.__ingest()    

    def __ingest(self):
        """Using DTT ingest source data into lakehouse tables"""
        
        try:            
            # Call DTT to transform Data
            self.__dtt_workflow()

            target_tables = Utils.get_target_anchor_tables_from_dtt_config(
                spark=self.spark,
                dtt_config_path=f"{self.dtt_service_config_path}/{GC.DMF_ADAPTER_FILE}"
            )
            self.collect_all_target_tables_metrics(
                table_names=target_tables,
                target_tables_root_path=self.target_tables_path
            )
            
        except Exception as ex:
            message = f"{LC.DTT_TRANSFORMATION_EXCEPTION_ERROR_MSG.format(str(ex), traceback.format_exc())}"
            self._logger.error(message)
            new_row = self.business_events_ingestion_service.create_new_business_event_row(
                id=str(uuid.uuid4()), 
                activityName=GC.DTT_GENERIC_INGESTION_ACTIVITY_NOTEBOOK,
                targetFilePath=self.target_tables_path, 
                sourceFilePath=self.source_tables_path,                 
                targetLakehouseName=self.target_lakehouse_name,
                sourceLakehouseName=self.source_lakehouse_name, 
                severity=GC.ERROR, 
                eventType=GC.DTT_TRANSFORMATION_EVENT, 
                message=message, 
                active=True
            )
            self.business_events_ingestion_service.insert_business_events([new_row])
            raise

    def __dtt_workflow(self):
        """Invokes the dtt workflow"""

        self.mssparkutils_client.fs_put(self.env_config_path, self.dtt_env_config, overwrite=True)
        self.mssparkutils_client.fs_mkdirs(str(self.rmt_mapping_input_dir))

        self._logger.info(
            f"{LC.RMT_CREATED_CONCEPT_FILE.format(self.rmt_mapping_input_dir)}"
        )

        rmt_data_folder_paths=[f"{self.rmt_reference_tables_dir}"]
        dtt_adapter = f"{self.dtt_service_config_path}/{GC.DMF_ADAPTER_FILE}"
        
        db_target_schema = f"{self.dtt_service_config_path}/{GC.DB_TARGET_SCHEMA}"
        db_target_schema_config = (
            f"{self.dtt_service_config_path}/{GC.DB_TARGET_SCHEMA_CONFIG}"
        )
        db_semantics = f"{self.dtt_service_config_path}/{GC.DB_SEMANTICS}"
        db_semantics_config = (
            f"{self.dtt_service_config_path}/{GC.DB_SEMANTICS_CONFIG}"
        )
        
        config_files = {
            "adaptor_file_location": dtt_adapter,
            "target_db_semantics_file_location": db_semantics,
            "env_config_file_location": self.env_config_path,
            "target_db_schema_file_location": db_target_schema,
            "db_schema_config_location": db_target_schema_config,           
            "target_db_semantics_config_file_location": db_semantics_config
        }          
        
        if self.dtt_rmt_mapping_input_dir is not None and len(self.dtt_rmt_mapping_input_dir) > 0:
            rmt_mapping_folder_path = [f"{self.dtt_rmt_mapping_input_dir}"]
        else:
            rmt_mapping_folder_path = None
             
        dtt_workflow = DTTWorkflowService( 
        spark=self.spark,   
        rmt_out_path=self.rmt_config_path,
        dtt_out_path=self.dmf_config_path,
        config_files=config_files,
        rmt_ordered_mapping_definitions_folders= rmt_mapping_folder_path,
        rmt_reference_tables_folders_paths=rmt_data_folder_paths,
        executeRMTReferenceTable=False,
        mssparkutils_client=self.mssparkutils_client,
        )                   
        dtt_workflow.execute_dtt_workflow()
        
        self._logger.info(
            LC.DTT_SERVICE__SUCCESS_INFO_MSG.format(self.dmf_config_path, self.rmt_config_path)
        )    
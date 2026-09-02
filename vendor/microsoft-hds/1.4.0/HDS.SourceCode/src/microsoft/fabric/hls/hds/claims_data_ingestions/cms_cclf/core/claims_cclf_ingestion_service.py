import os
import json
from microsoft.fabric.hls.hds.claims_data_ingestions.cms_cclf.core.constants import CmsCclfConstants
from microsoft.fabric.hls.hds.claims_data_ingestions.cms_cclf.core.process_cmscclf_files import Process_CmsCclf_Files
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.business_events_ingestion_handler import BusinessEventsIngestion
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.utils import Utils, FolderPath
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType
from microsoft.fabric.hls.hds.errors.claims_ingestion_service_failed_error import ClaimsCCLFIngestionFailedError


class ClaimsCCLFIngestionService(BaseRunnableService):
    """
    This class represents the service for ingesting CMS CCLF files into a lakehouse.
    """

    def __init__(self, 
                 spark: SparkSession,
                 workspace_name: str,
                 solution_name: str,
                 admin_lakehouse_name: str,
                 inline_params: dict = None,
                 one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
                 mssparkutils_client: MSSparkUtilsClientBase = None) -> None:
        """
        Initializes a new instance of the ClaimsCCLFIngestionService class.

        Args:
            - spark (SparkSession): The Spark session.
            - workspace_name (str): The name of the workspace.
            - solution_name (str): The name of the solution.
            - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
            - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
            - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
            - mssparksutils_client (MSSparkUtilsClientBase): The mssparkutils client
        Returns:
            None
        """
        self.spark: SparkSession = spark
        self.workspace_name = workspace_name
        self.solution_name = solution_name
        self.one_lake_endpoint = one_lake_endpoint
        self.mssparkutils_client = mssparkutils_client
        
        super().__init__(spark=spark,
                        workspace_name=workspace_name,
                        solution_name=solution_name,
                        admin_lakehouse_name=admin_lakehouse_name,
                        inline_params=inline_params,
                        one_lake_endpoint=one_lake_endpoint,
                        mssparkutils_client=mssparkutils_client)

        
    def _setup(self) -> None:
        
        self.business_events_table_path = FolderPath.get_fabric_tables_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                lakehouse_name=self.admin_lakehouse_name)
        
        self.target_lakehouse_name = self.source_lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
        
        self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            solution_name=self.solution_name
        )
        
        self.business_events_schema_dir_path = self.parameter_service.get_activity_config_value(
                GC.BUSINESS_EVENTS_SCHEMA_DIR_PATH_KEY,
                f"{FolderPath.get_fabric_workload_files_schema_root_folder_path(root_path=self.config_files_root_path)}/{GC.BUSINESS_EVENTS_SCHEMA_ROOT_FOLDER}"
            )
        
        self.lakehouse_files_root_path = FolderPath.get_fabric_files_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.target_lakehouse_name
        )
        
        self.business_events_ingestion_service = BusinessEventsIngestion(
                spark = self.spark,
                workspace_name = self.workspace_name,
                one_lake_endpoint = self.one_lake_endpoint,
                lakehouse_name = self.admin_lakehouse_name,
                solution_name = self.solution_name,
                parameter_service = self.parameter_service
                )
        
        try:
            self.checkpoint_path = os.path.join(
                self.parameter_service.get_foundation_config_value(
                GC.CLAIMS_CHECKPOINT_PATH_KEY,
                FolderPath.get_fabric_workload_files_checkpoint_folder_path(
                    root_path=self.config_files_root_path,
                    checkpoint_folder_name=f"{GC.CLAIMS_INGESTION_FOLDER}"
                )
                ),CmsCclfConstants.CMS_CCLF_DROP_FOLDER_TO_DELTA_TABLES_CHECKPOINT_FOLDER)            
            
            self.cms_cclf_files_drop_path = self.parameter_service.get_activity_config_value(
                GC.CMS_CCLF_FILES_DROP_PATH_KEY,
                os.path.join(self.lakehouse_files_root_path, GC.PROCESS_FOLDER, GC.CLAIMS_FOLDER, GC.CCLF_FOLDER)
            )
            self.cms_cclf_files_folder_path = FolderPath.get_fabric_workload_files_root_path(
                workspace_name=self.workspace_name,
                one_lake_endpoint=self.one_lake_endpoint,
                solution_name=self.solution_name
            )
            self.cclf_files_config_path = self.parameter_service.get_activity_config_value(
                GC.CCLF_FILES_CONFIG_PATH_KEY,
                f"{self.config_files_root_path}/{GC.CLAIMS_CCLF_FILES_CONFIG_PATH}/{CmsCclfConstants.CMS_CCLF_FILE_CONFIG_NAME}"
            )
            self.target_tables_path = self.parameter_service.get_activity_config_value(
                GC.TARGET_TABLES_PATH_KEY,
                FolderPath.get_fabric_tables_path(
                    workspace_name=self.workspace_name,
                    one_lake_endpoint=self.one_lake_endpoint,
                    lakehouse_name=self.target_lakehouse_name
                )
            )
            self.max_files_per_trigger = int(self.parameter_service.get_activity_config_value(
                GC.MAX_FILES_PER_TRIGGER_KEY,
                CmsCclfConstants.CMS_CCLF_MAX_FILES_PER_TRIGGER
            ))
            
            self.file_orchestration_config_path = self.parameter_service.get_foundation_config_value(
                GC.FILE_MOVEMENT_CONFIG_PATH_KEY,
                FolderPath.get_fabric_workload_files_file_orchestration_config_path(self.config_files_root_path)
            )
            
            self.supported_file_extensions = []   
            config_content = self.spark.sparkContext.wholeTextFiles(self.file_orchestration_config_path).collect()[0][1]
            file_orchestration_config = json.loads(config_content)
            claims_section = file_orchestration_config.get("Claims", [])
            if claims_section and "file_extensions" in claims_section[0]:
                file_extensions = claims_section[0]["file_extensions"]
                for value in file_extensions:
                    self.supported_file_extensions.append(value.replace("*.", ""))
            else:
                self._logger.error(LC.CMS_CCLF_SUPPORTED_FILE_EXTENSIONS_READ_ERR_MSG)
                raise
        except Exception as ex:
            self._logger.error(message=str(ex))
            raise ClaimsCCLFIngestionFailedError(message=ex)
        
    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.file,
            sourcePath=self.cms_cclf_files_drop_path,
            targetType=ExecutionDataType.deltaTable,
            targetPath=self.target_tables_path,
            sourceLakehouseName=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("displayName"),
            sourceLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.source_lakehouse_name).get("id"),
            targetLakehouseName=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("displayName"),
            targetLakehouseIdentifier=self.mssparkutils_client.get_lakehouse(self.target_lakehouse_name).get("id"),
        )

    def _get_internal_activity_name(self) -> str:
        return GC.CMS_CCLF_FILES_DELTA_TABLES_INGESTION_ACTIVITY_NAME

    def _register_custom_accumulators(self) -> None:
        self.execution_metrics_collector.register_accumulator(
            accumulator_activity_id=self._get_validation_metrics_accumulator_activity_id(),
            initial_state=self._get_validation_metrics_initial_state()
        )

    def _execute(self, **kwargs) -> None:
        """
        Wrap for the service's core execution logic.
        """
        self._ingest_logic()

    def _ingest_logic(self) -> None:
        """
        Actual ingestion logic moved here.
        """
        cmsCclfFileProcesser = Process_CmsCclf_Files(
            self.spark,
            self.cms_cclf_files_drop_path,
            self.lakehouse_files_root_path,
            self.supported_file_extensions,            
            self.business_events_ingestion_service,
            collect_metrics_fn=self.collect_target_delta_table_operation_summary_metrics,
            execution_metrics_collector=self.execution_metrics_collector,
            execution_metrics_accumulator_id=self.get_execution_metrics_accumulator_activity_id()
        )
        cmsCclfFileProcesser.process(self.cclf_files_config_path, self.checkpoint_path, self.target_tables_path, self.max_files_per_trigger)
import os
from typing import Optional, Type
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.claims_data_ingestions.cms_cclf.core.transform_cclf_to_fhir_ndjson import TransformCCLFToFHIRNDJSON#
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.utils import FolderPath
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType


class ClaimsFHIRTransformationService(BaseRunnableService):
    """
    Parent FHIR transformation service to determine and invoke the transformation logic
    based on the source type parameter.
    """

    def __init__(
        self, 
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        inline_params: Optional[dict] = None,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        mssparkutils_client: Optional[MSSparkUtilsClientBase] = None
    ) -> None:
        """
        Initializes a new instance of the ClaimsFHIRTransformationService class.

        Args:
            spark (SparkSession): The Spark session.
            workspace_name (str): The name of the workspace.
            solution_name (str): The solution name.
            admin_lakehouse_name (str): Name of the lakehouse containing admin configurations.
            inline_params (Optional[dict]): Inline parameters that override the admin lakehouse configuration.
            one_lake_endpoint (str): OneLake endpoint. Default is `onelake.dfs.fabric.microsoft.com`.
            mssparkutils_client (Optional[MSSparkUtilsClientBase]): The mssparkutils client.
        """
        self.spark = spark
        self.workspace_name = workspace_name
        self.solution_name = solution_name
        self.one_lake_endpoint = one_lake_endpoint
        self.admin_lakehouse_name = admin_lakehouse_name
        self.inline_params_dict = inline_params or {}  # Default to empty dict to avoid NoneType issues
        self.mssparkutils_client = mssparkutils_client
        
        super().__init__(spark=spark,
                         workspace_name=workspace_name,
                         solution_name=solution_name,
                         admin_lakehouse_name=admin_lakehouse_name,
                         inline_params=inline_params,
                         one_lake_endpoint=one_lake_endpoint,
                         mssparkutils_client=mssparkutils_client)

    def _setup(self) -> None:
        self.source_type = self.parameter_service.get_activity_config_value(GC.SOURCE_TYPE)
        self.lakehouse_name = self.parameter_service.get_foundation_config_value(GC.BRONZE_LAKEHOUSE_ID_KEY)
        self.lakehouse_files_root_path = FolderPath.get_fabric_files_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            lakehouse_name=self.lakehouse_name
        )
        self.source_path_pattern = self.parameter_service.get_activity_config_value(
                GC.CMS_CCLF_FILES_DROP_PATH_KEY,
                os.path.join(self.lakehouse_files_root_path, GC.DROP_FOLDER, GC.CLAIMS_FOLDER)
            )
        self.target_tables_path = self.parameter_service.get_activity_config_value(
                GC.CMS_CCLF_FILES_DROP_PATH_KEY,
                os.path.join(self.lakehouse_files_root_path, GC.PROCESS_FOLDER, GC.CLAIMS_FOLDER)
            )
        self.enable_summary_metrics = False
        self.metrics_polling_interval_min = 0


    def _get_internal_activity_name(self) -> str:
        return GC.CLAIMS_FILES_BRONZE_INGESTION_ACTIVITY_NAME

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        target_lakehouse_properties = self.mssparkutils_client.get_lakehouse(self.lakehouse_name)
        return ExecutionMetadata(
            sourceType=ExecutionDataType.file,
            sourcePath=self.source_path_pattern,
            targetType=ExecutionDataType.deltaTable,
            targetLakehouseName=target_lakehouse_properties.get("displayName"),
            targetLakehouseIdentifier=target_lakehouse_properties.get("id"),
            targetPath=self.target_tables_path
        )

    def _get_transformation_service(self):
        """
        Determines the appropriate transformation service based on the source type.

        Returns:
            Instance of either `TransformCCLFToFHIRNDJSON`.

        Raises:
            ValueError: If the source type is unsupported.
        """
        transformation_services = {
            GC.CCLF: TransformCCLFToFHIRNDJSON
        }

        service_class = transformation_services.get(self.source_type)
        if not service_class:
            error_message = LC.UNSUPPORTED_SOURCE_TYPE.format(source_type=self.source_type)
            self._logger.error(error_message)
            return None

        return service_class(
            spark=self.spark,
            workspace_name=self.workspace_name,
            solution_name=self.solution_name,
            admin_lakehouse_name=self.admin_lakehouse_name,
            inline_params=self.inline_params_dict,
            one_lake_endpoint=self.one_lake_endpoint
        )

    def _execute(self, **kwargs):
        """
        Executes the transformation process.
        """
        self.execute_ndjson_generation()

    def execute_ndjson_generation(self) -> None:
        """
        Calls the appropriate transformation method based on the source type.
        """
        try:
            service = self._get_transformation_service()
            if service:
                service.run()
            else:
                self._logger.error(LC.UNSUPPORTED_SOURCE_TYPE.format(source_type = self.source_type))
        except Exception as e:
            self._logger.error(LC.TRANSFORMATION_FAILED.format(source_type=self.source_type, error_message=str(e)))
            raise
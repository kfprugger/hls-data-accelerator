# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import time
from http import HTTPStatus
from datetime import datetime, timedelta
import requests
from typing import Callable
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.utils.utils import Utils, FolderPath
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.parameter_service import ParameterService
from microsoft.fabric.hls.hds.services.base_runnable_service import BaseRunnableService
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata, ExecutionDataType

class FHIRExportService(BaseRunnableService):   
    def __init__(
        self,
        spark: SparkSession,
        workspace_name: str,
        solution_name: str,
        admin_lakehouse_name: str,
        one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
        inline_params: dict = None,
        mssparkutils_client: MSSparkUtilsClientBase = None
        ) -> None:
        """
            Args:
                - spark (SparkSession): The current Spark session
                - workspace_name: Name of the Fabric Workspace
                - solution_name: Name of the HDS-Healthcare data solutions OneLake workload solution
                - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
                - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
                - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
                - mssparkutils_client (MSSparkUtilsClientBase): The mssparkutils client
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
        Setup method for the FHIRExportService
        """
        
        # Disable only the metrics poller as we are not collecting metrics for this service at the moment
        self.metrics_polling_interval_min = 0 
        self.max_polling_days = self.parameter_service.get_activity_config_value(GC.MAX_POLLING_DAYS_KEY, GC.FHIR_EXPORT_MAX_POLLING_DAYS, "int")
        
        Utils.validate_required_parameters({
            GC.KEYVAULT_NAME_KEY: self.kv_name
        })

        self.function_url = Utils.get_key_vault_secret(
                spark=self.spark,
                kv_secret_name=GC.FUNCTION_URL_SECRET_NAME,
                mssparkutils_client=self.mssparkutils_client,
            )

    def _setup_execution_metadata(self) -> ExecutionMetadata:
        return ExecutionMetadata(
            sourceType=ExecutionDataType.api, # The source type is a FHIR API
            sourcePath=self.function_url,
            targetType=ExecutionDataType.file, # The target type is ndjson files
            targetPath="" # The target is an ADLS Gen2 storage account configured in the Azure Function
        )

    def _get_internal_activity_name(self) -> str:
        return GC.FHIR_EXPORT_ACTIVITY_NAME

    def _get_function_secret(self) -> str:
        """
            Retrieves the ExportFunctionKey secret from a user-specified key vault.
        """
        token = Utils.get_key_vault_secret(
                spark=self.spark,
                kv_secret_name="ExportFunctionKey",
                mssparkutils_client=self.mssparkutils_client,
            )
        return token

    def _execute(self, **kwargs) -> None:
        """
            Executes the FHIRExportService.
        """
        self.run_pipeline()

    def _trigger_azure_function(self) -> str:
        """
            Triggers a user-specified azure function and returns the status URL to monitor.
        """
        
        constructed_url = f"{GC.AZURE_FUNCTION_URL_FORMAT.format(function_url=self.function_url, run_id=self.run_id, code=self._get_function_secret())}"
        
        response = requests.get(constructed_url)
        self._logger.info(f"{LC.FHIREXPORTSERVICE_RESPONSE_INFO_MSG.format(trigger_type='Azure Function', code=response.status_code)}")
        if response.status_code == HTTPStatus.ACCEPTED:
            status_query_uri = response.headers['Location']
            return status_query_uri
        else:
            self._logger.error(f"{LC.FHIREXPORTSERVICE_TRIGGER_ERR_MSG.format(code=response.status_code)}")
            raise RuntimeError(f"{LC.FHIREXPORTSERVICE_TRIGGER_ERR_MSG.format(code=response.status_code)}")
    
    def _poll_http_call(self, status_query_uri: str) -> None:
        """
            Polls a given status URL until a 202 response code is received or until
            max_polling_days days have passed.

            Args:
                - status_query_uri (str): the status URL of the orchestration instance
                - max_polling_days (int): the maximum number of days for polling
        """
        start_time = datetime.now()
        
        while True:
            current_time = datetime.now()
            elapsed_time = current_time - start_time

            if elapsed_time > timedelta(days=self.max_polling_days):
                self._logger.error(f"{LC.FHIREXPORTSERVICE_MAX_DURATION_ERR_MSG.format(max_days=self.max_polling_days)}")
                raise Exception(f"{LC.FHIREXPORTSERVICE_MAX_DURATION_ERR_MSG.format(max_days=self.max_polling_days)}")
            
            response = requests.get(status_query_uri)
            
            if response.status_code == HTTPStatus.OK:
                self._logger.info(f"{LC.FHIREXPORTSERVICE_RESPONSE_INFO_MSG.format(trigger_type='polling', code=response.status_code)}")
                self._logger.info(f"{LC.FHIREXPORTSERVICE_SUCCESS_INFO_MSG}")
                break
            elif response.status_code == HTTPStatus.ACCEPTED:
                self._logger.debug(f"{LC.FHIREXPORTSERVICE_IN_PROGRESS_DEBUG_MSG}")
            else:
                error_message = Utils.get_error_message(response)
                self._logger.error(f"{LC.FHIREXPORTSERVICE_POLLING_ERR_MSG.format(code=response.status_code, message=error_message)}")
                self._logger.error(f"{LC.FHIREXPORTSERVICE_FAILURE_ERR_MSG}")
                raise Exception(f"{LC.FHIREXPORTSERVICE_POLLING_ERR_MSG.format(code=response.status_code, message=error_message)}")
            time.sleep(10)
    
    def run_pipeline(self) -> None:
        """
            Triggers the FHIRExport pipeline.
        """
        status_query_uri = self._trigger_azure_function()
        
        try:
            # Start polling the status_query_uri. _poll_http_call will log the return code and break/raise an Exception 
            self._logger.info(f"{LC.FHIREXPORTSERVICE_TRIGGER_SUCCESS_INFO_MSG}")
            self._poll_http_call(status_query_uri)
        except Exception as e:
            # If the status_query_uri cannot be polled, run_pipeline will raise an exception
            self._logger.error(f"{LC.FHIREXPORTSERVICE_EXCEPTION_ERR_MSG.format(exception_message=e)}")
            raise Exception(f"{LC.FHIREXPORTSERVICE_EXCEPTION_ERR_MSG.format(exception_message=e)}")
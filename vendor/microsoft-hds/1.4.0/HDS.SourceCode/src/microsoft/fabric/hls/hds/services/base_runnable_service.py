# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import uuid
import time
from datetime import datetime
from typing import Callable, List
from abc import ABC, abstractmethod
from pyspark.sql import SparkSession, DataFrame
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.utils.utils import FolderPath, Utils
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.parameter_service import ParameterService
from microsoft.fabric.hls.hds.data_models.execution_result import ExecutionResult, ExecutionStatus, InternalExecutionStatus
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionMetadata
from microsoft.fabric.hls.hds.execution_metrics.execution_metrics_collector import ExecutionMetricsCollector
from microsoft.fabric.hls.hds.execution_metrics.execution_metrics_orchestrator import ExecutionMetricsOrchestrator
from microsoft.fabric.hls.hds.execution_metrics.constants import ExecutionMetricsConstants as EMC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.errors.execution_metrics_failed_error import ExecutionMetricsFailedError
from microsoft.fabric.hls.hds.errors.base_runnable_service_failed_error import BaseRunnableServiceFailedError
from microsoft.fabric.hls.hds.utils.dataframe_utils import get_num_records_delta_op
from microsoft.fabric.hls.hds.utils.fabric_utils import FabricClientUtils

class BaseRunnableService(ABC):
    def __init__(self, 
                 spark: SparkSession,
                 workspace_name: str,
                 solution_name: str,
                 admin_lakehouse_name: str,
                 inline_params: dict = None,
                 one_lake_endpoint: str = GC.DEFAULT_ONE_LAKE_ENDPOINT,
                 mssparkutils_client: MSSparkUtilsClientBase = None,
                 ) -> None:
        """
        Initializes the BaseRunnableService class
        
        Args:
            - spark: spark session
            - workspace_name: Name of the Fabric Workspace
            - solution_name: Name of the HDS-Healthcare data solutions OneLake workload solution
            - admin_lakehouse_name (str): The lakehouse name of where the administration configurations are located
            - inline_params (dict): Inline parameters that will overwrite and take precedence over the parameters in the administration lakehouse configuration
            - one_lake_endpoint (str): The one lake endpoint. Default is `onelake.dfs.fabric.microsoft.com`
            - mssparksutils_client (MSSparkUtilsClientBase): The mssparkutils client
        """
        self.spark: SparkSession = spark
        self.workspace_name: str = workspace_name
        self.solution_name: str = solution_name
        self.one_lake_endpoint: str = one_lake_endpoint
        self.admin_lakehouse_name: str = admin_lakehouse_name
        self.spark.sparkContext.setJobGroup(f"{self.__class__.__module__}.{self.__class__.__qualname__}","")
        
        self.mssparkutils_client = Utils.get_mssparkutils_client(mssparkutils_client) 
        self.inline_params = inline_params

        self.parameter_service = ParameterService(
            spark=spark,
            workspace_name=workspace_name,
            admin_lakehouse_name=admin_lakehouse_name,
            one_lake_endpoint=self.one_lake_endpoint,
            mssparkutils_client=self.mssparkutils_client,
            inline_params=inline_params
        )
        self.fabric_runtime_context = self.mssparkutils_client.get_runtime_context()
        self.workspace_id = self.fabric_runtime_context.get('currentWorkspaceId')

        # Retrieve notebook details from Fabric Rest API's
        notebook_info = FabricClientUtils.get_notebook(
            workspace_id=self.workspace_id,
            notebook_id=self.fabric_runtime_context.get('currentNotebookId')
        )
        # Use the displayName if available; otherwise, fall back to the internal activity name.
        self.notebook_name = notebook_info.get("displayName") or self._get_internal_activity_name()
        self.pipeline_run_id = self.parameter_service.get_foundation_config_value(GC.PIPELINE_RUN_ID_KEY)
        self.pipeline_name = self.parameter_service.get_foundation_config_value(GC.PIPELINE_NAME_KEY)
        self.enable_hds_logs = self.parameter_service.get_foundation_config_value(GC.ENABLE_HDS_LOGS_KEY, default="True")
        self.enable_summary_metrics : bool = self.parameter_service.get_foundation_config_value(GC.ENABLE_SUMMARY_METRICS_KEY, default=True, value_type="bool")
        self.metrics_polling_interval_min : int = self.parameter_service.get_foundation_config_value(GC.METRICS_POLLING_INTERVAL_IN_MIN_KEY, default=EMC.DEFAULT_METRICS_POLLING_INTERVAL_IN_MIN, value_type="int")
        self.admin_lakehouse_tables_root_path = FolderPath.get_fabric_tables_path(workspace_name=self.workspace_name,one_lake_endpoint=self.one_lake_endpoint,lakehouse_name=admin_lakehouse_name)
        self.admin_lakehouse_files_root_path = FolderPath.get_fabric_files_path(workspace_name=self.workspace_name,one_lake_endpoint=self.one_lake_endpoint,lakehouse_name=admin_lakehouse_name)
        self.default_execution_summary_table_path = f"{self.admin_lakehouse_tables_root_path}/{EMC.DEFAULT_EXECUTION_SUMMARY_TABLE}"
        self.execution_summary_table_path = self.parameter_service.get_foundation_config_value(GC.EXECUTION_SUMMARY_TABLE_PATH_KEY, default=self.default_execution_summary_table_path)
        self.config_files_root_path = FolderPath.get_fabric_workload_files_root_path(
            workspace_name=self.workspace_name,
            one_lake_endpoint=self.one_lake_endpoint,
            solution_name=self.solution_name
        )
        self.validation_config_path = self.parameter_service.get_foundation_config_value(
            GC.DATA_VALIDATION_CONFIG_PATH_KEY,
            f"{FolderPath.get_fabric_files_path(workspace_name=self.workspace_name, one_lake_endpoint=self.one_lake_endpoint,lakehouse_name=self.admin_lakehouse_name)}/{GC.PARAMETERS_CONFIGS_FOLDER}/{GC.VALIDATION_CONFIG_FILE}"
        )
        self.kv_name = self.parameter_service.get_foundation_config_value(GC.KEYVAULT_NAME_KEY)
        Utils.set_key_vault_name(self.spark, self.kv_name)
        
        self.has_validation_errors = False
        self.has_validations_warnings = False
        self.execution_metrics_collector = ExecutionMetricsCollector(spark=spark)
        self.run_id: str = None
        self._logger: DataManagerLogger = DataManagerLogger(
            spark=self.spark, 
            logger_name=f"{GC.DATA_MANAGER_LOGGER}.{self.__class__.__name__}", 
            log_level=GC.LOGGING_LEVEL,
            pipeline_run_id=self.pipeline_run_id,
        )
        
        # Setup the service
        self._setup()
        
        # Setup the execution metadata     
        self.execution_metadata: ExecutionMetadata = self._setup_execution_metadata()

        # Setup the execution metrics orchestrator
        self.execution_metrics_orchestrator = ExecutionMetricsOrchestrator(
            spark=self.spark, 
            execution_summary_table_path=self.execution_summary_table_path, 
            execution_metrics_collector=self.execution_metrics_collector,
            logger=self._logger,
            metrics_polling_interval_min=self.metrics_polling_interval_min,
            pipeline_run_id=self.pipeline_run_id,
            pipeline_name=self.pipeline_name,
            enable_summary_metrics=self.enable_summary_metrics
        )
        
        # Update the spark properties based on the deployment user configuration
        activity_key_to_spark_property_dict = {
            GC.PARQUET_DATE_REBASE_MODE_IN_WRITE_KEY: GC.SPARK_PARQUET_DATE_REBASE_MODE_IN_WRITE_KEY,
            GC.PARQUET_DATETIME_REBASE_MODE_IN_WRITE_KEY: GC.SPARK_PARQUET_DATETIME_REBASE_MODE_IN_WRITE_KEY,
            GC.ENABLE_HDS_LOGS_KEY: GC.SPARK_ENABLE_HDS_LOGS
        }
        self.parameter_service.update_spark_properties(activity_key_to_spark_property_dict)
        
    @abstractmethod
    def _setup(self) -> None:
        """
        Sets up the service for each individaul service. Must be implemented by subclasses.
        """
        raise NotImplementedError

    @abstractmethod
    def _setup_execution_metadata(self) -> ExecutionMetadata:
        """
        Sets up the execution details for the service. Must be implemented by subclasses.
        """
        raise NotImplementedError
    
    @abstractmethod
    def _get_internal_activity_name(self) -> str:
        """
        Retrieves the name of the activity. Must be implemented by subclasses.

        Returns:
            str: The name of the activity.
        """
        raise NotImplementedError

    def _register_custom_accumulators(self) -> None:
        """
        Registers custom accumulators. Optional method to be implemented by subclasses.
        """
        pass

    def _default_transformation_fn(self) -> Callable:
        """
        Retrieves the default transformation function. Optional method to be implemented by subclasses.

        Returns:
            Callable: The default transformation function.
        """
        pass

    def _cleanup(self, **kwargs) -> None:
        execution_time = time.time() - self.start_time
        execution_result = self._create_final_execution_result(exceptions=kwargs.get("exceptions", []))
        
        self.execution_metrics_orchestrator.run(
            accumulator_activity_id=self.get_execution_metrics_accumulator_activity_id(),
            internal_activity_name=self._get_internal_activity_name(),
            activity_display_name=self._get_activity_display_name(),
            run_id=self.run_id,
            execution_result=execution_result,
            execution_time=execution_time
        )
            
        if execution_result.internalExecutionStatus == InternalExecutionStatus.SUCCEEDED:
            self._get_logger().info(execution_result.executionStatusDetails)
        elif execution_result.internalExecutionStatus == InternalExecutionStatus.SUCCEEDED_WITH_ERRORS:
            self._get_logger().warning(execution_result.executionStatusDetails)
        else:
            self._get_logger().error(execution_result.executionStatusDetails)
        
        self.execution_metrics_collector.reset_accumulators()
    
    @abstractmethod
    def _execute(self, **kwargs) -> None:
        """
        Executes the main logic of the service. Must be implemented by subclasses.

        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.
        """
        raise NotImplementedError

    def run(self, **kwargs) -> None:
        """
        Runs the service, executing the provided transformation function. This method acts as the main entry point for the service. 
        The main steps include setting up the logger, setting up the service, setting up the execution details, executing the service, 
        and emitting the summary metrics as well as the library usage telemetry with a subset of the summary metrics.

        Keyword Args:
            transformation_fn (Callable, optional): The transformation function to be executed on the input data. Defaults to None.
        """
        exceptions: List[Exception] = []
        try:
            self.start_time = time.time()
            # Generate a unique run id for each execution run
            self.run_id = str(uuid.uuid4())
            self._logger.set_run_id(run_id=self.run_id)
            self._get_logger().info(self._get_service_execution_started_message())
            # Setup the default execution result
            execution_result: ExecutionResult = self._get_default_execution_result()
            # Get the execution metrics accumulator activity ID
            execution_metrics_accumulator_activity_id = self.get_execution_metrics_accumulator_activity_id()
            # Reset the validation errors and warnings flags
            self.has_validation_errors = False
            self.has_validations_warnings = False
            # Register accumulators and start the metrics poller for the execution metrics
            try:
                self.execution_metrics_collector.register_accumulator(accumulator_activity_id=execution_metrics_accumulator_activity_id) 
                self._register_custom_accumulators()
                if self.enable_summary_metrics:
                    self.execution_metrics_orchestrator.start_metrics_poller(
                        accumulator_activity_id=execution_metrics_accumulator_activity_id,
                        activity_display_name=self._get_activity_display_name(),
                        run_id=self.run_id,
                        execution_result=execution_result,
                        start_time=self.start_time
                    )
            except ExecutionMetricsFailedError as e:
                self._get_logger().error(str(e))
            
            # Execute the service
            self._execute(**kwargs)
        except BaseRunnableServiceFailedError as re:
            exceptions.append(re)
            raise
        except Exception as e:
            exceptions.append(e)
            raise
        finally:
            if self.enable_summary_metrics:
                self.execution_metrics_orchestrator.stop_metrics_poller()
            self.spark.sparkContext.setJobGroup("", "")
            self._cleanup(exceptions=exceptions)

    def _get_logger(self) -> DataManagerLogger:
        """
        Retrieves the logger for the service.

        Returns:
            DataManagerLogger: The logger for the service.
        """
        return self._logger

    def _get_activity_display_name(self) -> str:
        """
        Retrieves the activity display name.

        Returns:
            str: The activity display name. Defaults to the notebook name otherwise if not available, the defined internal activity name.
        """
        return self.notebook_name or self._get_internal_activity_name()
    
    def _get_validation_metrics_initial_state(self) -> dict:
        return {
                GC.VALIDATION_DF_TOTAL_KEY: 0,
                GC.VALIDATION_DF_SUCCESSES_KEY: 0,
                GC.VALIDATION_DF_ERRORS_KEY: 0,
                GC.VALIDATION_DF_WARNINGS_KEY: 0
            }

    def get_execution_metrics_accumulator_activity_id(self) -> str:
        """
        Generates the execution metrics accumulator activity ID.

        Returns:
            str: The accumulator activity ID.
        """
        return f"{self._get_internal_activity_name()}_{self.run_id}"

    def _get_validation_metrics_accumulator_activity_id(self) -> str:
        """
        Generates the validation metrics accumulator activity ID.

        Returns:
            str: The validation metrics accumulator activity ID.
        """
        return f"validation_{self._get_internal_activity_name()}_{self.run_id}"

    def _get_default_execution_result(self) -> ExecutionResult:
        """
        Retrieves the default execution result.

        Returns:
            ExecutionResult: The default execution result.
        """
        execution_result: ExecutionResult = ExecutionResult(
                internalExecutionStatus=InternalExecutionStatus.PENDING,
                internalExecutionStatusDetails=self._get_pending_completion_message(),
                executionStatus=ExecutionStatus.PENDING,
                executionStatusDetails=self._get_pending_completion_message(),
                executionMetadata=self.execution_metadata
            )
        
        return execution_result

    def _create_final_execution_result(self, exceptions: List[Exception]) -> ExecutionResult:
        """
        Creates the final execution result based on the presence of exceptions and validation warnings.

        Args:
            exceptions (List[Exception]): List of exceptions encountered during execution.

        Returns:
            ExecutionResult: The final execution result.

        Raises:
            TypeError: If any item in the exceptions list is not of type Exception.
        """
        # Validate that all exceptions are of the correct type
        for exception in exceptions:
            if not isinstance(exception, Exception):
                raise TypeError(f"Expected Exception, got {type(exception).__name__}")

        if len(exceptions) > 0:
            if self.has_validation_errors:
                return ExecutionResult(
                    internalExecutionStatus=InternalExecutionStatus.SUCCEEDED_WITH_ERRORS,
                    internalExecutionStatusDetails=self._get_successful_completion_with_errors_message(exceptions=exceptions),
                    executionStatus=ExecutionStatus.FAILED_WITH_VALIDATION_ERRORS,
                    executionStatusDetails=self._get_successful_completion_with_errors_message(exceptions=exceptions),
                    executionMetadata=self.execution_metadata
                )
            
            return ExecutionResult(
                internalExecutionStatus=InternalExecutionStatus.FAILED,
                internalExecutionStatusDetails=self._get_failed_completion_message(exceptions=exceptions),
                executionStatus=ExecutionStatus.FAILED,
                executionStatusDetails=self._get_failed_completion_message(exceptions=exceptions),
                executionMetadata=self.execution_metadata
            )
        
        if self.has_validations_warnings:
            return ExecutionResult(
                internalExecutionStatus=InternalExecutionStatus.SUCCEEDED,
                internalExecutionStatusDetails=self._get_successful_completion_message(),
                executionStatus=ExecutionStatus.SUCCEEDED_WITH_VALIDATION_WARNINGS,
                executionStatusDetails=self._get_successully_completed_with_validation_warnings_message(),
                executionMetadata=self.execution_metadata
            )
        
        return ExecutionResult(
            internalExecutionStatus=InternalExecutionStatus.SUCCEEDED,
            internalExecutionStatusDetails=self._get_successful_completion_message(),
            executionStatus=ExecutionStatus.SUCCEEDED,
            executionStatusDetails=self._get_successful_completion_message(),
            executionMetadata=self.execution_metadata
        )
        
    def collect_target_delta_table_operation_summary_metrics(self, target_table_path: str, **kwargs) -> None:
        """
        Collects the target delta operation summary metrics.

        Args:
            target_table_path (str): The target table path.
            **kwargs: Additional keyword arguments.
                - num_batches (int, optional): The incremental number of batches processed. Defaults to 1 with the assumption that metrics collection is invoked per batch ingested.
                - operation_type (str, optional): The operation type. Defaults to None.

        Raises:
            ValueError: If any of the required parameters are missing or invalid.
        """
        num_batches: int = kwargs.get("num_batches", 1)
        try:
            if not target_table_path:
                raise ValueError("The target_table_path parameter is required in order to collect the metrics.")
            
            execution_metrics_accumulator_activity_id = self.get_execution_metrics_accumulator_activity_id()
            records_info = get_num_records_delta_op(delta_table_path=target_table_path, spark_session=self.spark)
            table_name = target_table_path.split('/')[-1]
            operation_type = kwargs.get("operation_type", records_info['operation'])
            
            self.execution_metrics_collector.accumulate(
                accumulator_activity_id=execution_metrics_accumulator_activity_id,
                metrics={
                    "numTargetRecords": int(records_info['num_records_persisted']),
                    "targetDataSizeBytes": int(records_info['num_output_bytes']),
                    "batchesProcessed": int(num_batches) if records_info['num_records_persisted'] > 0 else 0,
                    "numTargetRecordsGranular": {
                        table_name: int(records_info["num_records_persisted"])
                    },
                    "activityAttributes": {
                        "numTargetParquetFiles": int(records_info['num_target_files'])
                    }
                }
            )
            
            # Ensure executionAttributes is initialized
            if self.execution_metadata.executionAttributes is None:
                self.execution_metadata.executionAttributes = {}
                
            self.execution_metadata.executionAttributes["operationType"] = operation_type
            new_ts = records_info['operation_timestamp']  # new_ts is a datetime object
            current_ts = self.execution_metadata.executionAttributes.get("operationTimestamp")
            if current_ts is None:
                self.execution_metadata.executionAttributes["operationTimestamp"] = new_ts.isoformat()
            else:
                # Convert current_ts from string to datetime if needed
                current_dt = datetime.fromisoformat(current_ts) if isinstance(current_ts, str) else current_ts
                if new_ts > current_dt:
                    self.execution_metadata.executionAttributes["operationTimestamp"] = new_ts.isoformat()
            
            if operation_type == "MERGE":
                self.execution_metrics_collector.accumulate(
                    accumulator_activity_id=execution_metrics_accumulator_activity_id,
                    metrics={
                        "activityAttributes": {
                            "numRecordsUpdated": int(records_info['num_records_updated']),
                            "numRecordsInserted": int(records_info['num_records_inserted']),
                        }
                    }
                )
            else:
                self.execution_metadata.executionAttributes["operationMode"] = records_info['operation_mode']
            
        except Exception as ex:
            self._get_logger().error(LC.COLLECT_METRICS_FAILED_ERR_MSG.format(
                activity_name=self._get_internal_activity_name(),    
                error_message=str(ex))
            )

    def collect_all_target_tables_metrics(self, table_names: List[str], target_tables_root_path: str) -> None:
        """
        Reusable function to collect metrics for a given list of target tables.
        
        Args:
            table_names (List[str]): A list of table names.
            target_tables_root_path (str): Root path for the target tables.
        """
        try:
            for table in table_names:
                # Build the complete Delta table path.
                target_table_path = f"{target_tables_root_path}/{table}"
                self.collect_target_delta_table_operation_summary_metrics(
                    target_table_path=target_table_path,
                )
        except Exception as ex:
            self._get_logger().error(LC.COLLECT_ALL_TABLES_METRICS_ERR_MSG.format(
                activity_name=self._get_internal_activity_name(),
                target_tables_root_path=target_tables_root_path,
                error_message=str(ex)
            ))
    
    def _get_service_execution_started_message(self) -> str:
        """
        Retrieves the service execution started message.

        Returns:
            str: The service execution started message.
        """
        return LC.SERVICE_EXECUTION_STARTED_INFO_MSG.format(activity_name=self._get_internal_activity_name())
    
    def _get_pending_completion_message(self) -> str:
        """
        Retrieves the pending completion message.

        Returns:
            str: The pending completion message.
        """
        return LC.PENDING_EXECUTION_INFO_MSG.format(activity_name=self._get_internal_activity_name())
    
    def _get_successful_completion_message(self) -> str:
        """
        Retrieves the successful completion message.

        Returns:
            str: The successful completion message.
        """
        return LC.SUCCESSFUL_EXECUTION_INFO_MSG.format(activity_name=self._get_internal_activity_name())
    
    def _get_successful_completion_with_errors_message(self, exceptions: List[Exception]) -> str:
        """
        Retrieves the successful completion with errors message.

        Returns:
            str: The successful completion with errors message.
        """
        return LC.SUCCESSFUL_EXECUTION_WITH_ERRORS_INFO_MSG.format(activity_name=self._get_internal_activity_name(),
                                                                   run_id=self.run_id,
                                                                   error_message=str(exceptions))

    def _get_successully_completed_with_validation_warnings_message(self) -> str:
        """
        Retrieves the successfully completed with validation warnings message.

        Returns:
            str: The execution successfully completed with validation warnings message.
        """
        return LC.SUCCESSFULLY_COMPLETED_WITH_VALIDATION_WARNINGS_MSG.format(activity_name=self._get_internal_activity_name(), 
                                                                             run_id=self.run_id)

    def _get_failed_completion_message(self, exceptions: List[Exception] = None) -> str:
        """
        Retrieves the failed completion message.

        Returns:
            str: The failed completion message.
        """
        if not exceptions:
            error_message = "No specific exceptions provided."
        else:
            error_message = str(exceptions)
            
        return LC.FAILED_EXECUTION_ERR_MSG.format(activity_name=self._get_internal_activity_name(), 
                                                  error_message=error_message)

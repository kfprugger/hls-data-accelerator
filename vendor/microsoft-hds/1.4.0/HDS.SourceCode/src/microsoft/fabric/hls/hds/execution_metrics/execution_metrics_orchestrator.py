# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import json
import time
import threading
from delta import DeltaTable
from pyspark.sql import SparkSession
from pyspark.sql import DataFrame
from pyspark.sql.functions import lit, col, coalesce
from microsoft.fabric.hls.hds.utils.dataframe_utils import upsert_unique_to_delta_managed, stringify_complex_types
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.data_models.execution_result import ExecutionResult
from microsoft.fabric.hls.hds.data_models.execution_metadata import ExecutionDataType
from microsoft.fabric.hls.hds.execution_metrics.base_metrics_collector import BaseMetricsCollector
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.execution_metrics.constants import ExecutionMetricsConstants
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger
from microsoft.fabric.hls.hds.errors.execution_metrics_failed_error import ExecutionMetricsFailedError

class ExecutionMetricsOrchestrator:

    def __init__(self, 
                 spark: SparkSession, 
                 execution_summary_table_path: str, 
                 execution_metrics_collector: BaseMetricsCollector, 
                 logger: DataManagerLogger,
                 metrics_polling_interval_min: int = ExecutionMetricsConstants.DEFAULT_METRICS_POLLING_INTERVAL_IN_MIN,
                 pipeline_run_id: str = None,
                 pipeline_name: str = None,
                 enable_summary_metrics: bool = True):
        """
        Initializes the ExecutionMetricsOrchestrator.

        Args:
            spark (SparkSession): The Spark session.
            execution_summary_table_path (str): Path to the execution summary table.
            execution_metrics_collector (BaseMetricsCollector): The metrics collector.
            logger (DataManagerLogger): Logger for logging information.
            metrics_polling_interval_min (int): Polling interval in minutes for metrics collection.
            pipeline_run_id (str): ID of the pipeline run.
            pipeline_name (str): Name of the pipeline.
            enable_summary_metrics (bool): Flag to enable or disable summary metrics.
        """
        
        self.spark = spark
        self.execution_summary_table_path = execution_summary_table_path
        self.execution_metrics_collector = execution_metrics_collector
        self._logger = logger
        self.enable_summary_metrics = enable_summary_metrics
        self.pipeline_run_id = pipeline_run_id
        self.pipeline_name = pipeline_name
        self.metrics_polling_interval_min = metrics_polling_interval_min
        self._stop_event = threading.Event()
        self._thread = None
        
        self.create_execution_summary_table_if_not_exists()

    def run(self, 
            accumulator_activity_id: str, 
            internal_activity_name: str,
            activity_display_name: str,
            run_id: str, 
            execution_result: ExecutionResult,
            execution_time: float
            ):
        """
        Runs the metrics orchestration process which includes persisting the metrics in the Execution Summary Table 
        as well as emitting a subset of the metrics as part of the library usage metrics.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.
            internal_activity_name (str): Internal name of the activity.
            activity_display_name (str): Display name of the activity.
            run_id (str): ID of the run.
            execution_result (ExecutionResult): Result of the execution.
            execution_time (float, optional): Execution time.
        """
        
        try:
            # Get the summary from the ExecutionMetricsCollector and normalize it
            normalized_summary = self.get_normalized_summary(
                activity_display_name=activity_display_name, 
                accumulator_activity_id=accumulator_activity_id, 
                execution_result=execution_result
            )
            
            self.persist_execution_summary(
                activity_display_name=activity_display_name, 
                run_id=run_id, 
                execution_result=execution_result, 
                summary=normalized_summary, 
                execution_time=execution_time
            )
            
        except ExecutionMetricsFailedError as e:
            self._logger.error(str(e))
            normalized_summary = {}


    def persist_execution_summary(self, 
                                  activity_display_name: str, 
                                  run_id: str, 
                                  execution_result: ExecutionResult, 
                                  summary: dict, 
                                  execution_time: float
                                  ):
        """
        Persists the execution metrics to the ExecutionSummary Delta table.

        Args:
            activity_display_name (str): Display name of the activity.
            run_id (str): ID of the run.
            execution_result (ExecutionResult): Result of the execution.
            summary (dict): Summary of the metrics.
            execution_time (float): Execution time.
        """

        if self.enable_summary_metrics:
            # Generate the default values for the summary
            default_values = self.generate_execution_summary_default_values(activity_display_name, run_id, execution_result, summary, execution_time)

            # Create a DataFrame with the default values
            summary_df: DataFrame = self.spark.createDataFrame([default_values], schema=ExecutionMetricsConstants.DEFAULT_EXECUTION_SUMMARY_TABLE_SCHEMA)

            # Add any additional custom accumulator parameters
            for key, value in summary.items():
                if key not in default_values:
                    if isinstance(value, dict):
                        default_values[key] = value.copy()
                    else:
                        default_values[key] = value

            # Dynamically extend the schema to include additional custom dimensions
            for key, value in default_values.items():
                if key not in summary_df.columns:
                    summary_df = summary_df.withColumn(key, lit(str(value)))

            summary_df = stringify_complex_types(summary_df)
            # Write the summary to the Delta table
            upsert_unique_to_delta_managed(
                spark_session=self.spark,
                data_manager_logger=self._logger,
                df_to_process=summary_df,
                delta_table_path=self.execution_summary_table_path,
                unique_columns=ExecutionMetricsConstants.DEFAULT_EXECUTION_SUMMARY_UNIQUE_COLUMNS,
                source_modified_on_column=ExecutionMetricsConstants.DEFAULT_SOURCE_MODIFIED_DATETIME_COL,
            )
            
            self._logger.info(LC.METRICS_ORCHESTRATOR_INFO_MSG.format(activity_display_name=activity_display_name, 
                                                                    execution_summary_table_path=self.execution_summary_table_path, 
                                                                    run_id=run_id))
            
            self._logger.debug(LC.METRICS_ORCHESTRATOR_SUMMARY_INFO_MSG.format(
                activity_display_name=activity_display_name,
                summary_metrics=json.dumps(default_values, indent=2)))

    def start_metrics_poller(self, 
                    accumulator_activity_id: str,
                    activity_display_name: str, 
                    run_id: str, 
                    execution_result: ExecutionResult, 
                    start_time: float = None
                    ):
        """
        Starts the metrics poller to periodically collect and persist metrics.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.
            activity_display_name (str): Display name of the activity.
            run_id (str): ID of the run.
            execution_result (ExecutionResult): Result of the execution.
            start_time (float, optional): Start time of the polling. Defaults to None.
        """
  
        if self.enable_summary_metrics and int(self.metrics_polling_interval_min) >= int(ExecutionMetricsConstants.DEFAULT_MINIMUM_METRICS_POLLING_INTERVAL_IN_MIN):
            self._logger.info(LC.POLLING_METRICS_STARTED_INFO_MSG.format(activity_display_name=activity_display_name, 
                                                                         metrics_polling_interval_min=self.metrics_polling_interval_min))
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._poll_metrics, 
                args=(accumulator_activity_id,
                      activity_display_name, 
                      run_id, 
                      execution_result, 
                      start_time
                    )
                )
            
            self._thread.start()

    def stop_metrics_poller(self):
        """
        Stops the metrics poller.
        """
        self._logger.info(LC.POLLING_METRICS_STOPPED_INFO_MSG)
        self._stop_event.set()
        if self._thread:
            self._thread.join()
            self._thread = None

    def _poll_metrics(self, 
              accumulator_activity_id: str,  
              activity_display_name: str, 
              run_id: str, 
              execution_result: ExecutionResult, 
              start_time: float
            ):
        """
        Polls metrics at regular intervals and persists them.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.
            activity_display_name (str): Display name of the activity.
            run_id (str): ID of the run.
            execution_result (ExecutionResult): Result of the execution.
            start_time (float): Start time of the polling.
        """

        polling_interval_seconds = self.metrics_polling_interval_min * 60
        check_interval_seconds = 5  # Check every 5 seconds if the stop event is set
        while not self._stop_event.is_set():
            try:
                self._logger.debug(LC.POLLING_METRICS_INFO_MSG.format(polling_interval_seconds=polling_interval_seconds, 
                                                                     activity_display_name=activity_display_name))
                # Get the summary from the ExecutionMetricsCollector
                summary = self.execution_metrics_collector.get_summary(accumulator_activity_id)
                normalized_summary = self._normalize_summary_metrics(summary, execution_result)
                
                execution_time = time.time() - start_time
                self.persist_execution_summary(
                    activity_display_name=activity_display_name, 
                    run_id=run_id, 
                    execution_result=execution_result, 
                    summary=normalized_summary, 
                    execution_time=execution_time
                )
                # Sleep in shorter intervals to allow for responsive stopping
                elapsed_time = 0
                while elapsed_time < polling_interval_seconds and not self._stop_event.is_set():
                    time.sleep(check_interval_seconds)
                    elapsed_time += check_interval_seconds
                    
            except ExecutionMetricsFailedError as e:
                self._logger.error(LC.POLLING_METRICS_FAILED_ERR_MSG.format(activity_display_name=activity_display_name, 
                                                                            error_message=str(e)))
   

    def generate_execution_summary_default_values(
        self, 
        activity_display_name: str, 
        run_id: str, 
        execution_result: ExecutionResult, 
        summary: dict, 
        execution_time: float):
        """
        Generates default values for the execution summary.

        Args:
            activity_display_name (str): Display name of the activity.
            run_id (str): ID of the run.
            execution_result (ExecutionResult): Result of the execution.
            summary (dict): Summary of the metrics.
            execution_time (float): Execution time.

        Returns:
            dict: Default values for the execution summary table.
        """
        metadata = execution_result.executionMetadata
        # Merge activity attributes from the summary and the execution metadata
        activity_attributes = {**summary.get("activityAttributes", {}), **(metadata.executionAttributes if metadata and metadata.executionAttributes else {})}
        
        return {
            "id": f"{activity_display_name}_{run_id}",
            "activityName": activity_display_name,
            "runId": run_id,
            "pipelineRunId": self.pipeline_run_id,
            "pipelineName": self.pipeline_name,
            "executionStatus": execution_result.executionStatus.value,
            "executionStatusDetails": execution_result.executionStatusDetails,
            "numSourceFiles": summary.get("numSourceFiles"),
            "numTargetRecords": summary.get("numTargetRecords"),
            "numTargetRecordsGranular": summary.get("numTargetRecordsGranular", {}),
            "numSourceRecords": summary.get("numSourceRecords"),
            "numSourceRecordsGranular": summary.get("numSourceRecordsGranular", {}),
            "sourceDataSizeBytes": summary.get("sourceDataSizeBytes"),
            "targetDataSizeBytes": summary.get("targetDataSizeBytes"),
            "numTargetFiles": summary.get("numTargetFiles"),
            "batchesProcessed": summary.get("batchesProcessed"),
            "sourceType": metadata.sourceType.value if metadata else None,
            "sourceLakehouseName": metadata.sourceLakehouseName if metadata else None,
            "sourceLakehouseIdentifier": metadata.sourceLakehouseIdentifier if metadata else None,
            "sourcePath": metadata.sourcePath if metadata else None,
            "targetType": metadata.targetType.value if metadata else None,
            "targetLakehouseName": metadata.targetLakehouseName if metadata else None,
            "targetLakehouseIdentifier": metadata.targetLakehouseIdentifier if metadata else None,
            "targetPath": metadata.targetPath if metadata else None,
            "elapsedTime": execution_time,
            "activityAttributes": activity_attributes
        }
    
    def read_metrics(self, run_id: str) -> DataFrame:
        """
        Reads the metrics from the Delta table.

        Args:
            run_id (str): ID of the run.

        Returns:
            DataFrame: DataFrame containing the metrics.
        """
        
        # Read the Delta table into a DataFrame
        return self.spark.read.format("delta").load(self.execution_summary_table_path).filter(f"runId = '{run_id}'")
    
    def create_execution_summary_table_if_not_exists(self) -> None:
        """
        Summary:
            Create execution summary table if not exists
        """
        if not DeltaTable.isDeltaTable(self.spark, self.execution_summary_table_path):
            self._logger.debug(
                f"{LC.CREATING_EXECUTION_SUMMARY_TABLE_INFO_MSG.format(delta_table_path=self.execution_summary_table_path)}"
            )
            empty_summary_df = self.spark.createDataFrame([], schema=ExecutionMetricsConstants.DEFAULT_EXECUTION_SUMMARY_TABLE_SCHEMA)
            # Write the summary to the Delta table
            upsert_unique_to_delta_managed(
                spark_session=self.spark,
                data_manager_logger=self._logger,
                df_to_process=empty_summary_df,
                delta_table_path=self.execution_summary_table_path,
                unique_columns=ExecutionMetricsConstants.DEFAULT_EXECUTION_SUMMARY_UNIQUE_COLUMNS,
                source_modified_on_column=ExecutionMetricsConstants.DEFAULT_SOURCE_MODIFIED_DATETIME_COL,
            )
            
    def _normalize_summary_metrics(self, summary: dict,  execution_result: ExecutionResult) -> dict:
        """
        Processes the raw summary dictionary by applying conditional logic and returns
        a normalized dictionary of metric values.
        
        Args:
            summary (dict): Raw summary dictionary.
            execution_result (ExecutionResult): Result of the execution.
        
        Returns:
            dict: Normalized metrics dictionary.
        """
        # Copy the original summary to preserve all keys
        normalized = summary.copy()
        metadata = execution_result.executionMetadata

        normalized["numSourceFiles"] = (summary.get("numSourceFiles") if metadata and metadata.sourceType == ExecutionDataType.file else None)
        normalized["numTargetFiles"] = (summary.get("numTargetFiles") if metadata and metadata.targetType == ExecutionDataType.file else None)
        normalized["numTargetRecords"] = (summary.get("numTargetRecords") if metadata and metadata.targetType == ExecutionDataType.deltaTable else None)
        
        if metadata and (metadata.sourceType == ExecutionDataType.deltaTable or metadata.sourceType == ExecutionDataType.file):
            num_target_records = normalized.get("numTargetRecords") or 0
            num_source_records = summary.get("numSourceRecords") or 0
            num_source_files = normalized.get("numSourceFiles") or 0
            num_target_files = normalized.get("numTargetFiles") or 0

            if metadata.targetType == ExecutionDataType.deltaTable and num_target_records > 0 and num_source_records < 1:
                normalized["numSourceRecords"] = None
            elif metadata.sourceType == ExecutionDataType.file and num_target_files > 0 and num_source_files < 1:
                normalized["numTargetRecords"] = None
            else:
                normalized["numSourceRecords"] = summary.get("numSourceRecords")
        else:
            normalized["numSourceRecords"] = None
        
        normalized["numTargetRecordsGranular"] = (summary.get("numTargetRecordsGranular", {}) if metadata and metadata.targetType == ExecutionDataType.deltaTable else {})
        normalized["numSourceRecordsGranular"] = (summary.get("numSourceRecordsGranular", {}) if metadata and metadata.targetType == ExecutionDataType.deltaTable else {})
        normalized["sourceDataSizeBytes"] = (
            summary.get("sourceDataSizeBytes")
            if ((normalized.get("numSourceFiles") or 0) > 0 or (normalized.get("numSourceRecords") or 0) > 0)
            and summary.get("sourceDataSizeBytes", 0) > 0
            else None
        )
        normalized["targetDataSizeBytes"] = (
            summary.get("targetDataSizeBytes")
            if ((normalized.get("numTargetFiles") or 0) > 0 or (normalized.get("numTargetRecords") or 0) > 0)
            and summary.get("targetDataSizeBytes", 0) > 0
            else None
        )

        return normalized

    def metrics_record_exists_for_activity_and_timestamp(self, activity_display_name: str, target_timestamp: str) -> bool:
        """
        Checks whether a record exists in the Execution Summary Delta table with the specified activityName
        and an activityAttributes.operationTimestamp equal to the target_timestamp.

        Args:
            activity_display_name (str): The display name of the activity.
            target_timestamp (str): The target operation timestamp (stored as an ISO-formatted string).

        Returns:
            bool: True if a matching record exists, False otherwise.
        """
        # Read the execution summary Delta table
        summary_df = self.spark.read.format("delta").load(self.execution_summary_table_path)
        
        # Filter by the activity name and nested operationTimestamp
        filtered_df = summary_df.filter(
            (col("activityName") == activity_display_name) &
            (coalesce(col("activityAttributes.operationTimestamp"), lit("")) == target_timestamp)
        )
        
        # Check if there's at least one matching record
        return filtered_df.limit(1).count() > 0
    
    def get_normalized_summary(self, activity_display_name: str, accumulator_activity_id: str, execution_result: ExecutionResult) -> dict:
        """
        Retrieves the raw summary from the ExecutionMetricsCollector, normalizes it using the internal _normalize_summary_metrics method,
        and returns the normalized summary.

        Args:
            accumulator_activity_id (str): The accumulator activity ID used to retrieve the summary.
            execution_result (ExecutionResult): The execution result containing additional metadata.

        Returns:
            dict: The normalized summary metrics dictionary.
        """
        try:
            # Ensure executionAttributes is initialized
            if execution_result.executionMetadata.executionAttributes is None:
                execution_result.executionMetadata.executionAttributes = {}
                
            target_operation_timestamp = execution_result.executionMetadata.executionAttributes.get("operationTimestamp")
            if not target_operation_timestamp or target_operation_timestamp.strip() == "":
                target_operation_timestamp = None
            
            # Reset the accumulator if a record already exists for the activity and timestamp to avoid duplicate entries for the same operation
            if self.metrics_record_exists_for_activity_and_timestamp(
                activity_display_name=activity_display_name,
                target_timestamp=target_operation_timestamp
            ):
                # Reset the accumulator to avoid duplicate metric entries for the same operation
                self.execution_metrics_collector.reset_accumulator(accumulator_activity_id)
            
            summary = self.execution_metrics_collector.get_summary(accumulator_activity_id)
            normalized_summary = self._normalize_summary_metrics(summary, execution_result)
            return normalized_summary
        except Exception as e:
            self._logger.error(f"Error retrieving and normalizing summary: {str(e)}.")
            return {}

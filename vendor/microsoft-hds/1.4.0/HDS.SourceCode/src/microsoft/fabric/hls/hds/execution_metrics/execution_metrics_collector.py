# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import copy
from pyspark.sql import SparkSession
from pyspark.accumulators import AccumulatorParam
from microsoft.fabric.hls.hds.execution_metrics.base_metrics_collector import BaseMetricsCollector
from microsoft.fabric.hls.hds.execution_metrics.execution_metrics_accumulator_param import ExecutionMetricsAccumulatorParam
from microsoft.fabric.hls.hds.execution_metrics.constants import ExecutionMetricsConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.errors.execution_metrics_failed_error import ExecutionMetricsFailedError

class ExecutionMetricsCollector(BaseMetricsCollector):
    """
    A class for accumulating execution metrics, extending the BaseMetricsCollector.
    """
    def __init__(self, spark: SparkSession):
        """
        Initializes the ExecutionMetricsCollector.

        Args:
            spark (SparkSession): The Spark session.
            initial_state (dict, optional): Initial state of the accumulator. Defaults to ExecutionMetricsAccumulatorParam.
        """
        super().__init__(
            spark = spark
        )

    def register_accumulator(self, accumulator_activity_id: str, accumulator_param: AccumulatorParam = None, initial_state: dict = None) -> None:
        """
        Registers a new accumulator for the given activity ID.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.
            accumulator_param (AccumulatorParam, optional): The accumulator_param to be registered. Defaults to ExecutionMetricsAccumulatorParam.
            initial_state (dict, optional): The initial state for the accumulator. Defaults to None.

        Raises:
            ExecutionMetricsFailedError: If the accumulator activity ID is already registered or if the metrics are invalid.
        """
        if accumulator_activity_id in self.accumulators_dict:
            raise ExecutionMetricsFailedError(LC.METRICS_DUPLICATE_ACCUMULATOR_ERR_MSG.format(accumulator_activity_id=accumulator_activity_id))
                
        accumulator_param = accumulator_param if accumulator_param else ExecutionMetricsAccumulatorParam()
        initial_state = initial_state if initial_state else copy.deepcopy(ExecutionMetricsConstants.DEFAULT_INITIAL_STATE)    
        self.validate_metrics(metrics=initial_state)
        
        self.initial_state_dict[accumulator_activity_id] = copy.deepcopy(initial_state)
        
        self.accumulators_dict[accumulator_activity_id] = self.spark.sparkContext.accumulator(initial_state, accumulator_param)
            
    def validate_metrics(self, metrics: dict) -> None:
        """
        Validates the provided execution metrics.

        Args:
            metrics (dict): Metrics to be validated.

        Raises:
            ExecutionMetricsFailedError: If the metrics are invalid.
        """
        if not isinstance(metrics, dict):
            raise ExecutionMetricsFailedError(LC.METRICS_INVALID_METRICS_DATATYPE_ERR_MSG.format(metrics=metrics))
        for key, value in metrics.items():
            if not isinstance(key, str):
                raise ExecutionMetricsFailedError(LC.METRICS_INVALID_METRICS_KEY_ERR_MSG.format(key=key))
            
            if key in ExecutionMetricsConstants.GRANULAR_METRICS_KEYS:
                if not isinstance(value, dict):
                    raise ExecutionMetricsFailedError(LC.METRICS_INVALID_GRANULAR_METRICS_DATATYPE_ERR_MSG.format(key=key, value=value))
                for table_name, count in value.items():
                    if not isinstance(table_name, str):
                        raise ExecutionMetricsFailedError(LC.METRICS_INVALID_GRANULAR_METRICS_KEY_ERR_MSG.format(table_name=table_name))
                    if not isinstance(count, int):
                        raise ExecutionMetricsFailedError(LC.METRICS_INVALID_GRANULAR_METRICS_VALUE_ERR_MSG.format(table_name=table_name, count=count))
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if not isinstance(sub_key, str):
                        raise ExecutionMetricsFailedError(LC.METRICS_INVALID_METRICS_KEY_ERR_MSG.format(key=sub_key))
                    if not isinstance(sub_value, (int, float)):
                        raise ExecutionMetricsFailedError(LC.METRICS_INVALID_METRICS_VALUE_ERR_MSG.format(key=sub_key, value=sub_value))
            elif not isinstance(value, (int, float)):
                raise ExecutionMetricsFailedError(LC.METRICS_INVALID_METRICS_VALUE_ERR_MSG.format(key=key, value=value))

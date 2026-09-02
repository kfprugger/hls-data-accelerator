# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import os
import copy
from abc import ABC, abstractmethod
from pyspark.sql import SparkSession
from pyspark.accumulators import AccumulatorParam, Accumulator
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants as GC
from microsoft.fabric.hls.hds.errors.execution_metrics_failed_error import ExecutionMetricsFailedError

class BaseMetricsCollector(ABC):
    """
    A base class for Summary Collectors to allow customization for specific use cases.
    """

    def __init__(self, spark: SparkSession):
        """
        Initializes the BaseMetricsCollector.

        Args:
            spark (SparkSession): The Spark session.
        """
 
        self.spark = spark
        self.accumulators_dict: dict[str, Accumulator] = {}
        self.initial_state_dict: dict[str, dict] = {}
        
        # Used to enable/disable the accumulation of metrics for dev purposes i.e unit tests
        self.enable_accumulators = spark.conf.get(GC.SPARK_ENABLE_HDS_COLLECT_METRICS, "true").lower() == "true"
    
    def accumulate(self, accumulator_activity_id: str, metrics: dict) -> None:
        """
        Accumulates the provided execution metrics.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.
            metrics (dict): Metrics to be accumulated.
        """
        if self.enable_accumulators:
            self.validate_metrics(metrics)
            accumulator = self.get_accumulator(accumulator_activity_id)
            accumulator += metrics

    def accumulate_single(self, accumulator_activity_id: str, metrics_key: str, value: int | float) -> None:
        """
        Accumulates a single metric value.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.
            metrics_key (str): Key of the metric to be accumulated.
            value (int | float): Value of the metric to be accumulated.
        """
        # Create a dictionary with the key and value to increment
        metrics = {metrics_key: value}
        self.accumulate(accumulator_activity_id, metrics)
    
    def get_accumulator(self, accumulator_activity_id: str) -> Accumulator:
        """
        Retrieves the accumulator for the given activity ID.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.

        Returns:
            Accumulator: The accumulator for the given activity ID.

        Raises:
            ExecutionMetricsFailedError: If the accumulator activity ID is not found.
        """
        if accumulator_activity_id not in self.accumulators_dict:
            raise ExecutionMetricsFailedError(LC.METRICS_INVALID_ACCUMULATOR_ERR_MSG.format(accumulator_activity_id=accumulator_activity_id))
        return self.accumulators_dict[accumulator_activity_id]

    def get_summary(self, accumulator_activity_id: str) -> dict:
        """
        Retrieves a summary of the accumulated metrics.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.

        Returns:
            dict: Summary of the accumulated metrics.
        """
        accumulator = self.get_accumulator(accumulator_activity_id)
        return copy.deepcopy(accumulator.value)

    def get_initial_state(self, accumulator_activity_id: str) -> dict:
        """
        Retrieves the initial state of the accumulator.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.

        Returns:
            dict: Initial state of the accumulator.
        """
        if accumulator_activity_id not in self.accumulators_dict:
            raise ExecutionMetricsFailedError(LC.METRICS_INVALID_ACCUMULATOR_ERR_MSG.format(accumulator_activity_id=accumulator_activity_id))
        
        return copy.deepcopy(self.initial_state_dict[accumulator_activity_id])
    
    def reset_accumulator(self, accumulator_activity_id: str) -> None:
        """
        Resets the accumulator for the given activity ID.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.

        Raises:
            ValueError: If the accumulator activity ID is not found.
        """
        if self.enable_accumulators:
            accumulator_param = self.get_accumulator(accumulator_activity_id)
            initial_state = self.get_initial_state(accumulator_activity_id)
            self.accumulators_dict[accumulator_activity_id] = self.spark.sparkContext.accumulator(initial_state, accumulator_param)

    def reset_accumulators(self) -> None:
        """
        Resets all accumulators.
        """
        
        for accumulator_activity_id in self.accumulators_dict:
            self.reset_accumulator(accumulator_activity_id)

    @abstractmethod
    def register_accumulator(self, accumulator_activity_id: str, accumulator_param: AccumulatorParam = None, initial_state: dict = None) -> None:
        """
        Abstract method to register an accumulator_param.
        Must be implemented by derived classes.

        Args:
            accumulator_activity_id (str): ID of the accumulator activity.
            accumulator_param (AccumulatorParam, optional): The accumulator_param to be registered. Defaults to None.
            initial_state (dict, optional): The initial state for the accumulator_param. Defaults to None.
        """
        
        raise NotImplementedError
    
    @abstractmethod
    def validate_metrics(self, metrics: dict) -> None:
        """
        Abstract method to validate the accumulator metrics/values.
        Must be implemented by derived classes.

        Args:
            metrics (dict): Metrics to be validated.
        """
        raise NotImplementedError
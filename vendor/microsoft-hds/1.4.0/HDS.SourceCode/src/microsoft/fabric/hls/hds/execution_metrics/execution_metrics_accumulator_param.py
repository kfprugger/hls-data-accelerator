# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import copy
from pyspark.accumulators import AccumulatorParam
from microsoft.fabric.hls.hds.execution_metrics.constants import ExecutionMetricsConstants

class ExecutionMetricsAccumulatorParam(AccumulatorParam):
    """
    A custom AccumulatorParam for accumulating execution metrics in a dictionary.
    """
    def zero(self, initial_state: dict):
        """
        Initializes the accumulator with the default state.

        Args:
            initial_state (dict): The initial state of the accumulator.

        Returns:
            dict: A deep copy of the initial state.
        """
        return copy.deepcopy(initial_state)
    
    def addInPlace(self, acc_dict: dict, incremental_dict: dict):
        """
        Merges incremental values into the accumulator.

        Args:
            acc_dict (dict): The accumulator dictionary.
            incremental_dict (dict): The dictionary with incremental values to be added.

        Returns:
            dict: The updated accumulator dictionary with merged values.
        """
        for key, value in incremental_dict.items():
            if key in ExecutionMetricsConstants.GRANULAR_METRICS_KEYS:
                acc_dict.setdefault(key, {})
                for table_name, count in value.items():
                    acc_dict[key][table_name] = acc_dict[key].get(table_name, 0) + count
            else:
                if isinstance(value, dict):
                    acc_dict.setdefault(key, {})
                    for sub_key, sub_value in value.items():
                        acc_dict[key][sub_key] = acc_dict[key].get(sub_key, 0) + sub_value
                else:
                    acc_dict[key] = acc_dict.get(key, 0) + value
        return acc_dict

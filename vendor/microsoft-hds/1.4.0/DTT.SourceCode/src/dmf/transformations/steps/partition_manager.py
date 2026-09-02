from typing import List

from pyspark.sql import DataFrame

from dmf.transformations.model.transformation_types import PartitionConfig


class PartitionManager:
    """
        Given parsed input from partitionRules in LakeDBSemantics configuration, this class can generate expressions for
        partition columns for tables. Those expressions are used to compute needed partition columns
        """

    @staticmethod
    def add_partition(source_df: DataFrame, partition_configs: List[PartitionConfig]) -> DataFrame:
        partition_cols_expressions = [
            PartitionManager._partition_expression(pc) for pc in partition_configs]
        if partition_cols_expressions:
            return source_df.selectExpr('*', *partition_cols_expressions)
        else:
            return source_df.selectExpr('*')

    @staticmethod
    def filter_target_by_source_partitions(source_df: DataFrame, target_df: DataFrame,
                                           partition_col_names: List[str]) -> DataFrame:
        if not partition_col_names:
            return target_df
        unique_partitions_df = PartitionManager._distinct_partitions(
            source_df, partition_col_names)
        return PartitionManager._filter(target_df, partition_col_names, unique_partitions_df)

    @staticmethod
    def get_partition_column_names(partition_configs: List[PartitionConfig]) -> List[str]:
        return [pc.partition_col_name for pc in partition_configs]

    @staticmethod
    def _distinct_partitions(partitioned_source_df: DataFrame, partition_col_names: List[str]) -> DataFrame:
        return partitioned_source_df.select(*partition_col_names).distinct()

    @staticmethod
    def _partition_expression(partition_config: PartitionConfig) -> str:
        _partition_calc_expression = PartitionManager._parse_partition_rule(
            partition_config.input_col_to_partition_col_rule, partition_config.input_col_name)
        _partition_type = partition_config.partition_col_type.simpleString()
        return f"CAST(({_partition_calc_expression}) AS {_partition_type}) {partition_config.partition_col_name}"

    @staticmethod
    def _parse_partition_rule(partitioning_rule: str, partition_col_name: str) -> str:
        return partitioning_rule.format(partition_col_name)

    @staticmethod
    def _filter(target_df: DataFrame, partition_col_names: List[str], unique_partitions_df: DataFrame) -> DataFrame:
        return target_df.join(unique_partitions_df, on=partition_col_names, how='inner')

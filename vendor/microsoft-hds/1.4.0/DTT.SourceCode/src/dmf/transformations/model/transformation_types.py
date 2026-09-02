from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional

from pyspark.sql import DataFrame
from pyspark.sql.types import DataType


@dataclass
class PartitionConfig:
    # todo better name?
    input_col_name: str
    partition_col_name: str
    input_col_to_partition_col_rule: str
    partition_col_type: DataType


@dataclass(eq=True, frozen=True)
class Source2TargetIdMapping:
    source_id_col_name: str
    target_id_col_name: str
    id_mapping_df_name: str

    def __str__(self) -> str:
        return f"Source2TargetIdMapping(source_id_col_name={self.source_id_col_name}, target_id_col_name={self.target_id_col_name})"


@dataclass
class TransformationData:
    source_df: DataFrame
    target_df: DataFrame
    id_mappings_df: Dict[str, DataFrame]


@dataclass
class TransformationMetaData:
    source_partitions_configs: List[PartitionConfig]
    source_modified_date_col_name: str
    source_key_col_names: List[str]
    source_data_col_names: FrozenSet[str]
    source_deleted_status_col_name: Optional[str]
    source_active_status_col_name: Optional[str]
    target_key_col_names: List[str]
    target_key_col_names_for_duration_transformation: Optional[List[str]]
    target_data_col_names: FrozenSet[str]
    target_schema_col_names: FrozenSet[str]
    target_modified_date_col_name: str
    target_period_start_col_name: str
    target_period_end_col_name: str
    source_to_target_ids_mapping: List[Source2TargetIdMapping]
    source_ids_with_conditions: List[str]
    source_to_target_col_names_mapping: Dict[str, List[str]]
    synthetically_nulled_primary_keys: FrozenSet[str]
    feed_id: str

    @property
    def writable_columns(self) -> List[str]:
        from dmf.transformations.steps.partition_manager import PartitionManager

        partition_columns = PartitionManager.get_partition_column_names(self.source_partitions_configs)
        return list(
            set(
                item for sublist in self.source_to_target_col_names_mapping.values()
                for item in sublist) |
            set(self.target_key_col_names) |
            self.synthetically_nulled_primary_keys |
            {self.target_period_start_col_name, self.target_period_end_col_name} |
            set(partition_columns)
        )

import json
from collections import defaultdict
from typing import FrozenSet

from configuration_compiler.config_files_models.common.field_type import CommonParsing
from configuration_compiler.config_files_models.semantics_config.model import RawSemanticsConfigModel
from dmf.model.target_configuration.target_configuration import PartitionConfig


class SemanticsConfigModel(RawSemanticsConfigModel):
    @classmethod
    def from_str(cls, semantics_config_str: str) -> "SemanticsConfigModel":
        try:
            return cls(**json.loads(semantics_config_str))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse 'semantics-config' file: {e}")

    @property
    def _partition_rules(self):
        config = defaultdict(list)
        for partition_rule in self.partitionRules:
            if not partition_rule.enabled:
                continue
            for partition_input_field in partition_rule.fields:
                (
                    partitioned_table_name,
                    partition_input_col,
                ) = partition_input_field.split(".", maxsplit=2)
                partition_config = PartitionConfig(
                    input_col_name=partition_input_col,
                    partition_col_name=partition_rule.name,
                    input_col_to_partition_col_rule=partition_rule.rule,
                    partition_col_type=CommonParsing.parse_field_type(partition_rule.type),
                )
                config[partitioned_table_name].append(partition_config)
        return config

    def partition_rules_for_table(self, table_name) -> FrozenSet[PartitionConfig]:
        try:
            return frozenset(self._partition_rules[table_name])
        except KeyError:
            return frozenset()

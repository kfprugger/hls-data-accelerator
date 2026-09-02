from collections import defaultdict
from typing import Dict, List, Set

from rmt.core.core_exceptions import MappingSourceValueAlreadyExistsError
from rmt.core.data_management.primitive_types import MappingChanged, SourceValue, TargetKey


class TableMapping:

    @property
    def table_name(self) -> str:
        return self._table_name

    @property
    def target_to_source_mapping(self) -> Dict[TargetKey, Set[SourceValue]]:
        return self._target_to_source_mapping.copy()

    def __init__(self, table_name: str) -> None:
        self._table_name = table_name
        self._target_to_source_mapping: Dict[TargetKey, Set[SourceValue]] = defaultdict(set)
        self._source_values: Set[SourceValue] = set()

    def __eq__(self, __value: object) -> bool:
        if isinstance(__value, TableMapping):
            return self.table_name == __value.table_name and self._target_to_source_mapping == __value.target_to_source_mapping
        else:
            raise ValueError(f"Invalid comparison between TableMapping and {type(__value)}")

    def add_target_mapping(self, target_key: TargetKey, source_values: List[SourceValue]) -> MappingChanged:

        result = False
        if target_key not in self._target_to_source_mapping:

            result = True
        for table_target_key, table_source_values in self._target_to_source_mapping.items():
            if target_key != table_target_key:
                for source_value in source_values:
                    if source_value in table_source_values:
                        raise MappingSourceValueAlreadyExistsError(self._table_name, source_value)

        for source_value in source_values:
            result = result or source_value not in self._target_to_source_mapping[target_key]
            self._target_to_source_mapping[target_key].add(source_value)

        return result

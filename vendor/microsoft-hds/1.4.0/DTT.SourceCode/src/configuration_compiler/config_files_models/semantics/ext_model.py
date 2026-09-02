import json
from collections import defaultdict
from typing import Set

from configuration_compiler.config_files_models.common.types import ChildId, ParentId
from configuration_compiler.config_files_models.semantics.model import RawSemanticsModel, ReferenceTable
from dmf.model.target_configuration.target_configuration import TemporalColumns


class SemanticsModel(RawSemanticsModel, extra="allow"):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__duration_tables_dict = None
        self.__reference_tables_dict = None

    @classmethod
    def from_str(cls, target_db_semantics_str: str) -> "SemanticsModel":
        try:
            return cls(**json.loads(target_db_semantics_str))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse target DB semantics file: {e}")

    @property
    def reference_tables_names(self):
        return set(t.table for t in self.referenceTables)

    @property
    def reference_tables_dict(self) -> dict[str, ReferenceTable]:
        if self.__reference_tables_dict is None:
            self.__reference_tables_dict = {table.table: table for table in self.referenceTables}
        return self.__reference_tables_dict

    @property
    def duration_tables_dict(self):
        if self.__duration_tables_dict is None:
            self.__duration_tables_dict = {table.table: table for table in self.durationTables}
        return self.__duration_tables_dict

    def is_reference_table(self, table: str) -> bool:
        return table in self.reference_tables_dict

    def is_duration_table(self, table: str) -> bool:
        return table in self.duration_tables_dict

    @property
    def temporal_tables(self) -> dict[str, TemporalColumns]:
        return {
            t.table: TemporalColumns(start_col_name=t.startField, end_col_name=t.endField) for t in self.durationTables
        }

    @property
    def extension_tables(self) -> dict[ParentId, Set[ChildId]]:
        result = defaultdict(set)
        for table in self.extensionTables:
            result[table.parentTable].add(table.childTable)
        return dict(result)

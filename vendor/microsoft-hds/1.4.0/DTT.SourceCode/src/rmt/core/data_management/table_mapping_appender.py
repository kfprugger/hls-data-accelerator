from typing import List

from rmt.core.core_exceptions import TableMappingAddError, UpdateValueError
from rmt.core.data_management.table_mapping import TableMapping


class TableMappingAppender:

    @property
    def table_mapping(self) -> TableMapping:
        return self._table_mapping

    @property
    def errors(self) -> List[UpdateValueError]:
        return self._errors

    def __init__(self, table_name: str):
        self._table_mapping = TableMapping(table_name)
        self._errors: List[UpdateValueError] = []

    def append(self, table_mapping: TableMapping) -> bool:
        """
        Add the table mapping with the provided table mapping.
        Run on all provided table mapping target_to_source mapping
        and add them to the instance table mapping
        raises an exception with the aggregated errors
        in case there was an update return True, otherwise False
        """

        if self._table_mapping.table_name != table_mapping.table_name:
            raise TableMappingAddError(self._table_mapping.table_name, table_mapping.table_name)

        result = False
        for target_key, source_values in table_mapping.target_to_source_mapping.items():
            try:
                result = self._table_mapping.add_target_mapping(target_key, source_values) or result
            except UpdateValueError as e:
                self._errors.append(e)

        return result

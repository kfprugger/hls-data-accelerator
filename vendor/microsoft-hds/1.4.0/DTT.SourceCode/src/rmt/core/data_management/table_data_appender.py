from typing import List

from rmt.core.core_exceptions import TableDataAddError, UpdateValueError
from rmt.core.data_management.table_data import TableData


class TableDataAppender:
    """
    this class is used to append TableData from different contributors to one TableData
    it is currently used to validate all the data of a table
    """

    @property
    def errors(self) -> List[UpdateValueError]:
        return self._errors

    @property
    def table_data(self) -> TableData:
        return self._table_data

    def __init__(self, table_name: str):
        self._table_data = TableData(table_name)
        self._errors: List[UpdateValueError] = []

    def append(self, table_data: TableData) -> bool:
        """
        Add to the instance table data the date entries of the table data.
        Run on all provided table data entries and raises an exception with the aggregated errors
        in case there was an update return True, otherwise False
        """

        if self._table_data.table_name != table_data.table_name:
            raise TableDataAddError(self._table_data.table_name, table_data.table_name)
        result = False
        for data_entry in table_data.entries:
            try:
                result = self._table_data.add_data_entry(data_entry) or result
            except UpdateValueError as e:
                self._errors.append(e)

        return result

from typing import Set

from rmt.core.core_exceptions import EntryKeyAlreadyExistsError, EntryNameAlreadyExistsError
from rmt.core.data_management.primitive_types import DataChanged


class DataEntry:

    def __init__(self, key: int, name: str):
        self.key = key
        self.name = name

    def __str__(self) -> str:
        return f"DataEntry(key={self.key}, name={self.name})"

    def __repr__(self):
        return self.__str__()

    def __hash__(self) -> int:
        return hash(str(self.key) + self.name)

    def __eq__(self, __value: object) -> bool:
        if isinstance(__value, DataEntry):
            return self.key == __value.key and self.name == __value.name
        else:
            raise ValueError(f"Invalid comparison between DataEntry and {type(__value)}")


class TableData:
    """
    this class holds the data of a table.
    it holds the table name and a set of DataEntry of the table
    the only way to add data to the table is by using the add_data_entry method
    which validates the data before adding it to the table
    thus the data in the TableData is always valid
    (The class is used to store the data of each contributor per table)
    """

    @property
    def entries(self) -> Set[DataEntry]:
        return frozenset(self._entries)

    @property
    def table_name(self) -> str:
        return self._table_name

    def __init__(self, table_name: str):
        self._table_name = table_name
        self._entries: Set[DataEntry] = set()
        self._keys: Set[int] = set()
        self._names: Set[str] = set()

    def add_data_entry(self, data_entry: DataEntry) -> DataChanged:
        if data_entry in self._entries:
            return False
        if data_entry.key in self._keys:
            raise EntryKeyAlreadyExistsError(self._table_name, data_entry.key)
        if data_entry.name in self._names:
            raise EntryNameAlreadyExistsError(self._table_name, data_entry.name)
        self._entries.add(data_entry)
        self._keys.add(data_entry.key)
        self._names.add(data_entry.name)
        return True

    def key_exist_in_data(self, key: int) -> bool:
        return key in self._keys

    def __eq__(self, __value: object) -> bool:
        if isinstance(__value, TableData):
            return self.table_name == __value.table_name and self.entries == __value.entries
        else:
            raise ValueError(f"Invalid comparison between TableData and {type(__value)}")

    def __str__(self) -> str:
        return f"TableData(table={self.table_name}, entries={self._entries}"

    def __repr__(self):
        return self.__str__()

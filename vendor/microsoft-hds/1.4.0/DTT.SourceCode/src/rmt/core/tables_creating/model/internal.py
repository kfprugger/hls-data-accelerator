from typing import Any

from pyspark.sql.types import DataType


class TableColumn:
    def __init__(self, name: str, type: DataType, is_nullable: bool):
        self.name = name
        self.type = type
        self.is_nullable = is_nullable


class ReferenceTable:
    def __init__(self, table_name: str, key_field: str, name_field: str, columns: list[TableColumn]) -> None:
        self.table_name = table_name
        self.key_field = key_field
        self.name_field = name_field
        self.columns = columns[:]

    def __str__(self):
        return f"ReferenceTable(table={self.table_name}, keyField={self.key_field}, nameField={self.name_field}, columns={self.columns})"

    def __repr__(self):
        return self.__str__()


class ReferenceTableFieldMapping:
    def __init__(self, adrmFieldName: str, referenceFieldName: str) -> None:
        self.adrmFieldName = adrmFieldName
        self.referenceFieldName = referenceFieldName

    def __str__(self):
        return f"ReferenceTableFieldMapping(adrmFieldName={self.adrmFieldName}, referenceFieldName={self.referenceFieldName})"

    def __repr__(self):
        return self.__str__()


class ReferenceTableData:
    def __init__(self, adrmTableName: str, fieldMapping: list[ReferenceTableFieldMapping], data: list[dict[str, Any]]) -> None:
        self.adrmTableName = adrmTableName
        self.fieldMapping = fieldMapping[:]
        self.data = data[:]

    def __str__(self) -> str:
        return f"ReferenceTableData(table={self.adrmTableName}, fieldMapping={self.fieldMapping}, data={self.data})"

    def __repr__(self):
        return self.__str__()

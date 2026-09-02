from pyspark.sql.types import DataType, StructField, StructType


class TableColumn:
    def __init__(self, name: str, type: DataType, is_nullable: bool):
        self.name = name
        self.type = type
        self.is_nullable = is_nullable

    def __str__(self):
        return f"TableColumn(name={self.name}, type={self.type}, isNullable={self.is_nullable})"


class TableSchema:
    def __init__(self, table_name: str, key_field: str, name_field: str, columns: list[TableColumn]):
        self.table_name = table_name
        self.key_field = key_field
        self.name_field = name_field
        self.columns = columns[:]

    def __str__(self):
        return f"TableSchema(table={self.table_name}, keyField={self.key_field}, nameField={self.name_field}, columns={self.columns})"

    def __repr__(self):
        return self.__str__()

    def to_schema(self) -> StructType:
        return StructType([StructField(c.name, c.type, c.is_nullable) for c in self.columns])

class ReferenceTable:
    def __init__(self, table_name: str, key_field_name: str, name_field_name: str):
        self.table_name = table_name
        self.key_field = key_field_name
        self.name_field = name_field_name

    def __str__(self):
        return f"ReferenceTable(table={self.table_name}, keyField={self.key_field}, nameField={self.name_field})"

    def __repr__(self):
        return self.__str__()

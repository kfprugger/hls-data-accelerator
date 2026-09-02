from rmt.contract.configuration.reference_table import ReferenceTable
from rmt.core.data_management.table_data import DataEntry, TableData
from rmt.file_model.data_file_model import DataFileModel, FieldMapping

DATA_FIELD_NAME_ID = "id"
DATA_FIELD_NAME_NAME = "name"


class TableDataFileModelAdapter:

    @staticmethod
    def to_core_model(file_model: DataFileModel, reference_table: ReferenceTable) -> TableData:
        key_field = None
        name_field = None
        for f in file_model.fieldMapping:
            if f.adrmFieldName == reference_table.key_field:
                key_field = f.referenceFieldName
            elif f.adrmFieldName == reference_table.name_field:
                name_field = f.referenceFieldName
        if key_field is None:
            raise ValueError(f"Key field {reference_table.key_field} not found in data definition field mapping")
        if name_field is None:
            raise ValueError(f"Name field {reference_table.name_field} not found in data_definition field mapping")

        table_date = TableData(file_model.adrmTableName)
        error_messages = []
        result = True
        try:
            for item in file_model.data:
                table_date.add_data_entry(DataEntry(item[key_field], item[name_field]))
        except ValueError as e:
            result = False
            error_messages.append(str(e))

        if not result:
            raise ValueError("\n".join(error_messages))

        return table_date

    @staticmethod
    def from_core_model(core_model: TableData, reference_table: ReferenceTable) -> DataFileModel:
        return DataFileModel(
            adrmTableName=core_model.table_name,
            fieldMapping=[
                FieldMapping(adrmFieldName=reference_table.key_field, referenceFieldName=DATA_FIELD_NAME_ID),
                FieldMapping(adrmFieldName=reference_table.name_field, referenceFieldName=DATA_FIELD_NAME_NAME),
            ],
            data=[{DATA_FIELD_NAME_ID: entry.key, DATA_FIELD_NAME_NAME: entry.name} for entry in core_model.entries],
        )

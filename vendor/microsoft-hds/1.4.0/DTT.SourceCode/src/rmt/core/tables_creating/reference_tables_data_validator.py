from collections import Counter, defaultdict
from enum import Enum
from typing import Dict, List

import rmt.core.logger as logger
from rmt.core.tables_creating.model.internal import ReferenceTable, ReferenceTableData


class InvalidReferenceTableDataError(Exception):
    def __init__(self, message, **context):
        super().__init__(message)
        self.context = context

    def __str__(self):
        context = "\n".join([f"{key}: {value}" for key, value in self.context.items()]) if self.context else "no context"
        return f"{super().__str__()}\n{context}"


class UnknownReferenceTableNameError(InvalidReferenceTableDataError):
    pass


class UnMappedKeyFieldError(InvalidReferenceTableDataError):
    pass


class UnMappedNameFieldError(InvalidReferenceTableDataError):
    pass


class UnPopulatedFieldError(InvalidReferenceTableDataError):
    pass


class DuplicateIdsInReferenceDataError(InvalidReferenceTableDataError):
    pass


class DuplicateNamesInReferenceDataError(InvalidReferenceTableDataError):
    pass


class MapppedColumn(Enum):
    KEY = 1
    NAME = 2


class ReferenceTablesDataValidator:
    def __init__(
        self,
        reference_tables_data: dict[str, list[ReferenceTableData]],
        reference_tables: Dict[str, ReferenceTable],
    ) -> None:
        self._reference_tables = reference_tables
        self._reference_tables_data = reference_tables_data

    def validate(self):
        errors = []
        errors += self._validate_key_and_name_are_mapped()
        errors += self._validate_key_and_name_fields_are_populated()
        errors += self._validate_non_null_fields_are_always_popuplated()
        errors += self._validate_ids_are_unique()
        errors += self._validate_names_are_unique()
        if errors:
            logger.error("Reference tables data is invalid")
            raise InvalidReferenceTableDataError("Invalid reference tables data", errors=errors)
        logger.info("Reference tables data is valid")

    def _validate_key_and_name_are_mapped(self) -> List[InvalidReferenceTableDataError]:
        errors = []
        for table_name, tables_data in self._reference_tables_data.items():
            if table_name in self._reference_tables:
                ref_table_definition = self._reference_tables[table_name]
                for table_data in tables_data:
                    mapped_fields = [mapping.adrmFieldName for mapping in table_data.fieldMapping]
                    if ref_table_definition.key_field not in mapped_fields:
                        errors.append(UnMappedKeyFieldError(f"Table {table_name} is missing key field {ref_table_definition.key_field} definition"))
                    if ref_table_definition.name_field not in mapped_fields:
                        errors.append(UnMappedNameFieldError(f"Table {table_name} is missing name field {ref_table_definition.name_field} definition"))
        return errors

    def _validate_key_and_name_fields_are_populated(self) -> List[InvalidReferenceTableDataError]:
        errors = []

        for table_name, tables_data in self._reference_tables_data.items():
            if table_name in self._reference_tables:
                ref_table_definition = self._reference_tables[table_name]
                for table_data in tables_data:
                    table_data_field_mappings = {mapping.adrmFieldName: mapping.referenceFieldName for mapping in table_data.fieldMapping}
                    key_mapping = table_data_field_mappings.get(ref_table_definition.key_field)
                    name_mapping = table_data_field_mappings.get(ref_table_definition.name_field)
                    for row_num, data_row in enumerate(table_data.data):
                        if key_mapping and key_mapping not in data_row:
                            errors.append(UnPopulatedFieldError(f"Table {table_name} is missing key field {ref_table_definition.key_field} definition for data row {row_num+1}"))
                        if name_mapping and name_mapping not in data_row:
                            errors.append(UnPopulatedFieldError(f"Table {table_name} is missing name field {ref_table_definition.name_field} definition for data row {row_num+1}"))
        return errors

    def _validate_ids_are_unique(self) -> List[InvalidReferenceTableDataError]:
        return self._validate_columns_are_unique_across_all_rows(MapppedColumn.KEY)

    def _validate_names_are_unique(self) -> List[InvalidReferenceTableDataError]:
        return self._validate_columns_are_unique_across_all_rows(MapppedColumn.NAME)

    def _validate_columns_are_unique_across_all_rows(self, column_type: MapppedColumn) -> List[InvalidReferenceTableDataError]:
        errors = []
        all_values = defaultdict(list)
        for table_name, tables_data in self._reference_tables_data.items():
            if table_name in self._reference_tables:
                if column_type == MapppedColumn.KEY:
                    column_name = self._reference_tables[table_name].key_field
                elif column_type == MapppedColumn.NAME:
                    column_name = self._reference_tables[table_name].name_field
                else:
                    raise ValueError(f"column_type must be one of {list(k.name for k in MapppedColumn)}")
                for table_data in tables_data:
                    column_in_table = None  # if unmapped (an error), will stay None
                    for field_mapping in table_data.fieldMapping:
                        if field_mapping.adrmFieldName == column_name:
                            column_in_table = field_mapping.referenceFieldName
                            break
                    if column_in_table:
                        all_values[table_name] += [row[column_in_table] for row in table_data.data if column_in_table in row]
        for table_name, names in all_values.items():
            name_counts = Counter(names)
            duplicate_values = [id for id, count in name_counts.items() if count > 1]
            if duplicate_values:
                errors.append(DuplicateNamesInReferenceDataError(f"Table {table_name} has duplicate value(s): {duplicate_values}"))
        return errors

    def _validate_non_null_fields_are_always_popuplated(self) -> List[InvalidReferenceTableDataError]:
        errors = []
        for table_name, tables_data in self._reference_tables_data.items():
            if table_name in self._reference_tables:
                ref_table_definition_non_nullable_columns = [col.name for col in self._reference_tables[table_name].columns if not col.is_nullable]
                for table_data in tables_data:
                    required_keys = []
                    for field_mapping in table_data.fieldMapping:
                        if field_mapping.adrmFieldName in ref_table_definition_non_nullable_columns:
                            required_keys.append(field_mapping.referenceFieldName)
                    for row_num, data_row in enumerate(table_data.data):
                        for key in required_keys:
                            if key not in data_row:
                                errors.append(
                                    UnPopulatedFieldError(f"Table {table_name} is missing key field {key}, row: {row_num+1} which is not nullable in reference table definition")
                                )
        return errors

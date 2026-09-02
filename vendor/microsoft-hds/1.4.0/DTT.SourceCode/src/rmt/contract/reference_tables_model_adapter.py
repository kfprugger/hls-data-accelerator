from typing import Dict, List

from rmt.contract.configuration.reference_table import ReferenceTable, TableColumn
from rmt.core.data_management.reference_table_schema import ReferenceTableColumn, ReferenceTableSchema


class ReferenceTablesModelAdapter:

    @staticmethod
    def to_core_models(reference_tables: List[ReferenceTable]) -> Dict[str, ReferenceTableSchema]:
        result: Dict[str, ReferenceTableSchema] = {}
        for reference_table in reference_tables:
            result[reference_table.table_name] = ReferenceTablesModelAdapter._to_core_model(reference_table)
        return reference_tables

    @staticmethod
    def _to_core_model(reference_table: ReferenceTable) -> ReferenceTableSchema:
        return ReferenceTableSchema(
            reference_table.table_name,
            reference_table.key_field,
            reference_table.name_field,
            [ReferenceTablesModelAdapter._to_core_column(column) for column in reference_table.columns],
        )

    @staticmethod
    def _to_core_column(column: TableColumn) -> ReferenceTableColumn:
        return ReferenceTableColumn(column.name, column.type, column.is_nullable)

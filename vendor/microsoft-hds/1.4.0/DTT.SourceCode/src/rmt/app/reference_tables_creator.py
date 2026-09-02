from pyspark.sql import SparkSession

from rmt.contract.configuration.reference_table import ReferenceTable, TableColumn
from rmt.core.tables_creating.model.internal import ReferenceTable as InternalReferenceTable
from rmt.core.tables_creating.model.internal import ReferenceTableData
from rmt.core.tables_creating.model.internal import TableColumn as InternalTableColumn
from rmt.core.tables_creating.reference_tables_data_reader import ReferenceTablesDataReader
from rmt.core.tables_creating.reference_tables_data_validator import ReferenceTablesDataValidator
from rmt.core.tables_creating.reference_tables_writer import ReferenceTablesWriter as Writer


class ReferenceTablesCreator:
    @staticmethod
    def create_reference_data_tables(
        spark: SparkSession,
        target_path: str,
        reference_tables: dict[str, ReferenceTable],
        tables_reader: ReferenceTablesDataReader,
    ):
        reference_tables_data: dict[str, list[ReferenceTableData]] = tables_reader.read()
        reference_tables: dict[str, InternalReferenceTable] = ReferenceTablesCreator._convert_to_internal_model(reference_tables)
        ReferenceTablesDataValidator(reference_tables_data, reference_tables).validate()
        Writer(spark, reference_tables_data, reference_tables, target_path).overwrite()

    @staticmethod
    def _convert_to_internal_model(reference_tables):
        return {k: ReferenceTablesCreator._to_internal_model_table(table) for k, table in reference_tables.items()}

    @staticmethod
    def _to_internal_model_table(table: ReferenceTable) -> InternalReferenceTable:
        return InternalReferenceTable(
            table_name=table.table_name,
            key_field=table.key_field,
            name_field=table.name_field,
            columns=[ReferenceTablesCreator._to_internal_column(c) for c in table.columns],
        )

    @staticmethod
    def _to_internal_column(column: TableColumn) -> InternalTableColumn:
        return InternalTableColumn(
            name=column.name,
            type=column.type,
            is_nullable=column.is_nullable,
        )

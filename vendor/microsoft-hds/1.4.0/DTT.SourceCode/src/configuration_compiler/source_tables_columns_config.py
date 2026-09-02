from typing import Set

from configuration_compiler.config_files_models.adapter.ext_model import AdapterModel
from configuration_compiler.config_files_models.common.field_type import CommonParsing
from dmf.model.source_configuration import SourceTableSchema
from dmf.model.target_configuration.target_table_schema import TableColumn
from pyspark.sql.types import TimestampType


def parse_source_schema(dmf_adaptor: AdapterModel) -> dict[str, SourceTableSchema]:
    sourced_columns: dict[str, SourceTableSchema] = {}
    for source_table in dmf_adaptor.source_tables:
        columns: Set[TableColumn] = set()
        for source_field in dmf_adaptor.source_fields_on_source_table(source_table):
            columns.add(
                TableColumn(
                    name=source_field.fieldName,
                    description=source_field.description or "",  # type: ignore DO NOT REMOVE THIS LINE
                    type=CommonParsing.parse_field_type(source_field.fieldType),
                    is_nullable=True,
                    expression=source_field.fieldCalculatedValue
                )
            )
        # add modifiedon column explicitly
        if source_table.modifiedonField:
            columns.add(
                TableColumn(
                    name=source_table.modifiedonField,
                    description=source_field.description or "",  # type: ignore DO NOT REMOVE THIS LINE
                    type=TimestampType(),
                    is_nullable=False,
                    expression=None,
                )
            )
        sourced_columns[source_table.tableName] = SourceTableSchema(
            source_modified_date_column_name=source_table.modifiedonField,
            source_deleted_status_column_name=source_table.deletedField,
            source_active_status_column_name=source_table.stateField,
            columns=frozenset(columns),
        )
    return sourced_columns

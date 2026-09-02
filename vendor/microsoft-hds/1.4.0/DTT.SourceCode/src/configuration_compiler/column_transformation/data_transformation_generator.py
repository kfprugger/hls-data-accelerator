from typing import Optional

from configuration_compiler.column_transformation.ids_mapping_helper import IdsMappingHelper
from configuration_compiler.config_files_models.adapter.model import SourceField, TargetField
from configuration_compiler.config_files_models.common.field_type import CommonParsing
from configuration_compiler.config_files_models.utils.target_table_schema_utils import TargetTableSchemaUtils
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.types import DataSourceId
from dmf.model.target_configuration.target_table_schema import TableColumn
from dmf.model.target_configuration.target_transformation import ColumnTransformation


class UnknownForeginKeyException(Exception):
    pass


class DataTransformationGenerator:
    def __init__(
        self,
        target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt],
        ids_mapping_helper: IdsMappingHelper,
        bypass_keys_harmonization: bool,
    ):
        self.target_tables_schemas = target_tables_schemas
        self.ids_mapping_helper = ids_mapping_helper
        self.bypass_keys_harmonization = bypass_keys_harmonization

    def generate_data_transformation(
        self, source_field: SourceField, target_field: TargetField
    ) -> Optional[ColumnTransformation]:
        target_table = self.target_tables_schemas[target_field.tableName]
        if target_table.is_ref_table:
            return None
        target_field_name = target_field.fieldName
        target_column = TargetTableSchemaUtils.get_column(target_table, target_field_name)
        should_be_id_mapped = self.ids_mapping_helper.should_map(self.bypass_keys_harmonization, target_table.id, target_field_name)
        owner_table = self._get_real_owner(target_column, target_table, target_table.id)

        transformation = ColumnTransformation(
            transformation_target_id=target_table.id,
            original_source_field_name=source_field.fieldName,
            target_field_name=target_field_name,
            target_field_type=target_column.type,
            source_field_type=CommonParsing.parse_field_type(source_field.fieldType),
            target_field_value=target_field.fieldValue,
            is_source_primary_key=target_column.is_primary_key,
            target_field_condition=target_field.condition,
            owner_target_id=owner_table,
            should_be_id_mapped=should_be_id_mapped,
            has_source_field=True,
        )
        return transformation

    def _get_real_owner(self, column: TableColumn, table: TargetTableSchemaExt, target_table_id: str):
        if column.is_fk:
            owner_table = TargetTableSchemaUtils.get_table_pointed_by_fk(table, column.name)
            if not owner_table:
                raise UnknownForeginKeyException(f"FK field '{column.name}' in table '{table.id}' does not point to any table")
        else:
            owner_table = target_table_id
        return owner_table

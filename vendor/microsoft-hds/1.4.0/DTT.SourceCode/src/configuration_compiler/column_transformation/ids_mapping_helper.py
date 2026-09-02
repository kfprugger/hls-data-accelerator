from typing import Optional
from configuration_compiler.config_files_models.utils.target_table_schema_utils import TargetTableSchemaUtils

from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from pyspark.sql.types import IntegerType, LongType
from common.model.types import DataSourceId


class IdsMappingHelper:
    def __init__(self, target_tables_schemas: dict[str, TargetTableSchemaExt]):
        self.target_tables_schemas = target_tables_schemas

    def should_map(self, bypass_keys_harmonization: bool, target_table_name: str, target_field_name: str) -> bool:
        if bypass_keys_harmonization:
            return False
        target_table_schema = self.target_tables_schemas[target_table_name]
        if not self._is_long_or_integer(target_field_name, target_table_schema):
            return False
        pointed_table = TargetTableSchemaUtils.get_table_pointed_by_fk(target_table_schema, target_field_name)
        if self._is_fk_to_ref_table(pointed_table):
            return False
        if self._is_fk_to_non_ref_table(pointed_table):
            return True
        if target_table_schema.is_ref_table:
            return False
        if not self._is_pk(target_field_name, target_table_schema):
            return False
        pointed_by_other_tables = bool(TargetTableSchemaUtils.pointed_by(target_table_schema))
        is_a_single_pk_on_table = self._is_a_single_pk(target_table_schema)
        if not (pointed_by_other_tables or is_a_single_pk_on_table):
            return False
        return True

    def _is_fk_to_non_ref_table(self, pointed_table: Optional[DataSourceId]):
        if not pointed_table:
            return False
        is_pointing_to_ref_table = self.target_tables_schemas[pointed_table].is_ref_table
        return not is_pointing_to_ref_table

    def _is_fk_to_ref_table(self, pointed_table: Optional[DataSourceId]):
        if not pointed_table:
            return False
        is_pointing_to_ref_table = self.target_tables_schemas[pointed_table].is_ref_table
        return is_pointing_to_ref_table

    def _is_long_or_integer(self, target_field_name: str, target_schema: TargetTableSchemaExt) -> bool:
        return TargetTableSchemaUtils.get_column_type(target_schema, target_field_name) in (
            IntegerType(),
            LongType(),
        )

    def _is_pk(self, target_column_name, target_schema: TargetTableSchemaExt):
        return TargetTableSchemaUtils.get_column(target_schema, target_column_name).is_primary_key

    def _is_a_single_pk(self, target_schema: TargetTableSchemaExt):
        return 1 == len(TargetTableSchemaUtils.primary_keys(target_schema))

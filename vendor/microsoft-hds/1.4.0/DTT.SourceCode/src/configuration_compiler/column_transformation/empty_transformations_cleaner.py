from typing import Set, Tuple

from configuration_compiler.config_files_models.utils.target_table_schema_utils import TargetTableSchemaUtils
from configuration_compiler.spec_models.target_table_schema import TargetTableColumn, TargetTableSchemaExt
from common.model.types import DataSourceId
from dmf.model.target_configuration.target_transformation import ColumnTransformation


class EmptyTransformationsCleaner:
    def __init__(self, target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt]):
        self.target_tables_schemas = target_tables_schemas

    def clean(
        self,
        transformations_from_source_table: dict[DataSourceId, Set[ColumnTransformation]],
    ):
        """if we have fk transformations which refer tables without data transformations, we remove them.
        This is because we don't want to generate fk values for tables without data.
        for that matter, ref tables are not considered as tables with data always
        """
        target_tables_with_non_pk_fields = self._find_tables_with_data_transformations(
            transformations_from_source_table
        )
        keys_to_remove = self._mark_transformations_for_removal(
            target_tables_with_non_pk_fields, transformations_from_source_table
        )
        self._remove_transformations(keys_to_remove, transformations_from_source_table)

    def _find_tables_with_data_transformations(
        self, transformations_from_source_table: dict[str, Set[ColumnTransformation]]
    ) -> Set[str]:
        def is_data_column(_column: TargetTableColumn, _table: TargetTableSchemaExt):
            if _table.is_duration_table:
                return _column.name not in _table.duration_semantics.group_by_cols
            return not _column.is_primary_key

        target_tables_with_data_fields = set()
        for (
            target_table_name,
            target_transformations,
        ) in transformations_from_source_table.items():
            target_table = self.target_tables_schemas[target_table_name]
            for transformation in target_transformations:
                target_column = TargetTableSchemaUtils.get_column(target_table, transformation.target_field_name)
                owner_table = self.target_tables_schemas[transformation.owner_target_id]
                if owner_table.is_ref_table:
                    # we treat ref tables as if they always have data
                    target_tables_with_data_fields.add(owner_table.id)
                if is_data_column(target_column, target_table):
                    # a writing to a pk is not writing data
                    target_tables_with_data_fields.add(target_table_name)
        return target_tables_with_data_fields

    def _mark_transformations_for_removal(
        self,
        target_tables_with_data_fields: Set[str],
        transformations_from_source_table: dict[str, Set[ColumnTransformation]],
    ) -> list[Tuple[str, str]]:
        """
        if we have transformations which write to a pk of a table and those are the only transformations for that table,
        we remove them. This is because we don't want to generate pk values for tables without data.
        """
        keys_to_remove = []
        for (
            target_table_name,
            target_transformations,
        ) in transformations_from_source_table.items():
            for transformation in target_transformations:
                if transformation.transformation_target_id not in target_tables_with_data_fields:
                    keys_to_remove.append((target_table_name, transformation.target_field_name))
        return keys_to_remove

    def _remove_transformations(
        self,
        keys_to_remove: list[Tuple[str, str]],
        transformations_from_source_table: dict[str, Set[ColumnTransformation]],
    ):
        for target_table_name, target_field_name in keys_to_remove:
            transformations = transformations_from_source_table[target_table_name]
            filtered_transformations = set(t for t in transformations if t.target_field_name != target_field_name)
            if filtered_transformations:
                transformations_from_source_table[target_table_name] = filtered_transformations
            else:
                del transformations_from_source_table[target_table_name]

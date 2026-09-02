from typing import Set

from configuration_compiler.config_files_models.utils.target_table_schema_utils import TargetTableSchemaUtils
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.types import DataSourceId, TargetId
from dmf.model.target_configuration.target_transformation import ColumnTransformation
from pyspark.sql.types import NullType


class NoPrimaryKeysException(Exception):
    pass


class MissingPKsFiller:
    """
    This class is responsible for filling in missing primary keys in the target tables.

    The main algorithm of this class works as follows:
    1. For each target table, it checks if there are any primary keys that are not mapped in the transformations.
    2. If there are missing primary keys, it generates a transformation for each missing primary key.
       The transformation assigns a NULL value to the missing primary key.
    3. The generated transformations are then added to the transformations_from_source_table attribute.
    """

    def __init__(
        self,
        target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt],
        transformations_from_source_table: dict[str, Set[ColumnTransformation]],
    ):
        self.target_tables_schemas = target_tables_schemas
        self.transformations_from_source_table = transformations_from_source_table

    def fill_in_unmapped_primary_keys(self):
        pk_transformations = set()
        for target_id, transformations_for_target in self.transformations_from_source_table.items():
            missing_pks = self._detect_missing_pks_for_target(target_id, transformations_for_target)
            if missing_pks:
                pk_transformations |= self._generate_missing_pks_for_target(target_id, missing_pks)
        if pk_transformations:
            self._update_generated_transformations(pk_transformations)

    def _detect_missing_pks_for_target(
        self, target_id: TargetId, transformations_for_target: Set[ColumnTransformation]
    ):
        target_table = self.target_tables_schemas[target_id]
        if target_table.is_duration_table:
            required_pks = list(target_table.duration_semantics.group_by_cols)
        else:
            required_pks = [col.name for col in TargetTableSchemaUtils.primary_keys(target_table)]
        missing_pks = set(required_pks)
        for transformation in transformations_for_target:
            field_name = transformation.target_field_name
            missing_pks.discard(field_name)
        if missing_pks == required_pks:
            raise NoPrimaryKeysException(f"No primary keys for target table '{target_id}' were mapped in the adapter")
        return missing_pks

    def _generate_missing_pks_for_target(self, target_id: str, missing_pks: Set[str]) -> Set[ColumnTransformation]:
        """
        Generate a transformation for each missing PK. A NULL value will be assigned.
        """
        target_table = self.target_tables_schemas[target_id]
        pk_transformations = set()
        for pk in missing_pks:
            column = TargetTableSchemaUtils.get_column(target_table, pk)
            transformation = ColumnTransformation(
                transformation_target_id=target_id,
                original_source_field_name="STUB",
                target_field_name=pk,
                target_field_type=column.type,
                source_field_type=NullType(),
                target_field_value=None,
                is_source_primary_key=False,
                target_field_condition=None,
                owner_target_id=target_id,
                #  this is because there is no source field for this transformation (see original_source_field_name)
                has_source_field=False,
                should_be_id_mapped=False,  # since its value is always NULL anyway
            )
            pk_transformations.add(transformation)
        return pk_transformations

    def _update_generated_transformations(self, pk_transformations: Set[ColumnTransformation]):
        for transformation in pk_transformations:
            self.transformations_from_source_table[transformation.transformation_target_id].add(transformation)

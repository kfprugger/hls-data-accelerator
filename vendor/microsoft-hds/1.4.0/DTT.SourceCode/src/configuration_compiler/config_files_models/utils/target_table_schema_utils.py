from typing import FrozenSet, Optional
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.types import DataSourceId
from dmf.model.target_configuration.target_table_schema import (
    TargetTableColumn,
    TableRelation,
)
from pyspark.sql.types import DataType


class TargetTableSchemaUtils:
    @staticmethod
    def primary_keys(t: TargetTableSchemaExt) -> FrozenSet[TargetTableColumn]:
        return frozenset(column for column in t.columns if column.is_primary_key)

    @staticmethod
    def is_extension(t: TargetTableSchemaExt) -> bool:
        return bool(TargetTableSchemaUtils.parent_table(t))

    @staticmethod
    def parent_table(t: TargetTableSchemaExt) -> Optional[DataSourceId]:
        """Returns the table which is extended by this table, if any.
        currently this solves only a single field PK and a single parent table
        """
        if len(TargetTableSchemaUtils.primary_keys(t)) != 1:
            return None
        pk = next(iter(TargetTableSchemaUtils.primary_keys(t)))
        for relation in t.relations:
            for fk in relation.foreign_keys:
                if fk.from_attribute == pk.name:
                    return relation.to_entity
        return None

    @staticmethod
    def columns_names(t: TargetTableSchemaExt) -> FrozenSet[str]:
        return frozenset(column.name for column in t.columns)

    @staticmethod
    def get_column(t: TargetTableSchemaExt, column_name: str) -> TargetTableColumn:
        for column in t.columns:
            if column.name == column_name:
                return column
        raise ValueError(
            f"Field '{column_name}' was not found in the field list {t.id}: [{list(TargetTableSchemaUtils.columns_names(t))}]"
        )

    @staticmethod
    def get_column_type(t: TargetTableSchemaExt, column_name: str) -> DataType:
        return TargetTableSchemaUtils.get_column(t, column_name).type

    @staticmethod
    def get_table_pointed_by_fk(t: TargetTableSchemaExt, fk: str) -> Optional[DataSourceId]:
        for relation in t.relations:
            for foreign_key in relation.foreign_keys:
                if foreign_key.from_attribute == fk:
                    return relation.to_entity
        return None

    @staticmethod
    def get_relations_pointing_to_table_id(t: TargetTableSchemaExt, table_id: str) -> set[TableRelation]:
        relations = set()
        for relation in t.relations:
            if relation.to_entity == table_id:
                relations.add(relation)
        return relations

    @staticmethod
    def get_relations_pointing_to_table(t1: TargetTableSchemaExt, t2: TargetTableSchemaExt) -> set[TableRelation]:
        return TargetTableSchemaUtils.get_relations_pointing_to_table_id(t1, t2.id)

    @staticmethod
    def get_self_relations(t: TargetTableSchemaExt) -> set[TableRelation]:
        return TargetTableSchemaUtils.get_relations_pointing_to_table(t, t)

    __pointed_by_cache = {}

    @staticmethod
    def pointed_by(t: TargetTableSchemaExt) -> FrozenSet[DataSourceId]:
        key = t.id
        if key in TargetTableSchemaUtils.__pointed_by_cache:
            return TargetTableSchemaUtils.__pointed_by_cache[key]
        result = frozenset(relation.from_entity for relation in TargetTableSchemaUtils.get_self_relations(t))
        TargetTableSchemaUtils.__pointed_by_cache[key] = result
        return result

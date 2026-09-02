from dataclasses import dataclass
from typing import Set

from configuration_compiler.column_transformation.tables_path_resolver import TableNamesPair
from configuration_compiler.config_files_models.utils.table_relation_utils import copy_with_fks
from configuration_compiler.config_files_models.utils.target_table_schema_utils import TargetTableSchemaUtils
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from dmf.model.target_configuration.target_table_schema import ForeignKey, TableRelation
from pyspark.sql.types import DataType


@dataclass(frozen=True)
class Relationship:
    origin: TargetTableSchemaExt
    destination: TargetTableSchemaExt
    relation: TableRelation

    def get_fk_type(self, fk: ForeignKey) -> DataType:
        return TargetTableSchemaUtils.get_column(self.origin, fk.from_attribute).type

    def __str__(self):
        if self.relation is None:
            return f"Relationship({self.origin.id}->{self.destination.id} [])"
        return f"Relationship({self.origin.id}->{self.destination.id} [{self.relation}])"

    def __repr__(self):
        return str(self)


class RelationshipsGenerator:
    """
    Given a sequence of table names pairs, this class generates a sequence of tables pairs.
    a `Relationship`, is a pair of tables, with a relation between them.
    if 2 tables have more than one relation between them, then there will be more than one `TablesPair` for the corresponding `TableNamesPair`
    if a `TableNamesPair` is a pair of the same table, `Relationship` for it with no relation.
    """

    def __init__(self, target_tables_schemas: dict[str, TargetTableSchemaExt]):
        self.target_tables_schemas = target_tables_schemas

    def compute_relationships(self, table_names_pairs: Set[TableNamesPair]) -> Set[Relationship]:
        relationships = set()
        for tnp in table_names_pairs:
            left_table = self.target_tables_schemas[tnp.left]
            right_table = self.target_tables_schemas[tnp.right]
            # look at both directions to find fks
            relationships |= self._compute_relationships_for_name_pair(left_table, right_table)
            relationships |= self._compute_relationships_for_name_pair(right_table, left_table)

        return relationships

    def _compute_relationships_for_name_pair(
        self, left: TargetTableSchemaExt, right: TargetTableSchemaExt
    ) -> Set[Relationship]:
        relationships = set()
        for rel in TargetTableSchemaUtils.get_relations_pointing_to_table(left, right):
            fks_pointing_to_pk = []
            for fk in rel.foreign_keys:
                if TargetTableSchemaUtils.get_column(right, fk.to_attribute).is_primary_key:
                    fks_pointing_to_pk.append(fk)
            if fks_pointing_to_pk:
                relationships.add(Relationship(left, right, copy_with_fks(rel, fks_pointing_to_pk)))
        return relationships

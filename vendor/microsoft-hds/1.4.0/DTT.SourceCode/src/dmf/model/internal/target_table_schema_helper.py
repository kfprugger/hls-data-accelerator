from typing import Set

from dmf.model.target_configuration.target_table_schema import TableRelation, TargetTableSchema


class TargetTableSchemaHelper:
    @staticmethod
    def _get_relations_pointing_to_table_id(table_schema: TargetTableSchema, table_id: str) -> Set[TableRelation]:
        relations = set()
        for relation in table_schema.relations:
            if relation.to_entity == table_id:
                relations.add(relation)
        return relations

    @staticmethod
    def get_relations_pointing_to_table(table_schema: TargetTableSchema, table_id: str) -> Set[TableRelation]:
        return TargetTableSchemaHelper._get_relations_pointing_to_table_id(table_schema, table_id)

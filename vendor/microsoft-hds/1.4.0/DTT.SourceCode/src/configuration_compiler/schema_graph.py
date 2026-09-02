import functools

from configuration_compiler.graph.graph import Graph
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.types import DataSourceId


class SchemaGraph:
    def __init__(self, target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt]):
        self._graph = Graph()
        for table_name in target_tables_schemas.keys():
            self._graph.add_node(table_name)
        for table_schema in target_tables_schemas.values():
            for relation in table_schema.relations:
                self._graph.add_two_way_edge(relation.from_entity, relation.to_entity)

    @functools.lru_cache(maxsize=1000)
    def shortest_paths(self, source_id, target_id) -> list[list[str]]:
        return self._graph.find_all_shortest_paths(source_id, target_id, max_allowed_node_in_path=4)

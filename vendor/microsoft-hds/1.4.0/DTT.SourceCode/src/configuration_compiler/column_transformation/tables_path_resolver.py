from dataclasses import dataclass
from typing import Any, List, Set, Tuple

from configuration_compiler.graph.graph import NoNodeException
from configuration_compiler.graph.levenshtein_distance import levenshtein_distance
from configuration_compiler.config_files_models.adapter.model import TargetField
from configuration_compiler.config_files_models.common.types import AnchorId
from configuration_compiler.config_files_models.utils.target_table_schema_utils import TargetTableSchemaUtils
from configuration_compiler.schema_graph import SchemaGraph
from configuration_compiler.spec_models.target_table_schema import TargetTableSchemaExt
from common.model.types import DataSourceId, TargetId


@dataclass(frozen=True)
class TableNamesPair:
    left: str
    right: str


class PathResolutionException(Exception):
    pass


class TablesPathResolver:
    """given a list of anchor tables names, and a single target table name,
    this class computes all the possible paths between any anchor to the target.
    It then generates a list of table pairs that correspond to each pair of connected tables
    along that path.
    high level flow:
    1. compute all the possible paths between any anchor to the target
    2. filter out paths that are invalid see `_is_valid_path`
    3. sort the paths by their score (low score means better path)- see `_path_score`
    4. take the best path (for each anchor-target pair)
    5. for each path, generate a list of table pairs that correspond to each pair of connected tables
    """

    def __init__(self,
                 anchor_tables: List[str],
                 schema_graph: SchemaGraph,
                 target_tables_schemas: dict[DataSourceId, TargetTableSchemaExt],
                 tables_paths: dict[DataSourceId, dict[TargetId, List[TargetId]]],
                 source_table_name: str,
                 target_field: TargetField):
        self.anchor_tables = anchor_tables
        self.target_field = target_field
        self.schema_graph = schema_graph
        self.target_tables_schemas = target_tables_schemas
        self.tables_paths = tables_paths
        self.source_table_name = source_table_name

    def generate_pairs(self) -> Set[TableNamesPair]:
        pairs = set()
        paths_overrides_per_source = self.tables_paths.get(self.source_table_name, {})
        specific_paths = paths_overrides_per_source.get(self.target_field.tableName, None)
        if specific_paths:
            paths = [specific_paths]
        else:
            paths = self._compute_shortest_paths(self.anchor_tables, self.target_field.tableName)
        for path in paths:
            pairs |= self.tables_path_to_tables_pairs(path)
        return pairs

    def tables_path_to_tables_pairs(self, path) -> Set[TableNamesPair]:
        path_pairs = set()
        for left, right in self._generate_pairs_from_path(path):
            path_pairs.add(TableNamesPair(left, right))
        return path_pairs

    def get_proposed_paths(self) -> List[List[TargetId]]:
        """for each anchor return the shortest path to the target table
        1. for each anchor and target pair there are multiple paths potentially
        2. for each set of paths, filter out the paths that are not valid (see _is_path_valid)
        """
        anchors = self.anchor_tables
        target = self.target_field.tableName
        try:
            paths_to_target = {anchor_id: self.schema_graph.shortest_paths(anchor_id, target) for anchor_id in anchors}
            paths_to_target_filtered = self._filter_all_paths(paths_to_target)

        except NoNodeException as e:
            raise PathResolutionException(
                f"Could not find path from {anchors} to {target}. Is a table missing from the schema?"
            ) from e
        return self._flatten_one_level(list(paths_to_target_filtered.values()))

    def _compute_shortest_paths(self, anchors: List[str], target: str) -> List[List[TargetId]]:
        """for each anchor return the shortest path to the target table
        1. for each anchor and target pair there are multiple paths potentially
        2. for each set of paths, filter out the paths that are not valid (see _is_path_valid)
        3. for each set of paths, take the best path (see _take_approximated_best_paths)
        """
        try:
            paths_to_target = {anchor_id: self.schema_graph.shortest_paths(anchor_id, target) for anchor_id in anchors}
            paths_to_target_filtered = self._filter_all_paths(paths_to_target)
            paths_to_target_approximated = self._take_approximated_best_paths(paths_to_target_filtered)

        except NoNodeException as e:
            raise PathResolutionException(
                f"Could not find a valid path from an anchor table to target table '{target}'. None of anchor tables '{anchors}' fits"
            ) from e
        return paths_to_target_approximated

    def _is_path_valid(self, path: List[TargetId]) -> bool:
        if not self._is_path_starts_with_correct_target_field(path):
            return False
        if self._is_trivial_path(path):
            return True
        if self._path_has_3_tables_with_intermediate_duration_or_extension(path):
            return True
        if self._path_has_4_tables_with_intermediate_duration_and_extension(path):
            return True
        return False

    def _generate_pairs_from_path(self, path: List[str]) -> Set[Tuple[str, str]]:
        if len(path) == 1:
            return {(path[0], path[0])}

        pairs = set()
        for i in range(len(path) - 1):
            pairs.add((path[i], path[i + 1]))
        return pairs

    def _is_trivial_path(self, path: List[TargetId]) -> bool:
        return len(path) <= 2

    def _path_has_3_tables_with_intermediate_duration_or_extension(self, path: List[TargetId]) -> bool:
        if len(path) != 3:
            return False
        intermediate_table = self.target_tables_schemas[path[1]]
        return intermediate_table.is_duration_table or TargetTableSchemaUtils.is_extension(intermediate_table)

    def _path_has_4_tables_with_intermediate_duration_and_extension(self, path: List[TargetId]) -> bool:
        """
        can be:
        1. anchor -> extension-> duration -> target (like customer and marital_status)
        2. anchor -> duration -> ? -> extension (like branch and bank)
        """
        if len(path) != 4:
            return False
        _, table1, table2, table3 = [self.target_tables_schemas[target_id] for target_id in path]
        if TargetTableSchemaUtils.is_extension(table1) and table2.is_duration_table:
            # e.g. customer <- individualCustomer -> cusrtomerMaritalStatus <- maritalStatus
            return True
        if table1.is_duration_table and TargetTableSchemaUtils.is_extension(table3):
            # e.g. customer <- customerRelatedChannel -> channel <- branch
            return True
        return False

    def _take_approximated_best_paths(self, paths_to_target_by_anchor: dict[AnchorId, List[List[TargetId]]]) -> List[List[TargetId]]:
        best_paths = []
        for paths_to_target in paths_to_target_by_anchor.values():
            best_paths.append(self._take_best_path(paths_to_target))
        return best_paths

    def _take_best_path(self, paths_to_target: List[List[TargetId]]) -> List[TargetId]:
        """if there are multiple paths of the same length, take the one with the smallest levenshtein distance
        between the intermediate tables and the outer tables
        TODO: this is a heuristic, maybe we can do better
        """
        if len(paths_to_target) == 1:
            return paths_to_target[0]
        path_length = len(paths_to_target[0])
        if path_length <= 2:
            raise PathResolutionException(f"Duplicate paths of length <= 2 found: '{paths_to_target}'")

        # at this point there is more than a single path, and the length is at least 3
        return min(paths_to_target, key=self.path_score)

    def path_score(self, path: List[TargetId]) -> int:
        """return levenshtein distance
        between the intermediate tables and the outer tables
        assume that the path is at least of length 3
        """
        intermediate_tables_str = " ".join(path[1:-1])
        outer_tables_str = " ".join((path[0], path[-1]))
        distance = levenshtein_distance(intermediate_tables_str, outer_tables_str)
        return distance

    def _filter_all_paths(self, paths_to_target: dict[AnchorId, List[List[TargetId]]]) -> dict[AnchorId, List[List[TargetId]]]:
        filtered_paths = {}
        for anchor_id, paths in paths_to_target.items():
            filtered_for_anchor = list(filter(self._is_path_valid, paths))
            if filtered_for_anchor:
                filtered_paths[anchor_id] = filtered_for_anchor
        return filtered_paths

    def _is_path_starts_with_correct_target_field(self, path: List[TargetId]) -> bool:
        if self.target_field.targetField is None:
            return True  # no target field, so any path is valid
        first_table_in_path = self.target_tables_schemas[path[0]]
        if len(path) == 1:
            relations = TargetTableSchemaUtils.get_self_relations(first_table_in_path)
        else:
            next_table = self.target_tables_schemas[path[1]]
            # test in both directions as the relation can be first->nex of next->first
            relations = TargetTableSchemaUtils.get_relations_pointing_to_table(first_table_in_path, next_table)
            relations |= TargetTableSchemaUtils.get_relations_pointing_to_table(next_table, first_table_in_path)
        for relation in relations:
            for fk in relation.foreign_keys:
                if fk.from_attribute == self.target_field.targetField:
                    return True
        return False

    def _flatten_one_level(self, nested_list: List[List[Any]]) -> List[Any]:
        flattened_list = []
        for sublist in nested_list:
            flattened_list.extend(sublist)
        return flattened_list

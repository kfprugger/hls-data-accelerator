import sys
from collections import deque
from functools import lru_cache
from typing import Optional


class Node:
    def __init__(self, node_id: str):
        self.id = node_id
        self.neighbors = {}  # Dictionary with key = adjacent node_id, value = Node object


class NoNodeException(Exception):
    pass


class DuplicateNodeException(Exception):
    pass


class Graph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}

    def add_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            self.nodes[node_id] = Node(node_id)
        else:
            raise DuplicateNodeException(f"Graph node '{node_id}' already exists") 

    def add_edge(self, start_node_id: str, end_node_id: str) -> None:
        self._connect(start_node_id, end_node_id)

    def add_two_way_edge(self, left_node_id: str, right_node_id: str) -> None:
        self._connect(left_node_id, right_node_id)
        self._connect(right_node_id, left_node_id)

    def _connect(self, left_node_id, right_node_id):
        self.nodes[left_node_id].neighbors[right_node_id] = self.nodes[right_node_id]

    def get_node(self, node_id: str) -> Node:
        if node_id not in self.nodes:
            raise NoNodeException(f"Graph node '{node_id}' does not exist in the graph") 
        return self.nodes[node_id]

    @lru_cache(maxsize=1000)
    def find_all_shortest_paths(
        self,
        start_node_id: str,
        end_node_id: str,
        max_allowed_node_in_path: Optional[int] = None,
    ) -> list[list[str]]:
        if start_node_id == end_node_id:
            return [[start_node_id]]
        if max_allowed_node_in_path is None:
            max_allowed_node_in_path = len(self.nodes)
        paths = []
        queue = deque([[start_node_id]])
        min_length = sys.maxsize
        while queue:
            path = queue.popleft()
            last_node = path[-1]
            last_node_neighbors = set(self.get_node(last_node).neighbors.keys())
            unvisited_neighbors = last_node_neighbors - set(path)
            for next_node in unvisited_neighbors:
                new_path = path + [next_node]
                len_new_path = len(new_path)
                is_path_allowed = len_new_path <= max_allowed_node_in_path
                should_be_queued = len_new_path < max_allowed_node_in_path
                is_path_not_worse = len_new_path <= min_length
                if is_path_not_worse and is_path_allowed:
                    if next_node == end_node_id:
                        min_length = len_new_path
                        paths.append(new_path)
                    elif should_be_queued:
                        queue.append(new_path)

        return paths

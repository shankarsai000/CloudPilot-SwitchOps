"""
Knowledge Graph Component

In-memory directed graph relating infrastructure, applications, decisions, outcomes,
incidents, engineers, and policies. Supports node/edge CRUD, adjacency queries,
path finding, and subgraph extraction.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any, Optional

from models_learning import KnowledgeNode, KnowledgeEdge, KnowledgeNodeType, KnowledgeEdgeType

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """In-memory directed graph for organizational knowledge relationships."""

    def __init__(self) -> None:
        """Initialize an empty knowledge graph."""
        self._nodes: dict[str, KnowledgeNode] = {}
        self._edges: list[KnowledgeEdge] = []
        self._adjacency: dict[str, list[KnowledgeEdge]] = defaultdict(list)
        self._reverse_adjacency: dict[str, list[KnowledgeEdge]] = defaultdict(list)

    def add_node(self, node: KnowledgeNode) -> None:
        """Add a node to the graph (upserts on node_id).

        Args:
            node: KnowledgeNode to add
        """
        self._nodes[node.node_id] = node
        logger.debug("Added knowledge node %s (%s)", node.node_id, node.node_type.value)

    def get_node(self, node_id: str) -> Optional[KnowledgeNode]:
        """Retrieve a node by ID.

        Args:
            node_id: Node identifier

        Returns:
            KnowledgeNode or None
        """
        return self._nodes.get(node_id)

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its connected edges.

        Args:
            node_id: Node identifier

        Returns:
            True if removed, False if not found
        """
        if node_id not in self._nodes:
            return False
        del self._nodes[node_id]
        self._edges = [e for e in self._edges if e.source_id != node_id and e.target_id != node_id]
        self._adjacency.pop(node_id, None)
        self._reverse_adjacency.pop(node_id, None)
        # Rebuild adjacency for remaining edges referencing this node
        for nid in list(self._adjacency.keys()):
            self._adjacency[nid] = [e for e in self._adjacency[nid] if e.target_id != node_id]
        for nid in list(self._reverse_adjacency.keys()):
            self._reverse_adjacency[nid] = [e for e in self._reverse_adjacency[nid] if e.source_id != node_id]
        return True

    def add_edge(self, edge: KnowledgeEdge) -> None:
        """Add a directed edge between two nodes.

        Args:
            edge: KnowledgeEdge to add
        """
        self._edges.append(edge)
        self._adjacency[edge.source_id].append(edge)
        self._reverse_adjacency[edge.target_id].append(edge)
        logger.debug(
            "Added edge %s -[%s]-> %s",
            edge.source_id, edge.edge_type.value, edge.target_id,
        )

    def get_neighbors(self, node_id: str) -> list[KnowledgeNode]:
        """Get all nodes directly connected from a given node.

        Args:
            node_id: Source node ID

        Returns:
            List of neighboring KnowledgeNode instances
        """
        neighbor_ids = {e.target_id for e in self._adjacency.get(node_id, [])}
        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]

    def get_incoming(self, node_id: str) -> list[KnowledgeNode]:
        """Get all nodes that have edges pointing to a given node.

        Args:
            node_id: Target node ID

        Returns:
            List of upstream KnowledgeNode instances
        """
        source_ids = {e.source_id for e in self._reverse_adjacency.get(node_id, [])}
        return [self._nodes[sid] for sid in source_ids if sid in self._nodes]

    def get_edges_from(self, node_id: str) -> list[KnowledgeEdge]:
        """Get all edges originating from a node.

        Args:
            node_id: Source node ID

        Returns:
            List of KnowledgeEdge instances
        """
        return self._adjacency.get(node_id, [])

    def get_edges_by_type(self, edge_type: KnowledgeEdgeType) -> list[KnowledgeEdge]:
        """Filter all edges by relationship type.

        Args:
            edge_type: Edge type to filter

        Returns:
            Matching KnowledgeEdge instances
        """
        return [e for e in self._edges if e.edge_type == edge_type]

    def get_nodes_by_type(self, node_type: KnowledgeNodeType) -> list[KnowledgeNode]:
        """Filter nodes by type.

        Args:
            node_type: Node type to filter

        Returns:
            Matching KnowledgeNode instances
        """
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def find_path(self, source_id: str, target_id: str) -> list[str]:
        """Find a path between two nodes using BFS.

        Args:
            source_id: Start node ID
            target_id: End node ID

        Returns:
            List of node IDs forming the path, empty if none found
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return []

        visited: set[str] = set()
        queue: deque[list[str]] = deque([[source_id]])

        while queue:
            path = queue.popleft()
            current = path[-1]

            if current == target_id:
                return path

            if current in visited:
                continue
            visited.add(current)

            for edge in self._adjacency.get(current, []):
                if edge.target_id not in visited:
                    queue.append(path + [edge.target_id])

        return []

    def get_subgraph(self, center_id: str, depth: int = 2) -> dict[str, Any]:
        """Extract a subgraph around a center node up to a given depth.

        Args:
            center_id: Center node ID
            depth: Maximum traversal depth

        Returns:
            Dict with 'nodes' and 'edges' lists
        """
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(center_id, 0)])
        collected_nodes: list[KnowledgeNode] = []
        collected_edges: list[KnowledgeEdge] = []

        while queue:
            nid, d = queue.popleft()
            if nid in visited or d > depth:
                continue
            visited.add(nid)

            node = self._nodes.get(nid)
            if node:
                collected_nodes.append(node)

            for edge in self._adjacency.get(nid, []):
                collected_edges.append(edge)
                if edge.target_id not in visited:
                    queue.append((edge.target_id, d + 1))

        return {
            "nodes": [n.dict() for n in collected_nodes],
            "edges": [e.dict() for e in collected_edges],
        }

    def node_count(self) -> int:
        """Return total node count."""
        return len(self._nodes)

    def edge_count(self) -> int:
        """Return total edge count."""
        return len(self._edges)

    def export_to_dict(self) -> dict[str, Any]:
        """Export the full graph as a serializable dictionary.

        Returns:
            Dict with 'nodes' and 'edges' lists
        """
        return {
            "nodes": [n.dict() for n in self._nodes.values()],
            "edges": [e.dict() for e in self._edges],
        }

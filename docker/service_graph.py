"""
Service Graph — networkx-based service dependency graph.

Wraps a networkx DiGraph to provide typed service dependency
graph operations including traversal, blast radius analysis,
critical path detection, and subgraph extraction.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import networkx as nx

from models_application import ServiceDependency, ServiceNode
from models_dependency import (
    CycleDependency,
    DependencyGraph,
    DependencyGraphEdge,
    DependencyGraphNode,
    DependencyEdgeType,
    DependencyStrength,
)

logger = logging.getLogger(__name__)


class ServiceGraph:
    """networkx-backed directed service dependency graph.

    Provides typed graph operations for service dependency analysis
    including topological ordering, cycle detection, blast radius
    calculation, and critical path identification.
    """

    def __init__(self) -> None:
        """Initialize an empty service graph."""
        self._graph: nx.DiGraph = nx.DiGraph()
        logger.debug("ServiceGraph initialized")

    @property
    def node_count(self) -> int:
        """Return the number of nodes in the graph."""
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        """Return the number of edges in the graph."""
        return self._graph.number_of_edges()

    def add_service(self, service: ServiceNode) -> None:
        """Add a service node to the graph.

        Args:
            service: ServiceNode to add
        """
        self._graph.add_node(
            service.service_id,
            name=service.name,
            service_type=service.service_type.value if hasattr(service.service_type, "value") else str(service.service_type),
            protocol=service.protocol.value if hasattr(service.protocol, "value") else str(service.protocol),
            port=service.port,
            resource_ids=service.resource_ids,
            health_status=service.health_status,
            metadata=service.metadata,
        )
        logger.debug("Added service node: %s", service.service_id)

    def add_dependency(self, dependency: ServiceDependency) -> None:
        """Add a dependency edge to the graph.

        Args:
            dependency: ServiceDependency edge to add
        """
        self._graph.add_edge(
            dependency.source_service_id,
            dependency.target_service_id,
            dependency_type=dependency.dependency_type.value if hasattr(dependency.dependency_type, "value") else str(dependency.dependency_type),
            protocol=dependency.protocol.value if hasattr(dependency.protocol, "value") else str(dependency.protocol),
            port=dependency.port,
            latency_ms=dependency.latency_ms,
            requests_per_second=dependency.requests_per_second,
            error_rate=dependency.error_rate,
            is_critical=dependency.is_critical,
            metadata=dependency.metadata,
        )
        logger.debug(
            "Added dependency: %s → %s",
            dependency.source_service_id,
            dependency.target_service_id,
        )

    def remove_service(self, service_id: str) -> None:
        """Remove a service node and all its edges.

        Args:
            service_id: Service identifier to remove
        """
        if service_id in self._graph:
            self._graph.remove_node(service_id)
            logger.debug("Removed service node: %s", service_id)

    def has_service(self, service_id: str) -> bool:
        """Check if a service exists in the graph.

        Args:
            service_id: Service identifier

        Returns:
            True if service exists
        """
        return service_id in self._graph

    def get_service_data(self, service_id: str) -> Optional[dict[str, Any]]:
        """Get node data for a service.

        Args:
            service_id: Service identifier

        Returns:
            Node data dict or None
        """
        if service_id in self._graph:
            return dict(self._graph.nodes[service_id])
        return None

    def get_upstream(self, service_id: str) -> list[str]:
        """Get all services that this service depends on (outgoing edges).

        Args:
            service_id: Service identifier

        Returns:
            List of upstream service IDs
        """
        if service_id not in self._graph:
            return []
        return list(self._graph.successors(service_id))

    def get_downstream(self, service_id: str) -> list[str]:
        """Get all services that depend on this service (incoming edges).

        Args:
            service_id: Service identifier

        Returns:
            List of downstream service IDs
        """
        if service_id not in self._graph:
            return []
        return list(self._graph.predecessors(service_id))

    def get_blast_radius(self, service_id: str) -> list[str]:
        """Get all services transitively affected if this service fails.

        Computes the set of all ancestors (services that depend on this
        service, directly or transitively).

        Args:
            service_id: Service identifier

        Returns:
            List of affected service IDs (excluding the service itself)
        """
        if service_id not in self._graph:
            return []

        # All nodes that can reach this node (its ancestors)
        affected = nx.ancestors(self._graph, service_id)
        return list(affected)

    def get_dependency_chain(self, service_id: str) -> list[str]:
        """Get the full transitive dependency chain for a service.

        Computes all descendants (services this service depends on,
        directly or transitively).

        Args:
            service_id: Service identifier

        Returns:
            List of dependency service IDs
        """
        if service_id not in self._graph:
            return []

        descendants = nx.descendants(self._graph, service_id)
        return list(descendants)

    def get_critical_path(self) -> list[str]:
        """Find the longest dependency chain (critical path) in the graph.

        Uses the DAG longest path algorithm. Falls back to an
        approximation if cycles exist.

        Returns:
            List of node IDs forming the critical path
        """
        if self._graph.number_of_nodes() == 0:
            return []

        try:
            return nx.dag_longest_path(self._graph)
        except nx.NetworkXUnfeasible:
            # Graph has cycles — find longest simple path approximation
            longest: list[str] = []
            for node in self._graph.nodes():
                for target in self._graph.nodes():
                    if node == target:
                        continue
                    try:
                        for path in nx.all_simple_paths(
                            self._graph, node, target, cutoff=20
                        ):
                            if len(path) > len(longest):
                                longest = path
                    except nx.NodeNotFound:
                        continue
            return longest

    def detect_cycles(self) -> list[list[str]]:
        """Detect all circular dependencies in the graph.

        Returns:
            List of cycles, each cycle is a list of node IDs
        """
        try:
            cycles = list(nx.simple_cycles(self._graph))
            if cycles:
                logger.warning("Detected %d cycles in service graph", len(cycles))
            return cycles
        except Exception as e:
            logger.error("Cycle detection failed: %s", e)
            return []

    def get_topological_order(self) -> list[str]:
        """Get topological ordering of services (dependency order).

        Returns:
            List of service IDs in dependency order, or empty list if cycles exist
        """
        try:
            return list(nx.topological_sort(self._graph))
        except nx.NetworkXUnfeasible:
            logger.warning("Cannot compute topological order: graph has cycles")
            return []

    def get_roots(self) -> list[str]:
        """Get root services (no incoming dependencies).

        Returns:
            List of root service IDs
        """
        return [
            node
            for node in self._graph.nodes()
            if self._graph.in_degree(node) == 0
        ]

    def get_leaves(self) -> list[str]:
        """Get leaf services (no outgoing dependencies).

        Returns:
            List of leaf service IDs
        """
        return [
            node
            for node in self._graph.nodes()
            if self._graph.out_degree(node) == 0
        ]

    def get_subgraph(self, node_ids: list[str]) -> "ServiceGraph":
        """Extract a subgraph containing only specified nodes.

        Args:
            node_ids: List of node IDs to include

        Returns:
            New ServiceGraph containing the subgraph
        """
        subgraph = ServiceGraph()
        sub_nx = self._graph.subgraph(node_ids).copy()
        subgraph._graph = sub_nx
        return subgraph

    def get_max_depth(self) -> int:
        """Calculate maximum depth (longest path length) of the graph.

        Returns:
            Maximum depth as integer
        """
        path = self.get_critical_path()
        return max(len(path) - 1, 0)

    def to_dependency_graph(
        self, application_id: Optional[str] = None
    ) -> DependencyGraph:
        """Export graph as a DependencyGraph model.

        Args:
            application_id: Optional application ID

        Returns:
            DependencyGraph model
        """
        nodes: list[DependencyGraphNode] = []
        for node_id in self._graph.nodes():
            data = self._graph.nodes[node_id]
            in_deg = self._graph.in_degree(node_id)
            out_deg = self._graph.out_degree(node_id)
            nodes.append(
                DependencyGraphNode(
                    node_id=node_id,
                    name=data.get("name", node_id),
                    node_type=data.get("service_type", "service"),
                    application_id=application_id,
                    resource_ids=data.get("resource_ids", []),
                    in_degree=in_deg,
                    out_degree=out_deg,
                    is_leaf=out_deg == 0,
                    is_root=in_deg == 0,
                    metadata=data.get("metadata", {}),
                )
            )

        edges: list[DependencyGraphEdge] = []
        for source, target, data in self._graph.edges(data=True):
            edges.append(
                DependencyGraphEdge(
                    source_id=source,
                    target_id=target,
                    edge_type=DependencyEdgeType.RUNTIME,
                    strength=(
                        DependencyStrength.STRONG
                        if data.get("is_critical")
                        else DependencyStrength.UNKNOWN
                    ),
                    protocol=data.get("protocol", "unknown"),
                    port=data.get("port"),
                    latency_ms=data.get("latency_ms"),
                    metadata=data.get("metadata", {}),
                )
            )

        raw_cycles = self.detect_cycles()
        cycles: list[CycleDependency] = [
            CycleDependency(
                cycle_id=f"cycle-{i:03d}",
                nodes=cycle,
                severity="warning",
                description=f"Circular dependency: {' → '.join(cycle)}",
            )
            for i, cycle in enumerate(raw_cycles)
        ]

        critical_path = self.get_critical_path()

        return DependencyGraph(
            application_id=application_id,
            nodes=nodes,
            edges=edges,
            cycles=cycles,
            has_cycles=len(cycles) > 0,
            total_nodes=len(nodes),
            total_edges=len(edges),
            max_depth=self.get_max_depth(),
            critical_path=critical_path,
        )

    def export_to_dict(self) -> dict[str, Any]:
        """Serialize graph to a JSON-compatible dictionary.

        Returns:
            Dict with 'nodes' and 'edges' keys
        """
        nodes = []
        for node_id in self._graph.nodes():
            data = dict(self._graph.nodes[node_id])
            data["id"] = node_id
            nodes.append(data)

        edges = []
        for source, target, data in self._graph.edges(data=True):
            edge = dict(data)
            edge["source"] = source
            edge["target"] = target
            edges.append(edge)

        return {"nodes": nodes, "edges": edges}

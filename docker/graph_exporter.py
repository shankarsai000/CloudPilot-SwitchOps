"""
Graph Exporter — Multi-format graph serialization.

Exports application, service, and dependency graphs in multiple
formats for API consumption and visualization: dict, adjacency list,
and Mermaid diagram format.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models_application import Application, ApplicationGraph
from models_dependency import DependencyGraph
from models_topology import ApplicationTopology
from service_graph import ServiceGraph

logger = logging.getLogger(__name__)


class GraphExporter:
    """Exports graphs in multiple formats for API and visualization.

    Supported formats:
    - dict: JSON-serializable dictionary
    - adjacency_list: Simplified adjacency list
    - mermaid: Mermaid diagram syntax
    """

    def __init__(self) -> None:
        """Initialize graph exporter."""
        logger.info("GraphExporter initialized")

    def application_graph_to_dict(
        self, graph: ApplicationGraph
    ) -> dict[str, Any]:
        """Export ApplicationGraph to a JSON-serializable dict.

        Args:
            graph: ApplicationGraph model

        Returns:
            Serializable dictionary
        """
        return {
            "total_applications": graph.total_applications,
            "total_services": graph.total_services,
            "total_dependencies": graph.total_dependencies,
            "applications_by_type": graph.applications_by_type,
            "applications_by_environment": graph.applications_by_environment,
            "applications_by_tier": graph.applications_by_tier,
            "unassigned_resources": graph.unassigned_resources,
            "discovery_timestamp": graph.discovery_timestamp.isoformat(),
            "failures": graph.failures,
            "applications": [
                self._application_to_dict(app) for app in graph.applications
            ],
        }

    def service_graph_to_dict(
        self, service_graph: ServiceGraph
    ) -> dict[str, Any]:
        """Export ServiceGraph to a JSON-serializable dict.

        Args:
            service_graph: ServiceGraph instance

        Returns:
            Serializable dictionary with nodes and edges
        """
        return service_graph.export_to_dict()

    def dependency_graph_to_dict(
        self, dep_graph: DependencyGraph
    ) -> dict[str, Any]:
        """Export DependencyGraph model to dict.

        Args:
            dep_graph: DependencyGraph model

        Returns:
            Serializable dictionary
        """
        return {
            "application_id": dep_graph.application_id,
            "total_nodes": dep_graph.total_nodes,
            "total_edges": dep_graph.total_edges,
            "has_cycles": dep_graph.has_cycles,
            "max_depth": dep_graph.max_depth,
            "critical_path": dep_graph.critical_path,
            "nodes": [
                {
                    "id": n.node_id,
                    "name": n.name,
                    "type": n.node_type,
                    "application_id": n.application_id,
                    "in_degree": n.in_degree,
                    "out_degree": n.out_degree,
                    "is_leaf": n.is_leaf,
                    "is_root": n.is_root,
                }
                for n in dep_graph.nodes
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.edge_type.value,
                    "strength": e.strength.value,
                    "protocol": e.protocol,
                    "port": e.port,
                }
                for e in dep_graph.edges
            ],
            "cycles": [
                {
                    "cycle_id": c.cycle_id,
                    "nodes": c.nodes,
                    "severity": c.severity,
                    "description": c.description,
                }
                for c in dep_graph.cycles
            ],
        }

    def topology_to_dict(
        self, topology: ApplicationTopology
    ) -> dict[str, Any]:
        """Export ApplicationTopology to dict.

        Args:
            topology: ApplicationTopology model

        Returns:
            Serializable dictionary
        """
        return {
            "application_id": topology.application_id,
            "depth": topology.depth,
            "entry_points": topology.entry_points,
            "data_stores": topology.data_stores,
            "external_dependencies": topology.external_dependencies,
            "layers": topology.layers,
            "nodes": [
                {
                    "id": n.node_id,
                    "name": n.name,
                    "layer": n.layer.value,
                    "service_type": n.service_type,
                    "health": n.health.value,
                    "replicas": n.replicas,
                    "port": n.port,
                }
                for n in topology.nodes
            ],
            "edges": [
                {
                    "source": e.source_node_id,
                    "target": e.target_node_id,
                    "protocol": e.protocol,
                    "port": e.port,
                    "rps": e.requests_per_second,
                    "latency_ms": e.latency_ms,
                }
                for e in topology.edges
            ],
        }

    def to_adjacency_list(
        self, service_graph: ServiceGraph
    ) -> dict[str, list[str]]:
        """Export service graph as simplified adjacency list.

        Args:
            service_graph: ServiceGraph instance

        Returns:
            Dict mapping node ID → list of connected node IDs
        """
        adjacency: dict[str, list[str]] = {}
        for node_id in service_graph._graph.nodes():
            upstream = service_graph.get_upstream(node_id)
            adjacency[node_id] = upstream
        return adjacency

    def to_mermaid(
        self,
        service_graph: ServiceGraph,
        title: Optional[str] = None,
    ) -> str:
        """Export service graph as Mermaid diagram syntax.

        Args:
            service_graph: ServiceGraph instance
            title: Optional diagram title

        Returns:
            Mermaid diagram string
        """
        lines: list[str] = []
        lines.append("graph TD")

        if title:
            lines.append(f"    %% {title}")

        # Add nodes with labels
        for node_id in service_graph._graph.nodes():
            data = service_graph.get_service_data(node_id)
            if data:
                name = data.get("name", node_id)
                service_type = data.get("service_type", "unknown")
                # Sanitize for mermaid
                safe_id = node_id.replace("-", "_").replace(".", "_")
                safe_name = name.replace('"', "'")
                lines.append(f'    {safe_id}["{safe_name}<br/>{service_type}"]')

        # Add edges
        for source, target, data in service_graph._graph.edges(data=True):
            safe_source = source.replace("-", "_").replace(".", "_")
            safe_target = target.replace("-", "_").replace(".", "_")
            protocol = data.get("protocol", "")
            if protocol and protocol != "unknown":
                lines.append(f"    {safe_source} -->|{protocol}| {safe_target}")
            else:
                lines.append(f"    {safe_source} --> {safe_target}")

        return "\n".join(lines)

    def topology_to_mermaid(
        self,
        topology: ApplicationTopology,
        title: Optional[str] = None,
    ) -> str:
        """Export topology as a layered Mermaid diagram.

        Args:
            topology: ApplicationTopology model
            title: Optional diagram title

        Returns:
            Mermaid diagram string
        """
        lines: list[str] = []
        lines.append("graph TD")

        if title:
            lines.append(f"    %% {title}")

        # Group by layers using subgraphs
        for layer_name, node_ids in topology.layers.items():
            safe_layer = layer_name.replace("-", "_")
            lines.append(f"    subgraph {safe_layer}[{layer_name.upper()}]")
            for node_id in node_ids:
                # Find node details
                node = next(
                    (n for n in topology.nodes if n.node_id == node_id), None
                )
                if node:
                    safe_id = node_id.replace("-", "_").replace(".", "_")
                    safe_name = node.name.replace('"', "'")
                    lines.append(f'        {safe_id}["{safe_name}"]')
            lines.append("    end")

        # Add edges
        for edge in topology.edges:
            safe_source = edge.source_node_id.replace("-", "_").replace(".", "_")
            safe_target = edge.target_node_id.replace("-", "_").replace(".", "_")
            if edge.protocol and edge.protocol != "unknown":
                lines.append(f"    {safe_source} -->|{edge.protocol}| {safe_target}")
            else:
                lines.append(f"    {safe_source} --> {safe_target}")

        return "\n".join(lines)

    @staticmethod
    def _application_to_dict(app: Application) -> dict[str, Any]:
        """Serialize single Application to dict.

        Args:
            app: Application model

        Returns:
            Serializable dictionary
        """
        return {
            "application_id": app.application_id,
            "name": app.name,
            "description": app.description,
            "application_type": app.application_type.value,
            "environment": app.environment.value,
            "tier": app.tier.value,
            "resource_ids": app.resource_ids,
            "service_count": len(app.services),
            "dependency_count": len(app.dependencies),
            "total_monthly_cost": app.total_monthly_cost,
            "discovery_source": app.discovery_source,
            "tags": app.tags,
            "discovered_at": app.discovered_at.isoformat(),
            "ownership": (
                {
                    "owner": app.ownership.owner,
                    "team": app.ownership.team,
                    "slack_channel": app.ownership.slack_channel,
                    "repository": app.ownership.repository,
                    "confidence": app.ownership.confidence,
                }
                if app.ownership
                else None
            ),
            "criticality": (
                {
                    "score": app.criticality.criticality_score,
                    "risk_level": app.criticality.risk_level.value,
                    "revenue_impact": app.criticality.revenue_impact,
                    "compliance_impact": app.criticality.compliance_impact,
                    "availability_target": app.criticality.availability_target,
                    "customer_facing": app.criticality.customer_facing,
                }
                if app.criticality
                else None
            ),
        }

"""
Dependency Analyzer Component

Analyzes cascading operational risks and downstream impact paths using M3 service dependency graphs.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from models_application import Application, ServiceNode
from service_graph import ServiceGraph

logger = logging.getLogger(__name__)


class DependencyAnalyzer:
    """Uses the M3 service dependency graph to predict downstream cascading failures."""

    def __init__(self) -> None:
        """Initialize dependency analyzer."""
        pass

    def analyze_downstream_impact(
        self,
        target_resource_id: str,
        applications: list[Application],
        service_graph: ServiceGraph,
    ) -> dict[str, Any]:
        """Predict downstream cascading failure paths if a resource is disrupted.

        Args:
            target_resource_id: ID of resource being affected
            applications: List of discovered applications from M3
            service_graph: Complete service graph from M3

        Returns:
            Dict containing downstream impact details, affected application/service IDs, and path traces
        """
        affected_services: list[str] = []
        impact_paths: list[list[str]] = []
        max_depth = 0

        # Step 1: Find the service node(s) holding the target resource
        root_service_id: Optional[str] = None
        root_service_name: Optional[str] = None

        for app in applications:
            for service in app.services:
                if target_resource_id in service.resource_ids:
                    root_service_id = service.service_id
                    root_service_name = service.name
                    break
            if root_service_id:
                break

        # Step 2: Traverse downstream nodes (using get_blast_radius / predictors)
        if root_service_id and service_graph.has_service(root_service_id):
            # Blast radius of service failures consists of nodes that depend on it transitively (downstream)
            # In networkx representation, dependencies are modeled source -> target (e.g. frontend -> backend)
            # So the downstream nodes affected by losing target_service are its predecessors (incoming edges)
            affected_services = service_graph.get_blast_radius(root_service_id)
            affected_services.append(root_service_id)

            # Build impact paths for explanations
            # For each affected service, find a path to the root service
            for service_id in affected_services:
                if service_id != root_service_id:
                    try:
                        # Find path in reverse (since target depends on source)
                        # We want path from target to source
                        import networkx as nx
                        paths = list(nx.all_simple_paths(service_graph._graph, service_id, root_service_id))
                        if paths:
                            # Reverse it to represent: root_service -> ... -> affected_service
                            path = paths[0]
                            impact_paths.append(path)
                            if len(path) > max_depth:
                                max_depth = len(path)
                    except Exception:
                        pass

        # Step 3: Determine affected application IDs
        affected_apps: set[str] = set()
        for service_id in affected_services:
            for app in applications:
                if any(s.service_id == service_id for s in app.services):
                    affected_apps.add(app.application_id)
                    break

        return {
            "root_service_id": root_service_id,
            "root_service_name": root_service_name,
            "affected_service_ids": affected_services,
            "affected_application_ids": list(affected_apps),
            "impact_paths": impact_paths,
            "complexity_depth": max_depth,
            "dependency_risk_score": min(len(affected_services) * 15.0, 100.0)
        }

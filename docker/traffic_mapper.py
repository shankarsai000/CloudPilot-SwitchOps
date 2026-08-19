"""
Traffic Mapper — Traffic flow intelligence.

Models request flows through the application topology,
identifying ingress, egress, and internal service-to-service
traffic patterns with RPS, latency, and error rate metrics.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from models_application import (
    Application,
    DependencyProtocol,
    TrafficFlow,
)
from service_graph import ServiceGraph

logger = logging.getLogger(__name__)


class TrafficMapper:
    """Maps traffic flows through application service topologies.

    Analyzes the service graph to produce a complete traffic flow
    model including ingress (external → app), egress (app → external),
    and internal (service → service) flows.
    """

    def __init__(self) -> None:
        """Initialize traffic mapper."""
        logger.info("TrafficMapper initialized")

    def map_traffic_flows(
        self,
        application: Application,
        service_graph: ServiceGraph,
    ) -> list[TrafficFlow]:
        """Map all traffic flows for an application.

        Args:
            application: Application model
            service_graph: Application's service dependency graph

        Returns:
            List of TrafficFlow objects
        """
        flows: list[TrafficFlow] = []

        # Map internal service-to-service flows
        internal_flows = self._map_internal_flows(service_graph)
        flows.extend(internal_flows)

        # Map ingress flows (external → entry points)
        ingress_flows = self._map_ingress_flows(service_graph)
        flows.extend(ingress_flows)

        # Map egress flows (services → external)
        egress_flows = self._map_egress_flows(service_graph)
        flows.extend(egress_flows)

        # Attach to application
        application.traffic_flows = flows

        logger.info(
            "Mapped %d traffic flows for %s (ingress=%d, internal=%d, egress=%d)",
            len(flows),
            application.name,
            len(ingress_flows),
            len(internal_flows),
            len(egress_flows),
        )
        return flows

    def get_ingress_flows(
        self, service_graph: ServiceGraph
    ) -> list[TrafficFlow]:
        """Get external → application ingress flows.

        Args:
            service_graph: Service graph

        Returns:
            List of ingress TrafficFlow objects
        """
        return self._map_ingress_flows(service_graph)

    def get_egress_flows(
        self, service_graph: ServiceGraph
    ) -> list[TrafficFlow]:
        """Get application → external egress flows.

        Args:
            service_graph: Service graph

        Returns:
            List of egress TrafficFlow objects
        """
        return self._map_egress_flows(service_graph)

    def get_internal_flows(
        self, service_graph: ServiceGraph
    ) -> list[TrafficFlow]:
        """Get internal service-to-service flows.

        Args:
            service_graph: Service graph

        Returns:
            List of internal TrafficFlow objects
        """
        return self._map_internal_flows(service_graph)

    def _map_internal_flows(
        self, service_graph: ServiceGraph
    ) -> list[TrafficFlow]:
        """Map internal service-to-service traffic flows from graph edges.

        Args:
            service_graph: Service graph

        Returns:
            List of internal TrafficFlow objects
        """
        flows: list[TrafficFlow] = []

        for source, target, data in service_graph._graph.edges(data=True):
            source_data = service_graph.get_service_data(source)
            target_data = service_graph.get_service_data(target)

            source_name = source_data.get("name", source) if source_data else source
            target_name = target_data.get("name", target) if target_data else target

            protocol_str = data.get("protocol", "unknown")
            try:
                protocol = DependencyProtocol(protocol_str)
            except ValueError:
                protocol = DependencyProtocol.UNKNOWN

            flow = TrafficFlow(
                flow_id=f"flow-{uuid.uuid4().hex[:10]}",
                source=source_name,
                destination=target_name,
                protocol=protocol,
                port=data.get("port"),
                requests_per_second=data.get("requests_per_second", 0.0) or 0.0,
                latency_p50_ms=data.get("latency_ms"),
                error_rate=data.get("error_rate", 0.0) or 0.0,
                is_external=False,
                direction="internal",
                metadata={
                    "source_id": source,
                    "target_id": target,
                    "dependency_type": data.get("dependency_type", "unknown"),
                },
            )
            flows.append(flow)

        return flows

    def _map_ingress_flows(
        self, service_graph: ServiceGraph
    ) -> list[TrafficFlow]:
        """Map ingress traffic flows (external → root services).

        Root services (no incoming edges within the graph) are assumed
        to receive external traffic.

        Args:
            service_graph: Service graph

        Returns:
            List of ingress TrafficFlow objects
        """
        flows: list[TrafficFlow] = []
        roots = service_graph.get_roots()

        for root_id in roots:
            root_data = service_graph.get_service_data(root_id)
            if not root_data:
                continue

            root_name = root_data.get("name", root_id)
            protocol_str = root_data.get("protocol", "https")
            try:
                protocol = DependencyProtocol(protocol_str)
            except ValueError:
                protocol = DependencyProtocol.HTTPS

            flow = TrafficFlow(
                flow_id=f"flow-ingress-{uuid.uuid4().hex[:8]}",
                source="internet",
                destination=root_name,
                protocol=protocol,
                port=root_data.get("port", 443),
                requests_per_second=0.0,
                is_external=True,
                direction="ingress",
                metadata={"target_service_id": root_id},
            )
            flows.append(flow)

        return flows

    def _map_egress_flows(
        self, service_graph: ServiceGraph
    ) -> list[TrafficFlow]:
        """Map egress traffic flows (leaf services → external).

        Leaf services with 'external' type are modeled as egress endpoints.

        Args:
            service_graph: Service graph

        Returns:
            List of egress TrafficFlow objects
        """
        flows: list[TrafficFlow] = []
        leaves = service_graph.get_leaves()

        for leaf_id in leaves:
            leaf_data = service_graph.get_service_data(leaf_id)
            if not leaf_data:
                continue

            # Only model external services as egress
            service_type = leaf_data.get("service_type", "unknown")
            if service_type == "external":
                leaf_name = leaf_data.get("name", leaf_id)
                flow = TrafficFlow(
                    flow_id=f"flow-egress-{uuid.uuid4().hex[:8]}",
                    source=leaf_name,
                    destination="external-api",
                    protocol=DependencyProtocol.HTTPS,
                    port=443,
                    requests_per_second=0.0,
                    is_external=True,
                    direction="egress",
                    metadata={"source_service_id": leaf_id},
                )
                flows.append(flow)

        return flows

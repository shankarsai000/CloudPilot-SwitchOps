"""
Topology Builder — Constructs application deployment topology.

Classifies services into topology layers (frontend, backend, data,
cache, gateway, external) and builds a layered topology model
from the service dependency graph.
"""

from __future__ import annotations

import logging
from typing import Optional

from models_application import Application, ServiceNode, ServiceType
from models_topology import (
    ApplicationTopology,
    DeploymentTopology,
    HealthStatus,
    TopologyEdge,
    TopologyLayer,
    TopologyNode,
)
from models_resource import CloudResource
from service_graph import ServiceGraph

logger = logging.getLogger(__name__)


# Mapping from ServiceType to TopologyLayer
SERVICE_TYPE_TO_LAYER: dict[ServiceType, TopologyLayer] = {
    ServiceType.FRONTEND: TopologyLayer.FRONTEND,
    ServiceType.BACKEND: TopologyLayer.BACKEND,
    ServiceType.API_GATEWAY: TopologyLayer.API_GATEWAY,
    ServiceType.DATABASE: TopologyLayer.DATA,
    ServiceType.CACHE: TopologyLayer.CACHE,
    ServiceType.QUEUE: TopologyLayer.QUEUE,
    ServiceType.STORAGE: TopologyLayer.STORAGE,
    ServiceType.LOAD_BALANCER: TopologyLayer.INGRESS,
    ServiceType.CDN: TopologyLayer.INGRESS,
    ServiceType.MONITORING: TopologyLayer.MONITORING,
    ServiceType.LOGGING: TopologyLayer.MONITORING,
    ServiceType.AUTH: TopologyLayer.BACKEND,
    ServiceType.EXTERNAL: TopologyLayer.EXTERNAL,
    ServiceType.UNKNOWN: TopologyLayer.UNKNOWN,
}


class TopologyBuilder:
    """Builds layered application topologies from service graphs.

    Classifies service nodes into architecture layers and constructs
    a deployment-aware topology with entry points, data stores,
    and external dependencies.
    """

    def __init__(self) -> None:
        """Initialize topology builder."""
        logger.info("TopologyBuilder initialized")

    def build_topology(
        self,
        application: Application,
        service_graph: ServiceGraph,
        resources: Optional[list[CloudResource]] = None,
    ) -> ApplicationTopology:
        """Build the application topology from service graph.

        Args:
            application: Application model
            service_graph: Service dependency graph
            resources: Optional M1 resources for enrichment

        Returns:
            ApplicationTopology model
        """
        resource_map: dict[str, CloudResource] = {}
        if resources:
            resource_map = {r.id: r for r in resources}

        nodes: list[TopologyNode] = []
        edges: list[TopologyEdge] = []
        layers: dict[str, list[str]] = {}
        entry_points: list[str] = []
        data_stores: list[str] = []
        external_deps: list[str] = []

        # Build nodes from service graph
        for node_id in service_graph._graph.nodes():
            data = service_graph.get_service_data(node_id)
            if not data:
                continue

            service_type_str = data.get("service_type", "unknown")
            try:
                service_type = ServiceType(service_type_str)
            except ValueError:
                service_type = ServiceType.UNKNOWN

            layer = SERVICE_TYPE_TO_LAYER.get(service_type, TopologyLayer.UNKNOWN)

            # Compute replicas from resource count
            resource_ids = data.get("resource_ids", [])
            replicas = max(len(resource_ids), 1)

            # Infer health from resource states
            health = self._infer_health(resource_ids, resource_map)

            topo_node = TopologyNode(
                node_id=node_id,
                name=data.get("name", node_id),
                layer=layer,
                service_type=service_type_str,
                resource_ids=resource_ids,
                health=health,
                replicas=replicas,
                port=data.get("port"),
                protocol=data.get("protocol", "unknown"),
                metadata=data.get("metadata", {}),
            )
            nodes.append(topo_node)

            # Classify into layers
            layer_key = layer.value
            if layer_key not in layers:
                layers[layer_key] = []
            layers[layer_key].append(node_id)

            # Classify entry points, data stores, external deps
            if layer in (TopologyLayer.INGRESS, TopologyLayer.API_GATEWAY):
                entry_points.append(node_id)
            elif layer in (TopologyLayer.DATA, TopologyLayer.STORAGE):
                data_stores.append(node_id)
            elif layer == TopologyLayer.EXTERNAL:
                external_deps.append(node_id)

        # Build edges from service graph
        for source, target, data in service_graph._graph.edges(data=True):
            edge = TopologyEdge(
                source_node_id=source,
                target_node_id=target,
                protocol=data.get("protocol", "unknown"),
                port=data.get("port"),
                requests_per_second=data.get("requests_per_second"),
                latency_ms=data.get("latency_ms"),
                error_rate=data.get("error_rate"),
                is_encrypted=data.get("protocol") in ("https", "grpc"),
                metadata=data.get("metadata", {}),
            )
            edges.append(edge)

        # Use graph roots as fallback entry points
        if not entry_points:
            roots = service_graph.get_roots()
            entry_points = roots[:5]  # Limit to top 5

        depth = service_graph.get_max_depth()

        topology = ApplicationTopology(
            application_id=application.application_id,
            nodes=nodes,
            edges=edges,
            layers=layers,
            entry_points=entry_points,
            data_stores=data_stores,
            external_dependencies=external_deps,
            depth=depth,
        )

        logger.info(
            "Built topology for %s: %d nodes, %d edges, depth=%d",
            application.name,
            len(nodes),
            len(edges),
            depth,
        )
        return topology

    def get_deployment_topology(
        self,
        application: Application,
        topology: ApplicationTopology,
        resources: Optional[list[CloudResource]] = None,
    ) -> DeploymentTopology:
        """Build deployment-aware topology with infrastructure bindings.

        Args:
            application: Application model
            topology: Base application topology
            resources: M1 resources for infrastructure metadata

        Returns:
            DeploymentTopology model
        """
        resource_map: dict[str, CloudResource] = {}
        if resources:
            resource_map = {r.id: r for r in resources}

        availability_zones: set[str] = set()
        regions: set[str] = set()
        providers: set[str] = set()
        total_instances: int = 0

        for resource_id in application.resource_ids:
            resource = resource_map.get(resource_id)
            if not resource:
                continue

            if resource.region:
                regions.add(resource.region)
            providers.add(resource.provider)

            az = resource.metadata.get("availability_zone")
            if az:
                availability_zones.add(az)

            total_instances += 1

        # Detect auto-scaling
        auto_scaling = any(
            resource_map.get(rid) and resource_map[rid].metadata.get("auto_scaling_group")
            for rid in application.resource_ids
            if rid in resource_map
        )

        return DeploymentTopology(
            application_id=application.application_id,
            topology=topology,
            availability_zones=sorted(availability_zones),
            regions=sorted(regions),
            providers=sorted(providers),
            total_instances=total_instances,
            auto_scaling_enabled=auto_scaling,
            multi_az=len(availability_zones) > 1,
            multi_region=len(regions) > 1,
        )

    @staticmethod
    def _infer_health(
        resource_ids: list[str],
        resource_map: dict[str, CloudResource],
    ) -> HealthStatus:
        """Infer node health from bound resource states.

        Args:
            resource_ids: Resource IDs bound to this node
            resource_map: Resource ID → CloudResource mapping

        Returns:
            Inferred HealthStatus
        """
        if not resource_ids:
            return HealthStatus.UNKNOWN

        states: list[str] = []
        for rid in resource_ids:
            resource = resource_map.get(rid)
            if resource:
                states.append(resource.state.value)

        if not states:
            return HealthStatus.UNKNOWN

        if all(s == "running" or s == "available" for s in states):
            return HealthStatus.HEALTHY
        if any(s in ("terminated", "deleted", "unavailable") for s in states):
            return HealthStatus.UNHEALTHY
        if any(s in ("stopped", "pending") for s in states):
            return HealthStatus.DEGRADED

        return HealthStatus.UNKNOWN

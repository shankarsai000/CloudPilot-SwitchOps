"""
Dependency Mapper — Service dependency graph builder.

Infers service-to-service dependencies from M1 resource metadata
including security groups, load balancer targets, DNS records,
K8s services, and environment variables. Builds a complete
dependency graph using the ServiceGraph.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from models_application import (
    Application,
    DependencyCoupling,
    DependencyProtocol,
    ServiceDependency,
    ServiceNode,
    ServiceType,
)
from models_dependency import DependencyGraph
from models_resource import CloudResource, DependencyEdge, ResourceType
from service_graph import ServiceGraph

logger = logging.getLogger(__name__)


class DependencyMapper:
    """Builds service dependency graphs from M1 resource data.

    Infers inter-service dependencies by analyzing:
    - Security group rules (port-based connectivity)
    - Load balancer target groups
    - K8s service selectors and ingress rules
    - Environment variables referencing other services
    - DNS records and hostnames
    - M1 DependencyEdge relationships
    """

    def __init__(self) -> None:
        """Initialize the dependency mapper."""
        self._graph: ServiceGraph = ServiceGraph()
        logger.info("DependencyMapper initialized")

    def map_dependencies(
        self,
        applications: list[Application],
        resources: list[CloudResource],
        m1_dependencies: Optional[list[DependencyEdge]] = None,
    ) -> ServiceGraph:
        """Build the complete service dependency graph.

        Args:
            applications: Discovered applications from ApplicationDiscoveryEngine
            resources: M1 cloud resources
            m1_dependencies: M1 DependencyEdge relationships

        Returns:
            Populated ServiceGraph
        """
        self._graph = ServiceGraph()
        resource_map = {r.id: r for r in resources}

        # Phase 1: Create service nodes from applications
        for app in applications:
            self._create_service_nodes(app, resource_map)

        # Phase 2: Infer dependencies from M1 edges
        if m1_dependencies:
            self._infer_from_m1_edges(m1_dependencies, applications)

        # Phase 3: Infer dependencies from resource metadata
        self._infer_from_resource_metadata(applications, resource_map)

        # Phase 4: Infer from load balancer targets
        self._infer_from_load_balancers(applications, resource_map)

        # Phase 5: Infer from K8s service/ingress
        self._infer_from_kubernetes(applications, resource_map)

        logger.info(
            "Dependency mapping complete: %d nodes, %d edges",
            self._graph.node_count,
            self._graph.edge_count,
        )
        return self._graph

    def get_dependency_graph(
        self, application_id: Optional[str] = None
    ) -> DependencyGraph:
        """Export the current graph as a DependencyGraph model.

        Args:
            application_id: Optional filter for single application

        Returns:
            DependencyGraph model
        """
        return self._graph.to_dependency_graph(application_id)

    def detect_cycles(self) -> list[list[str]]:
        """Detect circular dependencies in the graph.

        Returns:
            List of cycles (each cycle is a list of node IDs)
        """
        return self._graph.detect_cycles()

    def get_dependency_chain(self, service_id: str) -> list[str]:
        """Get the full transitive dependency chain for a service.

        Args:
            service_id: Service identifier

        Returns:
            List of all transitive dependency IDs
        """
        return self._graph.get_dependency_chain(service_id)

    def _create_service_nodes(
        self,
        app: Application,
        resource_map: dict[str, CloudResource],
    ) -> None:
        """Create service nodes for an application's resources.

        Groups resources within an application into logical service
        nodes based on resource type.

        Args:
            app: Application to process
            resource_map: Resource ID → CloudResource mapping
        """
        # Group application resources by inferred service role
        service_groups: dict[str, list[str]] = {}

        for resource_id in app.resource_ids:
            resource = resource_map.get(resource_id)
            if not resource:
                continue

            service_type = self._classify_service_type(resource)
            group_key = f"{app.application_id}-{service_type.value}"

            if group_key not in service_groups:
                service_groups[group_key] = []
            service_groups[group_key].append(resource_id)

        # Create a ServiceNode per group
        for group_key, resource_ids in service_groups.items():
            service_type_str = group_key.split("-")[-1]
            service_id = f"svc-{group_key}-{uuid.uuid4().hex[:6]}"

            # Pick the best name from resources
            sample_resource = resource_map.get(resource_ids[0])
            name = sample_resource.name if sample_resource else group_key

            try:
                svc_type = ServiceType(service_type_str)
            except ValueError:
                svc_type = ServiceType.UNKNOWN

            protocol = self._infer_protocol(svc_type)

            node = ServiceNode(
                service_id=service_id,
                name=name,
                service_type=svc_type,
                protocol=protocol,
                resource_ids=resource_ids,
                metadata={"application_id": app.application_id},
            )
            self._graph.add_service(node)

    def _infer_from_m1_edges(
        self,
        m1_dependencies: list[DependencyEdge],
        applications: list[Application],
    ) -> None:
        """Infer service dependencies from M1 DependencyEdge relationships.

        Maps M1 resource-level dependencies to service-level dependencies
        by finding which services own which resources.

        Args:
            m1_dependencies: M1 DependencyEdge list
            applications: Discovered applications
        """
        # Build resource_id → service_id mapping
        resource_to_service: dict[str, str] = {}
        for node_id in self._graph._graph.nodes():
            data = self._graph.get_service_data(node_id)
            if data:
                for rid in data.get("resource_ids", []):
                    resource_to_service[rid] = node_id

        for edge in m1_dependencies:
            source_svc = resource_to_service.get(edge.source_id)
            target_svc = resource_to_service.get(edge.target_id)

            if source_svc and target_svc and source_svc != target_svc:
                dep = ServiceDependency(
                    source_service_id=source_svc,
                    target_service_id=target_svc,
                    dependency_type=DependencyCoupling.SYNCHRONOUS,
                    protocol=DependencyProtocol.UNKNOWN,
                    metadata={"source": "m1_edge", "relationship": edge.relationship_type.value},
                )
                self._graph.add_dependency(dep)

    def _infer_from_resource_metadata(
        self,
        applications: list[Application],
        resource_map: dict[str, CloudResource],
    ) -> None:
        """Infer dependencies from resource metadata (env vars, security groups).

        Args:
            applications: Discovered applications
            resource_map: Resource ID → CloudResource mapping
        """
        resource_to_service: dict[str, str] = {}
        for node_id in self._graph._graph.nodes():
            data = self._graph.get_service_data(node_id)
            if data:
                for rid in data.get("resource_ids", []):
                    resource_to_service[rid] = node_id

        for app in applications:
            for resource_id in app.resource_ids:
                resource = resource_map.get(resource_id)
                if not resource:
                    continue

                source_svc = resource_to_service.get(resource_id)
                if not source_svc:
                    continue

                # Check environment variables for database/service references
                env_vars = resource.metadata.get("environment_variables", {})
                if isinstance(env_vars, dict):
                    for key, value in env_vars.items():
                        key_lower = key.lower()
                        if any(
                            indicator in key_lower
                            for indicator in ["database_url", "db_host", "redis_url", "cache_url", "api_url"]
                        ):
                            # Find target service by matching hostname
                            for other_id, other_svc in resource_to_service.items():
                                if other_svc != source_svc:
                                    other_res = resource_map.get(other_id)
                                    if other_res and isinstance(value, str) and other_res.name in value:
                                        dep = ServiceDependency(
                                            source_service_id=source_svc,
                                            target_service_id=other_svc,
                                            dependency_type=DependencyCoupling.DATA,
                                            protocol=DependencyProtocol.SQL if "database" in key_lower or "db" in key_lower else DependencyProtocol.REDIS if "redis" in key_lower else DependencyProtocol.UNKNOWN,
                                            metadata={"source": "env_var", "env_key": key},
                                        )
                                        self._graph.add_dependency(dep)

    def _infer_from_load_balancers(
        self,
        applications: list[Application],
        resource_map: dict[str, CloudResource],
    ) -> None:
        """Infer dependencies from load balancer target groups.

        Args:
            applications: Discovered applications
            resource_map: Resource ID → CloudResource mapping
        """
        resource_to_service: dict[str, str] = {}
        for node_id in self._graph._graph.nodes():
            data = self._graph.get_service_data(node_id)
            if data:
                for rid in data.get("resource_ids", []):
                    resource_to_service[rid] = node_id

        lb_types = {ResourceType.ALB, ResourceType.NLB, ResourceType.ELB, ResourceType.AZURE_LOAD_BALANCER, ResourceType.GCP_LOAD_BALANCER}

        for app in applications:
            for resource_id in app.resource_ids:
                resource = resource_map.get(resource_id)
                if not resource or resource.type not in lb_types:
                    continue

                lb_svc = resource_to_service.get(resource_id)
                if not lb_svc:
                    continue

                # Check target instances/services
                targets = resource.metadata.get("target_instances", [])
                if isinstance(targets, list):
                    for target_id in targets:
                        target_svc = resource_to_service.get(target_id)
                        if target_svc and target_svc != lb_svc:
                            dep = ServiceDependency(
                                source_service_id=lb_svc,
                                target_service_id=target_svc,
                                dependency_type=DependencyCoupling.SYNCHRONOUS,
                                protocol=DependencyProtocol.HTTPS,
                                is_critical=True,
                                metadata={"source": "load_balancer"},
                            )
                            self._graph.add_dependency(dep)

    def _infer_from_kubernetes(
        self,
        applications: list[Application],
        resource_map: dict[str, CloudResource],
    ) -> None:
        """Infer dependencies from K8s services and ingress rules.

        Args:
            applications: Discovered applications
            resource_map: Resource ID → CloudResource mapping
        """
        resource_to_service: dict[str, str] = {}
        for node_id in self._graph._graph.nodes():
            data = self._graph.get_service_data(node_id)
            if data:
                for rid in data.get("resource_ids", []):
                    resource_to_service[rid] = node_id

        for app in applications:
            for resource_id in app.resource_ids:
                resource = resource_map.get(resource_id)
                if not resource:
                    continue

                # K8s Ingress → Service dependency
                if resource.type == ResourceType.K8S_INGRESS:
                    ingress_svc = resource_to_service.get(resource_id)
                    backend_service = resource.metadata.get("backend_service")
                    if ingress_svc and backend_service:
                        # Find the service node for the backend
                        for other_id, other_svc in resource_to_service.items():
                            other_res = resource_map.get(other_id)
                            if (
                                other_res
                                and other_res.type == ResourceType.K8S_SERVICE
                                and other_res.name == backend_service
                                and other_svc != ingress_svc
                            ):
                                dep = ServiceDependency(
                                    source_service_id=ingress_svc,
                                    target_service_id=other_svc,
                                    dependency_type=DependencyCoupling.SYNCHRONOUS,
                                    protocol=DependencyProtocol.HTTP,
                                    is_critical=True,
                                    metadata={"source": "k8s_ingress"},
                                )
                                self._graph.add_dependency(dep)

    @staticmethod
    def _classify_service_type(resource: CloudResource) -> ServiceType:
        """Classify a resource into a service type.

        Args:
            resource: Cloud resource

        Returns:
            Inferred ServiceType
        """
        type_mapping: dict[ResourceType, ServiceType] = {
            ResourceType.ALB: ServiceType.LOAD_BALANCER,
            ResourceType.NLB: ServiceType.LOAD_BALANCER,
            ResourceType.ELB: ServiceType.LOAD_BALANCER,
            ResourceType.AZURE_LOAD_BALANCER: ServiceType.LOAD_BALANCER,
            ResourceType.AZURE_APPLICATION_GATEWAY: ServiceType.LOAD_BALANCER,
            ResourceType.GCP_LOAD_BALANCER: ServiceType.LOAD_BALANCER,
            ResourceType.RDS_DATABASE: ServiceType.DATABASE,
            ResourceType.RDS_CLUSTER: ServiceType.DATABASE,
            ResourceType.AZURE_SQL_DATABASE: ServiceType.DATABASE,
            ResourceType.AZURE_SQL_SERVER: ServiceType.DATABASE,
            ResourceType.AZURE_COSMOS_DB: ServiceType.DATABASE,
            ResourceType.GCP_SQL_INSTANCE: ServiceType.DATABASE,
            ResourceType.GCP_SQL_DATABASE: ServiceType.DATABASE,
            ResourceType.DYNAMODB_TABLE: ServiceType.DATABASE,
            ResourceType.S3_BUCKET: ServiceType.STORAGE,
            ResourceType.AZURE_STORAGE_ACCOUNT: ServiceType.STORAGE,
            ResourceType.GCP_STORAGE_BUCKET: ServiceType.STORAGE,
            ResourceType.SQS_QUEUE: ServiceType.QUEUE,
            ResourceType.SNS_TOPIC: ServiceType.QUEUE,
            ResourceType.GCP_PUBSUB_TOPIC: ServiceType.QUEUE,
            ResourceType.KINESIS_STREAM: ServiceType.QUEUE,
            ResourceType.CLOUDFRONT_DISTRIBUTION: ServiceType.CDN,
            ResourceType.K8S_INGRESS: ServiceType.API_GATEWAY,
            ResourceType.EC2_INSTANCE: ServiceType.BACKEND,
            ResourceType.AZURE_VM: ServiceType.BACKEND,
            ResourceType.GCP_COMPUTE_INSTANCE: ServiceType.BACKEND,
            ResourceType.LAMBDA_FUNCTION: ServiceType.BACKEND,
            ResourceType.AZURE_FUNCTION_APP: ServiceType.BACKEND,
            ResourceType.GCP_CLOUD_FUNCTION: ServiceType.BACKEND,
            ResourceType.GCP_CLOUD_RUN_SERVICE: ServiceType.BACKEND,
            ResourceType.ECS_SERVICE: ServiceType.BACKEND,
            ResourceType.AZURE_APP_SERVICE: ServiceType.BACKEND,
            ResourceType.K8S_DEPLOYMENT: ServiceType.BACKEND,
            ResourceType.K8S_STATEFULSET: ServiceType.BACKEND,
            ResourceType.K8S_POD: ServiceType.BACKEND,
            ResourceType.K8S_DAEMONSET: ServiceType.BACKEND,
            ResourceType.K8S_SERVICE: ServiceType.BACKEND,
        }
        return type_mapping.get(resource.type, ServiceType.UNKNOWN)

    @staticmethod
    def _infer_protocol(service_type: ServiceType) -> DependencyProtocol:
        """Infer default protocol from service type.

        Args:
            service_type: Service type

        Returns:
            Inferred protocol
        """
        protocol_mapping: dict[ServiceType, DependencyProtocol] = {
            ServiceType.DATABASE: DependencyProtocol.SQL,
            ServiceType.CACHE: DependencyProtocol.REDIS,
            ServiceType.QUEUE: DependencyProtocol.AMQP,
            ServiceType.LOAD_BALANCER: DependencyProtocol.HTTPS,
            ServiceType.API_GATEWAY: DependencyProtocol.HTTPS,
            ServiceType.FRONTEND: DependencyProtocol.HTTPS,
            ServiceType.BACKEND: DependencyProtocol.HTTP,
            ServiceType.CDN: DependencyProtocol.HTTPS,
        }
        return protocol_mapping.get(service_type, DependencyProtocol.UNKNOWN)

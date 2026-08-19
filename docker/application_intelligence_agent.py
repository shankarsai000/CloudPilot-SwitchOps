"""
Application Intelligence Agent — Main Orchestrator

M3 module entry point. Transforms M1 infrastructure resources into
business-aware applications by orchestrating discovery, dependency
mapping, topology building, ownership resolution, deployment
analysis, traffic flow modeling, and business criticality scoring.

Pipeline:
    M1 Resources → Discovery → Dependency Mapping → Topology Building →
    Ownership Resolution → Deployment Analysis → Traffic Mapping →
    Business Criticality → Application Graph
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from application_discovery import ApplicationDiscoveryEngine
from business_context import BusinessContextEngine
from dependency_mapper import DependencyMapper
from deployment_analyzer import DeploymentAnalyzer
from graph_exporter import GraphExporter
from models_application import Application, ApplicationGraph
from models_dependency import DependencyGraph
from models_resource import CloudResource, DependencyEdge, ResourceGraph
from models_topology import ApplicationTopology, DeploymentTopology
from observability_connector import ObservabilityConnector
from ownership_mapper import OwnershipMapper
from service_graph import ServiceGraph
from topology_builder import TopologyBuilder
from traffic_mapper import TrafficMapper

logger = logging.getLogger(__name__)


class ApplicationIntelligenceAgent:
    """Main Application Intelligence Agent orchestrator.

    Coordinates all M3 sub-components to produce a complete
    application-aware view of cloud infrastructure. Consumes
    M1 ResourceGraph and optionally enriches with M2 cost data.

    Usage:
        agent = ApplicationIntelligenceAgent()
        graph = agent.discover_applications(m1_resource_graph)
    """

    def __init__(
        self,
        discovery_engine: Optional[ApplicationDiscoveryEngine] = None,
        dependency_mapper: Optional[DependencyMapper] = None,
        topology_builder: Optional[TopologyBuilder] = None,
        ownership_mapper: Optional[OwnershipMapper] = None,
        deployment_analyzer: Optional[DeploymentAnalyzer] = None,
        observability_connector: Optional[ObservabilityConnector] = None,
        traffic_mapper: Optional[TrafficMapper] = None,
        business_engine: Optional[BusinessContextEngine] = None,
        graph_exporter: Optional[GraphExporter] = None,
    ) -> None:
        """Initialize the Application Intelligence Agent.

        All sub-components are injected via constructor. Defaults are
        created if not provided, enabling easy testing with mocks.

        Args:
            discovery_engine: Application discovery engine
            dependency_mapper: Service dependency mapper
            topology_builder: Topology builder
            ownership_mapper: Ownership resolver
            deployment_analyzer: Deployment intelligence
            observability_connector: Monitoring integration
            traffic_mapper: Traffic flow mapper
            business_engine: Business criticality calculator
            graph_exporter: Graph serialization engine
        """
        self._discovery = discovery_engine or ApplicationDiscoveryEngine()
        self._dependency_mapper = dependency_mapper or DependencyMapper()
        self._topology_builder = topology_builder or TopologyBuilder()
        self._ownership_mapper = ownership_mapper or OwnershipMapper()
        self._deployment_analyzer = deployment_analyzer or DeploymentAnalyzer()
        self._observability = observability_connector or ObservabilityConnector()
        self._traffic_mapper = traffic_mapper or TrafficMapper()
        self._business_engine = business_engine or BusinessContextEngine()
        self._graph_exporter = graph_exporter or GraphExporter()

        # State
        self._applications: list[Application] = []
        self._service_graph: ServiceGraph = ServiceGraph()
        self._application_graph: Optional[ApplicationGraph] = None
        self._resources: list[CloudResource] = []
        self._m1_dependencies: list[DependencyEdge] = []

        logger.info("ApplicationIntelligenceAgent initialized")

    def discover_applications(
        self,
        resource_graph: ResourceGraph,
    ) -> ApplicationGraph:
        """Run the complete application discovery pipeline.

        Pipeline stages:
        1. Extract resources from M1 ResourceGraph
        2. Discover applications (group resources)
        3. Map service dependencies
        4. Build application topologies
        5. Resolve ownership
        6. Analyze deployments
        7. Map traffic flows
        8. Calculate business criticality
        9. Build final ApplicationGraph

        Args:
            resource_graph: M1 ResourceGraph with discovered resources

        Returns:
            Complete ApplicationGraph
        """
        logger.info(
            "Starting application discovery pipeline (%d resources, %d dependencies)",
            len(resource_graph.resources),
            len(resource_graph.dependencies),
        )

        self._resources = resource_graph.resources
        self._m1_dependencies = resource_graph.dependencies
        failures: list[str] = list(resource_graph.failures)

        # Stage 1: Discover applications
        try:
            self._applications = self._discovery.discover(self._resources)
            logger.info("Stage 1 - Discovered %d applications", len(self._applications))
        except Exception as e:
            error = f"Application discovery failed: {e}"
            logger.error(error)
            failures.append(error)
            self._applications = []

        # Stage 2: Map dependencies
        try:
            self._service_graph = self._dependency_mapper.map_dependencies(
                self._applications, self._resources, self._m1_dependencies
            )
            logger.info(
                "Stage 2 - Mapped %d service nodes, %d dependency edges",
                self._service_graph.node_count,
                self._service_graph.edge_count,
            )
        except Exception as e:
            error = f"Dependency mapping failed: {e}"
            logger.error(error)
            failures.append(error)

        # Stage 3: Build topologies
        try:
            self._build_topologies()
            logger.info("Stage 3 - Built topologies for %d applications", len(self._applications))
        except Exception as e:
            error = f"Topology building failed: {e}"
            logger.error(error)
            failures.append(error)

        # Stage 4: Resolve ownership
        try:
            mappings = self._ownership_mapper.map_ownership(
                self._applications, self._resources
            )
            logger.info("Stage 4 - Resolved ownership for %d applications", len(mappings))
        except Exception as e:
            error = f"Ownership resolution failed: {e}"
            logger.error(error)
            failures.append(error)

        # Stage 5: Analyze deployments
        try:
            deployments = self._deployment_analyzer.analyze_deployments(
                self._applications, self._resources
            )
            total_deploys = sum(len(d) for d in deployments.values())
            logger.info("Stage 5 - Found %d deployment records", total_deploys)
        except Exception as e:
            error = f"Deployment analysis failed: {e}"
            logger.error(error)
            failures.append(error)

        # Stage 6: Map traffic flows
        try:
            for app in self._applications:
                self._traffic_mapper.map_traffic_flows(app, self._service_graph)
            logger.info("Stage 6 - Mapped traffic flows")
        except Exception as e:
            error = f"Traffic mapping failed: {e}"
            logger.error(error)
            failures.append(error)

        # Stage 7: Calculate business criticality
        try:
            self._business_engine.calculate_all(
                self._applications, self._service_graph
            )
            logger.info("Stage 7 - Calculated business criticality")
        except Exception as e:
            error = f"Business criticality calculation failed: {e}"
            logger.error(error)
            failures.append(error)

        # Stage 8: Build final ApplicationGraph
        self._application_graph = self._build_application_graph(failures)

        logger.info(
            "Application discovery pipeline complete: "
            "%d applications, %d services, %d dependencies, %d failures",
            self._application_graph.total_applications,
            self._application_graph.total_services,
            self._application_graph.total_dependencies,
            len(self._application_graph.failures),
        )

        return self._application_graph

    def get_application_graph(self) -> Optional[ApplicationGraph]:
        """Return the current application graph.

        Returns:
            ApplicationGraph or None if discovery hasn't run
        """
        return self._application_graph

    def get_application(self, application_id: str) -> Optional[Application]:
        """Get a single application by ID.

        Args:
            application_id: Application identifier

        Returns:
            Application or None
        """
        for app in self._applications:
            if app.application_id == application_id:
                return app
        return None

    def get_application_topology(
        self, application_id: str
    ) -> Optional[ApplicationTopology]:
        """Get topology for a single application.

        Args:
            application_id: Application identifier

        Returns:
            ApplicationTopology or None
        """
        app = self.get_application(application_id)
        if not app:
            return None

        return self._topology_builder.build_topology(
            app, self._service_graph, self._resources
        )

    def get_application_dependencies(
        self, application_id: str
    ) -> Optional[DependencyGraph]:
        """Get dependency graph for a single application.

        Args:
            application_id: Application identifier

        Returns:
            DependencyGraph or None
        """
        app = self.get_application(application_id)
        if not app:
            return None

        return self._dependency_mapper.get_dependency_graph(application_id)

    def get_deployment_topology(
        self, application_id: str
    ) -> Optional[DeploymentTopology]:
        """Get deployment topology for a single application.

        Args:
            application_id: Application identifier

        Returns:
            DeploymentTopology or None
        """
        app = self.get_application(application_id)
        if not app:
            return None

        topology = self.get_application_topology(application_id)
        if not topology:
            return None

        return self._topology_builder.get_deployment_topology(
            app, topology, self._resources
        )

    def enrich_from_cost_data(
        self,
        cost_data: dict[str, float],
    ) -> None:
        """Enrich applications with M2 cost data (loosely coupled).

        Args:
            cost_data: Dict mapping resource_id → monthly cost
        """
        for app in self._applications:
            total_cost: float = 0.0
            for resource_id in app.resource_ids:
                if resource_id in cost_data:
                    total_cost += cost_data[resource_id]
            app.total_monthly_cost = round(total_cost, 2) if total_cost > 0 else None

        logger.info("Enriched %d applications with cost data", len(self._applications))

    def refresh(self, resource_graph: ResourceGraph) -> ApplicationGraph:
        """Re-run the full discovery pipeline with fresh M1 data.

        Args:
            resource_graph: Updated M1 ResourceGraph

        Returns:
            Fresh ApplicationGraph
        """
        logger.info("Refreshing application discovery")
        return self.discover_applications(resource_graph)

    def get_service_graph(self) -> ServiceGraph:
        """Return the current service graph.

        Returns:
            ServiceGraph instance
        """
        return self._service_graph

    def get_graph_exporter(self) -> GraphExporter:
        """Return the graph exporter.

        Returns:
            GraphExporter instance
        """
        return self._graph_exporter

    def _build_topologies(self) -> None:
        """Build topologies for all applications."""
        for app in self._applications:
            try:
                topology = self._topology_builder.build_topology(
                    app, self._service_graph, self._resources
                )
                # Attach service nodes from the topology to the application
                for node in topology.nodes:
                    from models_application import ServiceNode, ServiceType, DependencyProtocol

                    try:
                        svc_type = ServiceType(node.service_type)
                    except ValueError:
                        svc_type = ServiceType.UNKNOWN

                    svc_node = ServiceNode(
                        service_id=node.node_id,
                        name=node.name,
                        service_type=svc_type,
                        port=node.port,
                        resource_ids=node.resource_ids,
                        health_status=node.health.value,
                    )
                    # Avoid duplicates
                    existing_ids = {s.service_id for s in app.services}
                    if svc_node.service_id not in existing_ids:
                        app.services.append(svc_node)
            except Exception as e:
                logger.warning(
                    "Failed to build topology for %s: %s", app.name, e
                )

    def _build_application_graph(
        self, failures: list[str]
    ) -> ApplicationGraph:
        """Build the final ApplicationGraph with statistics.

        Args:
            failures: List of pipeline failures

        Returns:
            ApplicationGraph model
        """
        # Compute statistics
        apps_by_type: dict[str, int] = {}
        apps_by_env: dict[str, int] = {}
        apps_by_tier: dict[str, int] = {}
        total_services: int = 0
        total_deps: int = 0

        for app in self._applications:
            type_key = app.application_type.value
            apps_by_type[type_key] = apps_by_type.get(type_key, 0) + 1

            env_key = app.environment.value
            apps_by_env[env_key] = apps_by_env.get(env_key, 0) + 1

            tier_key = app.tier.value
            apps_by_tier[tier_key] = apps_by_tier.get(tier_key, 0) + 1

            total_services += len(app.services)
            total_deps += len(app.dependencies)

        # Find unassigned resources
        assigned_ids: set[str] = set()
        for app in self._applications:
            assigned_ids.update(app.resource_ids)
        all_ids = {r.id for r in self._resources}
        unassigned = sorted(all_ids - assigned_ids)

        return ApplicationGraph(
            applications=self._applications,
            total_applications=len(self._applications),
            total_services=total_services,
            total_dependencies=total_deps,
            applications_by_type=apps_by_type,
            applications_by_environment=apps_by_env,
            applications_by_tier=apps_by_tier,
            unassigned_resources=unassigned,
            failures=failures,
        )

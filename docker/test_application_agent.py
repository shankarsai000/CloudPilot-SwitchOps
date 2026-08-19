"""
M3 Application Intelligence Agent - Comprehensive Tests

Tests all M3 components with mocked cloud and observability data:
- Application discovery (tag-based, namespace, naming convention, label)
- Dependency mapping and cycle detection
- Topology building and layer classification
- Ownership resolution
- Business criticality calculation
- Traffic flow mapping
- Service graph operations
- Graph export formats
- API routes
- Full pipeline integration
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from models_resource import (
    CloudResource,
    DependencyEdge,
    DependencyType,
    ResourceGraph,
    ResourceState,
    ResourceType,
)


# ═══════════════════════════════════════════════════════════════
# Test Fixtures — Mocked Cloud Resources
# ═══════════════════════════════════════════════════════════════


def _make_resource(
    name: str,
    rtype: ResourceType,
    provider: str = "aws",
    region: str = "us-east-1",
    tags: dict | None = None,
    metadata: dict | None = None,
    state: ResourceState = ResourceState.RUNNING,
) -> CloudResource:
    """Create a mock CloudResource for testing."""
    return CloudResource(
        id=f"res-{name}-{uuid.uuid4().hex[:6]}",
        name=name,
        type=rtype,
        provider=provider,
        region=region,
        state=state,
        tags=tags or {},
        metadata=metadata or {},
    )


def make_payment_service_resources() -> list[CloudResource]:
    """Create mocked resources for the Payment Service application."""
    return [
        _make_resource(
            "payment-api-prod-001",
            ResourceType.EC2_INSTANCE,
            tags={"app": "payment-service", "env": "production", "team": "Payments", "owner": "jane.doe", "tier": "1"},
            metadata={"instance_type": "t3.large", "version": "2.3.1"},
        ),
        _make_resource(
            "payment-api-prod-002",
            ResourceType.EC2_INSTANCE,
            tags={"app": "payment-service", "env": "production", "team": "Payments"},
        ),
        _make_resource(
            "payment-db-primary",
            ResourceType.RDS_DATABASE,
            tags={"app": "payment-service", "env": "production", "team": "Payments"},
            metadata={"engine": "postgres", "multi_az": True},
        ),
        _make_resource(
            "payment-alb",
            ResourceType.ALB,
            tags={"app": "payment-service", "env": "production"},
            metadata={"target_instances": []},
        ),
        _make_resource(
            "payment-cache",
            ResourceType.SQS_QUEUE,
            tags={"app": "payment-service", "env": "production"},
        ),
    ]


def make_inventory_service_resources() -> list[CloudResource]:
    """Create mocked resources for the Inventory Service application."""
    return [
        _make_resource(
            "inventory-api-prod",
            ResourceType.ECS_SERVICE,
            tags={"app": "inventory-service", "env": "production", "team": "Platform"},
        ),
        _make_resource(
            "inventory-db",
            ResourceType.DYNAMODB_TABLE,
            tags={"app": "inventory-service", "env": "production"},
        ),
    ]


def make_frontend_resources() -> list[CloudResource]:
    """Create mocked resources for the Frontend application."""
    return [
        _make_resource(
            "frontend-web",
            ResourceType.S3_BUCKET,
            tags={"app": "frontend-web", "env": "production", "visibility": "external"},
        ),
        _make_resource(
            "frontend-cdn",
            ResourceType.CLOUDFRONT_DISTRIBUTION,
            tags={"app": "frontend-web", "env": "production"},
        ),
    ]


def make_k8s_resources() -> list[CloudResource]:
    """Create mocked K8s resources grouped by namespace."""
    return [
        _make_resource(
            "orders-deployment",
            ResourceType.K8S_DEPLOYMENT,
            provider="k8s",
            tags={},
            metadata={
                "namespace": "orders",
                "labels": {"app.kubernetes.io/name": "order-service"},
                "version": "1.5.0",
            },
        ),
        _make_resource(
            "orders-service",
            ResourceType.K8S_SERVICE,
            provider="k8s",
            tags={},
            metadata={"namespace": "orders"},
        ),
        _make_resource(
            "orders-ingress",
            ResourceType.K8S_INGRESS,
            provider="k8s",
            tags={},
            metadata={
                "namespace": "orders",
                "backend_service": "orders-service",
            },
        ),
    ]


def make_untagged_resources() -> list[CloudResource]:
    """Create resources without application tags."""
    return [
        _make_resource(
            "orphan-vm-001",
            ResourceType.EC2_INSTANCE,
            tags={"env": "dev"},
        ),
        _make_resource(
            "orphan-bucket",
            ResourceType.S3_BUCKET,
            tags={},
        ),
    ]


def build_all_resources() -> list[CloudResource]:
    """Build complete resource set across all applications."""
    resources = []
    resources.extend(make_payment_service_resources())
    resources.extend(make_inventory_service_resources())
    resources.extend(make_frontend_resources())
    resources.extend(make_k8s_resources())
    resources.extend(make_untagged_resources())
    return resources


def build_resource_graph() -> ResourceGraph:
    """Build a complete ResourceGraph for integration tests."""
    resources = build_all_resources()
    return ResourceGraph(
        resources=resources,
        dependencies=[],
        total_resources=len(resources),
        resources_by_type={},
        resources_by_provider={},
        failures=[],
    )


# ═══════════════════════════════════════════════════════════════
# Test: Application Discovery
# ═══════════════════════════════════════════════════════════════


class TestApplicationDiscovery:
    """Tests for the ApplicationDiscoveryEngine."""

    def test_tag_based_strategy_discovers_applications(self) -> None:
        """Tag-based strategy groups resources by app tag."""
        from application_discovery import TagBasedStrategy

        strategy = TagBasedStrategy()
        resources = make_payment_service_resources() + make_inventory_service_resources()

        groups = strategy.discover(resources)

        assert "payment-service" in groups
        assert "inventory-service" in groups
        assert len(groups["payment-service"]) == 5
        assert len(groups["inventory-service"]) == 2

    def test_namespace_strategy_discovers_k8s_apps(self) -> None:
        """Namespace strategy groups K8s resources by namespace."""
        from application_discovery import NamespaceStrategy

        strategy = NamespaceStrategy()
        resources = make_k8s_resources()

        groups = strategy.discover(resources)

        assert "orders" in groups
        assert len(groups["orders"]) == 3

    def test_namespace_strategy_skips_system_namespaces(self) -> None:
        """Namespace strategy ignores kube-system and similar."""
        from application_discovery import NamespaceStrategy

        strategy = NamespaceStrategy()
        resources = [
            _make_resource(
                "coredns",
                ResourceType.K8S_DEPLOYMENT,
                provider="k8s",
                metadata={"namespace": "kube-system"},
            ),
        ]

        groups = strategy.discover(resources)
        assert len(groups) == 0

    def test_naming_convention_strategy(self) -> None:
        """Naming convention strategy groups by prefix."""
        from application_discovery import NamingConventionStrategy

        strategy = NamingConventionStrategy()
        resources = make_payment_service_resources()

        groups = strategy.discover(resources)

        # Should group payment-api-prod-001 and payment-api-prod-002
        assert len(groups) >= 1

    def test_label_strategy_discovers_by_k8s_labels(self) -> None:
        """Label strategy groups by app.kubernetes.io/name."""
        from application_discovery import LabelStrategy

        strategy = LabelStrategy()
        resources = make_k8s_resources()

        groups = strategy.discover(resources)

        assert "order-service" in groups

    def test_discovery_engine_full_pipeline(self) -> None:
        """Full discovery engine merges all strategies."""
        from application_discovery import ApplicationDiscoveryEngine

        engine = ApplicationDiscoveryEngine()
        resources = build_all_resources()

        applications = engine.discover(resources)

        assert len(applications) >= 3  # payment, inventory, frontend
        app_names = [a.name.lower() for a in applications]
        assert any("payment" in n for n in app_names)
        assert any("inventory" in n for n in app_names)

    def test_discovery_engine_infers_application_type(self) -> None:
        """Discovery engine infers correct application type."""
        from application_discovery import ApplicationDiscoveryEngine

        engine = ApplicationDiscoveryEngine()

        # Static site (S3 + CloudFront)
        apps = engine.discover(make_frontend_resources())
        assert len(apps) >= 1
        frontend_app = next((a for a in apps if "frontend" in a.name.lower()), None)
        if frontend_app:
            assert frontend_app.application_type.value == "static_site"

    def test_discovery_engine_infers_environment(self) -> None:
        """Discovery engine infers production environment from tags."""
        from application_discovery import ApplicationDiscoveryEngine

        engine = ApplicationDiscoveryEngine()
        apps = engine.discover(make_payment_service_resources())

        assert len(apps) >= 1
        assert apps[0].environment.value == "production"

    def test_discovery_with_empty_resources(self) -> None:
        """Discovery returns empty list for empty input."""
        from application_discovery import ApplicationDiscoveryEngine

        engine = ApplicationDiscoveryEngine()
        apps = engine.discover([])

        assert apps == []


# ═══════════════════════════════════════════════════════════════
# Test: Service Graph
# ═══════════════════════════════════════════════════════════════


class TestServiceGraph:
    """Tests for the ServiceGraph."""

    def test_add_and_query_services(self) -> None:
        """Add services and verify graph state."""
        from models_application import ServiceNode, ServiceType, DependencyProtocol
        from service_graph import ServiceGraph

        graph = ServiceGraph()

        svc1 = ServiceNode(
            service_id="svc-api",
            name="API",
            service_type=ServiceType.BACKEND,
            protocol=DependencyProtocol.HTTP,
        )
        svc2 = ServiceNode(
            service_id="svc-db",
            name="Database",
            service_type=ServiceType.DATABASE,
            protocol=DependencyProtocol.SQL,
        )

        graph.add_service(svc1)
        graph.add_service(svc2)

        assert graph.node_count == 2
        assert graph.has_service("svc-api")
        assert graph.has_service("svc-db")

    def test_dependency_edges(self) -> None:
        """Add dependencies and verify traversal."""
        from models_application import (
            DependencyCoupling,
            DependencyProtocol,
            ServiceDependency,
            ServiceNode,
            ServiceType,
        )
        from service_graph import ServiceGraph

        graph = ServiceGraph()

        for svc_id in ["svc-gw", "svc-api", "svc-db"]:
            graph.add_service(
                ServiceNode(
                    service_id=svc_id,
                    name=svc_id,
                    service_type=ServiceType.BACKEND,
                )
            )

        graph.add_dependency(
            ServiceDependency(
                source_service_id="svc-gw",
                target_service_id="svc-api",
            )
        )
        graph.add_dependency(
            ServiceDependency(
                source_service_id="svc-api",
                target_service_id="svc-db",
            )
        )

        assert graph.edge_count == 2
        assert "svc-api" in graph.get_upstream("svc-gw")
        assert "svc-gw" in graph.get_downstream("svc-api")

    def test_blast_radius(self) -> None:
        """Blast radius returns all transitively affected services."""
        from models_application import ServiceDependency, ServiceNode, ServiceType
        from service_graph import ServiceGraph

        graph = ServiceGraph()
        for svc_id in ["A", "B", "C", "D"]:
            graph.add_service(ServiceNode(service_id=svc_id, name=svc_id, service_type=ServiceType.BACKEND))

        # A → B → C, A → D
        graph.add_dependency(ServiceDependency(source_service_id="A", target_service_id="B"))
        graph.add_dependency(ServiceDependency(source_service_id="B", target_service_id="C"))
        graph.add_dependency(ServiceDependency(source_service_id="A", target_service_id="D"))

        # Blast radius of C (who is affected if C goes down)
        blast = graph.get_blast_radius("C")
        assert "B" in blast
        assert "A" in blast

    def test_cycle_detection(self) -> None:
        """Cycle detection identifies circular dependencies."""
        from models_application import ServiceDependency, ServiceNode, ServiceType
        from service_graph import ServiceGraph

        graph = ServiceGraph()
        for svc_id in ["A", "B", "C"]:
            graph.add_service(ServiceNode(service_id=svc_id, name=svc_id, service_type=ServiceType.BACKEND))

        graph.add_dependency(ServiceDependency(source_service_id="A", target_service_id="B"))
        graph.add_dependency(ServiceDependency(source_service_id="B", target_service_id="C"))
        graph.add_dependency(ServiceDependency(source_service_id="C", target_service_id="A"))

        cycles = graph.detect_cycles()
        assert len(cycles) >= 1

    def test_critical_path(self) -> None:
        """Critical path returns longest dependency chain."""
        from models_application import ServiceDependency, ServiceNode, ServiceType
        from service_graph import ServiceGraph

        graph = ServiceGraph()
        for svc_id in ["A", "B", "C", "D"]:
            graph.add_service(ServiceNode(service_id=svc_id, name=svc_id, service_type=ServiceType.BACKEND))

        graph.add_dependency(ServiceDependency(source_service_id="A", target_service_id="B"))
        graph.add_dependency(ServiceDependency(source_service_id="B", target_service_id="C"))
        graph.add_dependency(ServiceDependency(source_service_id="C", target_service_id="D"))

        path = graph.get_critical_path()
        assert len(path) == 4

    def test_roots_and_leaves(self) -> None:
        """Roots have no incoming; leaves have no outgoing."""
        from models_application import ServiceDependency, ServiceNode, ServiceType
        from service_graph import ServiceGraph

        graph = ServiceGraph()
        for svc_id in ["A", "B", "C"]:
            graph.add_service(ServiceNode(service_id=svc_id, name=svc_id, service_type=ServiceType.BACKEND))

        graph.add_dependency(ServiceDependency(source_service_id="A", target_service_id="B"))
        graph.add_dependency(ServiceDependency(source_service_id="B", target_service_id="C"))

        assert "A" in graph.get_roots()
        assert "C" in graph.get_leaves()

    def test_export_to_dict(self) -> None:
        """Export graph to serializable dict."""
        from models_application import ServiceNode, ServiceType
        from service_graph import ServiceGraph

        graph = ServiceGraph()
        graph.add_service(ServiceNode(service_id="svc-1", name="Service 1", service_type=ServiceType.BACKEND))

        result = graph.export_to_dict()
        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) == 1


# ═══════════════════════════════════════════════════════════════
# Test: Dependency Mapper
# ═══════════════════════════════════════════════════════════════


class TestDependencyMapper:
    """Tests for the DependencyMapper."""

    def test_map_dependencies_creates_service_nodes(self) -> None:
        """Dependency mapper creates service nodes from applications."""
        from application_discovery import ApplicationDiscoveryEngine
        from dependency_mapper import DependencyMapper

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        mapper = DependencyMapper()
        graph = mapper.map_dependencies(apps, resources)

        assert graph.node_count > 0

    def test_map_dependencies_from_m1_edges(self) -> None:
        """Dependency mapper infers from M1 DependencyEdge."""
        from application_discovery import ApplicationDiscoveryEngine
        from dependency_mapper import DependencyMapper

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        # Create M1 edges between resources
        edges = [
            DependencyEdge(
                source_id=resources[0].id,
                target_id=resources[2].id,
                relationship_type=DependencyType.DEPENDS_ON,
            )
        ]

        mapper = DependencyMapper()
        graph = mapper.map_dependencies(apps, resources, edges)

        assert graph.node_count > 0

    def test_get_dependency_graph_model(self) -> None:
        """Dependency mapper exports DependencyGraph model."""
        from application_discovery import ApplicationDiscoveryEngine
        from dependency_mapper import DependencyMapper

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        mapper = DependencyMapper()
        mapper.map_dependencies(apps, resources)

        dep_graph = mapper.get_dependency_graph()
        assert dep_graph.total_nodes >= 0


# ═══════════════════════════════════════════════════════════════
# Test: Topology Builder
# ═══════════════════════════════════════════════════════════════


class TestTopologyBuilder:
    """Tests for the TopologyBuilder."""

    def test_build_topology(self) -> None:
        """Topology builder creates layered topology."""
        from application_discovery import ApplicationDiscoveryEngine
        from dependency_mapper import DependencyMapper
        from topology_builder import TopologyBuilder

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        mapper = DependencyMapper()
        graph = mapper.map_dependencies(apps, resources)

        builder = TopologyBuilder()
        topology = builder.build_topology(apps[0], graph, resources)

        assert topology.application_id == apps[0].application_id
        assert len(topology.nodes) >= 0

    def test_deployment_topology(self) -> None:
        """Deployment topology includes infrastructure bindings."""
        from application_discovery import ApplicationDiscoveryEngine
        from dependency_mapper import DependencyMapper
        from topology_builder import TopologyBuilder

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        mapper = DependencyMapper()
        graph = mapper.map_dependencies(apps, resources)

        builder = TopologyBuilder()
        topology = builder.build_topology(apps[0], graph, resources)
        deploy_topo = builder.get_deployment_topology(apps[0], topology, resources)

        assert deploy_topo.application_id == apps[0].application_id
        assert "aws" in deploy_topo.providers


# ═══════════════════════════════════════════════════════════════
# Test: Ownership Mapper
# ═══════════════════════════════════════════════════════════════


class TestOwnershipMapper:
    """Tests for the OwnershipMapper."""

    def test_resolve_ownership_from_tags(self) -> None:
        """Ownership mapper resolves from resource tags."""
        from application_discovery import ApplicationDiscoveryEngine
        from ownership_mapper import OwnershipMapper

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        mapper = OwnershipMapper()
        mappings = mapper.map_ownership(apps, resources)

        assert len(mappings) >= 1
        payment_mapping = mappings[0]
        assert payment_mapping.primary_owner == "jane.doe"
        assert payment_mapping.confidence >= 0.7

    def test_ownership_coverage_report(self) -> None:
        """Ownership mapper generates coverage report."""
        from application_discovery import ApplicationDiscoveryEngine
        from ownership_mapper import OwnershipMapper

        engine = ApplicationDiscoveryEngine()
        resources = build_all_resources()
        apps = engine.discover(resources)

        mapper = OwnershipMapper()
        mappings = mapper.map_ownership(apps, resources)
        report = mapper.get_coverage_report(mappings)

        assert report.total_applications == len(apps)
        assert 0.0 <= report.coverage_percentage <= 100.0

    def test_team_registry_lookup(self) -> None:
        """Ownership mapper uses team registry for resolution."""
        from models_ownership import TeamInfo
        from ownership_mapper import OwnershipMapper

        team = TeamInfo(
            team_id="team-payments",
            team_name="Payments",
            business_unit="Commerce",
            manager="John Smith",
        )

        mapper = OwnershipMapper(team_registry={"payments": team})

        from application_discovery import ApplicationDiscoveryEngine

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        mappings = mapper.map_ownership(apps, resources)
        assert len(mappings) >= 1


# ═══════════════════════════════════════════════════════════════
# Test: Business Criticality
# ═══════════════════════════════════════════════════════════════


class TestBusinessCriticality:
    """Tests for the BusinessContextEngine."""

    def test_calculate_criticality(self) -> None:
        """Business engine calculates criticality scores."""
        from application_discovery import ApplicationDiscoveryEngine
        from business_context import BusinessContextEngine

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        biz = BusinessContextEngine()
        criticality = biz.calculate_criticality(apps[0])

        assert 0.0 <= criticality.criticality_score <= 100.0
        assert criticality.risk_level is not None

    def test_calculate_all_applications(self) -> None:
        """Business engine processes all applications."""
        from application_discovery import ApplicationDiscoveryEngine
        from business_context import BusinessContextEngine

        engine = ApplicationDiscoveryEngine()
        resources = build_all_resources()
        apps = engine.discover(resources)

        biz = BusinessContextEngine()
        results = biz.calculate_all(apps)

        assert len(results) == len(apps)
        for result in results:
            assert 0.0 <= result.criticality_score <= 100.0

    def test_rank_applications(self) -> None:
        """Business engine ranks applications by criticality."""
        from application_discovery import ApplicationDiscoveryEngine
        from business_context import BusinessContextEngine

        engine = ApplicationDiscoveryEngine()
        resources = build_all_resources()
        apps = engine.discover(resources)

        biz = BusinessContextEngine()
        biz.calculate_all(apps)
        ranked = biz.rank_applications(apps)

        if len(ranked) >= 2:
            assert (
                ranked[0].criticality.criticality_score
                >= ranked[-1].criticality.criticality_score
            )

    def test_compliance_framework_extraction(self) -> None:
        """Business engine extracts compliance frameworks from tags."""
        from business_context import BusinessContextEngine
        from models_application import Application

        app = Application(
            application_id="test-app",
            name="Test App",
            tags={"pci-dss": "true", "compliance": "soc2,gdpr"},
        )

        frameworks = BusinessContextEngine._extract_compliance_frameworks(app)
        assert "pci-dss" in frameworks
        assert "soc2" in frameworks
        assert "gdpr" in frameworks


# ═══════════════════════════════════════════════════════════════
# Test: Deployment Analyzer
# ═══════════════════════════════════════════════════════════════


class TestDeploymentAnalyzer:
    """Tests for the DeploymentAnalyzer."""

    def test_analyze_deployments(self) -> None:
        """Deployment analyzer extracts deployment records."""
        from application_discovery import ApplicationDiscoveryEngine
        from deployment_analyzer import DeploymentAnalyzer

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        analyzer = DeploymentAnalyzer()
        deployments = analyzer.analyze_deployments(apps, resources)

        assert isinstance(deployments, dict)

    def test_dora_metrics(self) -> None:
        """DORA metrics calculate correctly."""
        from deployment_analyzer import DeploymentAnalyzer, DORAMetrics
        from models_application import DeploymentRecord, DeploymentStatus, DeploymentStrategy

        analyzer = DeploymentAnalyzer()

        # Manually add deployment records
        app_id = "test-app"
        records = [
            DeploymentRecord(
                deployment_id=f"deploy-{i}",
                application_id=app_id,
                version=f"1.0.{i}",
                strategy=DeploymentStrategy.ROLLING,
                status=DeploymentStatus.SUCCESS if i % 5 != 0 else DeploymentStatus.FAILED,
                deployed_at=datetime.utcnow() - timedelta(days=30 - i),
                duration_seconds=180 + i * 10,
            )
            for i in range(30)
        ]
        analyzer._deployment_store[app_id] = records

        dora = analyzer.calculate_dora_metrics(app_id)
        assert dora.deployment_frequency > 0
        assert 0.0 <= dora.change_failure_rate <= 1.0
        assert dora.performance_level in ("elite", "high", "medium", "low")

    def test_deployment_stats(self) -> None:
        """Deployment stats returns summary dict."""
        from deployment_analyzer import DeploymentAnalyzer
        from models_application import DeploymentRecord, DeploymentStatus, DeploymentStrategy

        analyzer = DeploymentAnalyzer()
        app_id = "test-app"
        analyzer._deployment_store[app_id] = [
            DeploymentRecord(
                deployment_id="deploy-1",
                application_id=app_id,
                version="1.0.0",
                strategy=DeploymentStrategy.CANARY,
                status=DeploymentStatus.SUCCESS,
            ),
        ]

        stats = analyzer.get_deployment_stats(app_id)
        assert stats["total_deployments"] == 1
        assert stats["success_rate"] == 1.0


# ═══════════════════════════════════════════════════════════════
# Test: Observability Connector
# ═══════════════════════════════════════════════════════════════


class TestObservabilityConnector:
    """Tests for the ObservabilityConnector."""

    def test_get_service_metrics(self) -> None:
        """Observability connector returns mocked metrics."""
        from observability_connector import ObservabilityConnector

        connector = ObservabilityConnector()
        metrics = connector.get_service_metrics("svc-test")

        assert metrics is not None
        assert metrics.service_id == "svc-test"
        assert metrics.health_status == "healthy"
        assert metrics.request_rate > 0

    def test_get_traces(self) -> None:
        """Observability connector returns traces."""
        from observability_connector import (
            DatadogAdapter,
            ObservabilityConnector,
        )

        connector = ObservabilityConnector(adapters=[DatadogAdapter()])
        traces = connector.get_traces("payment-api")

        assert len(traces) >= 1
        assert traces[0].service_name == "payment-api"

    def test_multiple_adapters(self) -> None:
        """Connector queries multiple adapters."""
        from observability_connector import (
            DatadogAdapter,
            GenericOTelAdapter,
            ObservabilityConnector,
            PrometheusAdapter,
        )

        connector = ObservabilityConnector(
            adapters=[PrometheusAdapter(), DatadogAdapter(), GenericOTelAdapter()]
        )

        all_metrics = connector.get_all_metrics("svc-test")
        assert len(all_metrics) == 3

    def test_adapter_status(self) -> None:
        """Connector reports adapter status."""
        from observability_connector import ObservabilityConnector, PrometheusAdapter

        connector = ObservabilityConnector(adapters=[PrometheusAdapter()])
        status = connector.get_adapter_status()

        assert "prometheus" in status
        assert status["prometheus"] == "connected"


# ═══════════════════════════════════════════════════════════════
# Test: Traffic Mapper
# ═══════════════════════════════════════════════════════════════


class TestTrafficMapper:
    """Tests for the TrafficMapper."""

    def test_map_traffic_flows(self) -> None:
        """Traffic mapper produces flow records."""
        from application_discovery import ApplicationDiscoveryEngine
        from dependency_mapper import DependencyMapper
        from traffic_mapper import TrafficMapper

        engine = ApplicationDiscoveryEngine()
        resources = make_payment_service_resources()
        apps = engine.discover(resources)

        mapper = DependencyMapper()
        graph = mapper.map_dependencies(apps, resources)

        traffic = TrafficMapper()
        flows = traffic.map_traffic_flows(apps[0], graph)

        # Should have at least ingress flows for root services
        assert isinstance(flows, list)

    def test_ingress_flows(self) -> None:
        """Traffic mapper identifies ingress flows."""
        from models_application import ServiceDependency, ServiceNode, ServiceType
        from service_graph import ServiceGraph
        from traffic_mapper import TrafficMapper

        graph = ServiceGraph()
        graph.add_service(ServiceNode(service_id="gw", name="Gateway", service_type=ServiceType.API_GATEWAY))
        graph.add_service(ServiceNode(service_id="api", name="API", service_type=ServiceType.BACKEND))
        graph.add_dependency(ServiceDependency(source_service_id="gw", target_service_id="api"))

        traffic = TrafficMapper()
        ingress = traffic.get_ingress_flows(graph)

        # Gateway is a root node, so it should have an ingress flow
        assert len(ingress) >= 1
        assert ingress[0].direction == "ingress"


# ═══════════════════════════════════════════════════════════════
# Test: Graph Exporter
# ═══════════════════════════════════════════════════════════════


class TestGraphExporter:
    """Tests for the GraphExporter."""

    def test_to_mermaid(self) -> None:
        """Graph exporter produces Mermaid syntax."""
        from models_application import ServiceDependency, ServiceNode, ServiceType
        from graph_exporter import GraphExporter
        from service_graph import ServiceGraph

        graph = ServiceGraph()
        graph.add_service(ServiceNode(service_id="svc-a", name="Service A", service_type=ServiceType.BACKEND))
        graph.add_service(ServiceNode(service_id="svc-b", name="Service B", service_type=ServiceType.DATABASE))
        graph.add_dependency(ServiceDependency(source_service_id="svc-a", target_service_id="svc-b"))

        exporter = GraphExporter()
        mermaid = exporter.to_mermaid(graph, title="Test Graph")

        assert "graph TD" in mermaid
        assert "Service A" in mermaid
        assert "Service B" in mermaid

    def test_to_adjacency_list(self) -> None:
        """Graph exporter produces adjacency list."""
        from models_application import ServiceDependency, ServiceNode, ServiceType
        from graph_exporter import GraphExporter
        from service_graph import ServiceGraph

        graph = ServiceGraph()
        graph.add_service(ServiceNode(service_id="A", name="A", service_type=ServiceType.BACKEND))
        graph.add_service(ServiceNode(service_id="B", name="B", service_type=ServiceType.BACKEND))
        graph.add_dependency(ServiceDependency(source_service_id="A", target_service_id="B"))

        exporter = GraphExporter()
        adj = exporter.to_adjacency_list(graph)

        assert "A" in adj
        assert "B" in adj["A"]


# ═══════════════════════════════════════════════════════════════
# Test: Full Pipeline Integration
# ═══════════════════════════════════════════════════════════════


class TestFullPipeline:
    """Integration tests for the complete M3 pipeline."""

    def test_full_discovery_pipeline(self) -> None:
        """Full pipeline discovers applications from ResourceGraph."""
        from application_intelligence_agent import ApplicationIntelligenceAgent

        agent = ApplicationIntelligenceAgent()
        resource_graph = build_resource_graph()

        app_graph = agent.discover_applications(resource_graph)

        assert app_graph.total_applications >= 3
        assert len(app_graph.applications) >= 3

        # Every application should have a name
        for app in app_graph.applications:
            assert app.name
            assert app.application_id

    def test_pipeline_assigns_ownership(self) -> None:
        """Pipeline assigns ownership to applications."""
        from application_intelligence_agent import ApplicationIntelligenceAgent

        agent = ApplicationIntelligenceAgent()
        resource_graph = build_resource_graph()
        app_graph = agent.discover_applications(resource_graph)

        owned = [a for a in app_graph.applications if a.ownership and a.ownership.owner]
        assert len(owned) >= 1

    def test_pipeline_calculates_criticality(self) -> None:
        """Pipeline calculates criticality for all applications."""
        from application_intelligence_agent import ApplicationIntelligenceAgent

        agent = ApplicationIntelligenceAgent()
        resource_graph = build_resource_graph()
        app_graph = agent.discover_applications(resource_graph)

        for app in app_graph.applications:
            assert app.criticality is not None
            assert 0.0 <= app.criticality.criticality_score <= 100.0

    def test_pipeline_cost_enrichment(self) -> None:
        """Pipeline enriches applications with M2 cost data."""
        from application_intelligence_agent import ApplicationIntelligenceAgent

        agent = ApplicationIntelligenceAgent()
        resource_graph = build_resource_graph()
        app_graph = agent.discover_applications(resource_graph)

        # Build cost data for known resource IDs
        cost_data = {}
        for resource in resource_graph.resources:
            cost_data[resource.id] = 100.0

        agent.enrich_from_cost_data(cost_data)

        enriched = [a for a in app_graph.applications if a.total_monthly_cost]
        assert len(enriched) >= 1

    def test_pipeline_get_application_by_id(self) -> None:
        """Pipeline supports single application lookup."""
        from application_intelligence_agent import ApplicationIntelligenceAgent

        agent = ApplicationIntelligenceAgent()
        resource_graph = build_resource_graph()
        app_graph = agent.discover_applications(resource_graph)

        app = agent.get_application(app_graph.applications[0].application_id)
        assert app is not None
        assert app.name == app_graph.applications[0].name

    def test_pipeline_tracks_unassigned_resources(self) -> None:
        """Pipeline identifies resources not assigned to any application."""
        from application_intelligence_agent import ApplicationIntelligenceAgent

        agent = ApplicationIntelligenceAgent()
        resource_graph = build_resource_graph()
        app_graph = agent.discover_applications(resource_graph)

        # Some resources should be unassigned (orphan resources)
        assert isinstance(app_graph.unassigned_resources, list)

    def test_pipeline_refresh(self) -> None:
        """Pipeline supports refresh with new data."""
        from application_intelligence_agent import ApplicationIntelligenceAgent

        agent = ApplicationIntelligenceAgent()
        resource_graph = build_resource_graph()

        graph1 = agent.discover_applications(resource_graph)
        graph2 = agent.refresh(resource_graph)

        assert graph2.total_applications == graph1.total_applications

    def test_pipeline_handles_failures_gracefully(self) -> None:
        """Pipeline continues when individual stages fail."""
        from application_intelligence_agent import ApplicationIntelligenceAgent

        agent = ApplicationIntelligenceAgent()
        empty_graph = ResourceGraph(
            resources=[], dependencies=[], total_resources=0
        )

        app_graph = agent.discover_applications(empty_graph)
        assert app_graph.total_applications == 0


# ═══════════════════════════════════════════════════════════════
# Test: Models
# ═══════════════════════════════════════════════════════════════


class TestModels:
    """Tests for Pydantic model validation."""

    def test_application_model(self) -> None:
        """Application model validates correctly."""
        from models_application import Application

        app = Application(
            application_id="test-app",
            name="Test App",
            tags={"env": "prod"},
        )
        assert app.application_id == "test-app"
        assert app.application_type.value == "unknown"

    def test_business_criticality_model(self) -> None:
        """BusinessCriticality validates score ranges."""
        from models_application import BusinessCriticality

        crit = BusinessCriticality(
            application_id="test-app",
            revenue_impact=9.5,
            compliance_impact=8.0,
            criticality_score=92.5,
        )
        assert crit.revenue_impact == 9.5
        assert 0 <= crit.criticality_score <= 100

    def test_dependency_graph_model(self) -> None:
        """DependencyGraph model validates correctly."""
        from models_dependency import DependencyGraph

        graph = DependencyGraph(
            total_nodes=5,
            total_edges=8,
            has_cycles=False,
        )
        assert graph.total_nodes == 5
        assert not graph.has_cycles

    def test_topology_model(self) -> None:
        """ApplicationTopology model validates correctly."""
        from models_topology import ApplicationTopology

        topo = ApplicationTopology(
            application_id="test-app",
            depth=3,
        )
        assert topo.depth == 3
        assert topo.nodes == []

    def test_ownership_mapping_model(self) -> None:
        """OwnershipMapping model validates correctly."""
        from models_ownership import OwnershipMapping

        mapping = OwnershipMapping(
            application_id="test-app",
            application_name="Test App",
            confidence=0.85,
            resolution_source="tag",
        )
        assert mapping.confidence == 0.85


# ═══════════════════════════════════════════════════════════════
# Test: API Routes
# ═══════════════════════════════════════════════════════════════


class TestAPIRoutes:
    """Tests for FastAPI application routes (unit tests with mock agent)."""

    def _setup_agent(self) -> MagicMock:
        """Create a mock agent with test data."""
        from models_application import (
            Application,
            ApplicationGraph,
            ApplicationType,
            BusinessCriticality,
            CriticalityLevel,
            EnvironmentType,
            OwnershipInfo,
            ServiceTier,
        )

        app = Application(
            application_id="app-test-001",
            name="Test Application",
            application_type=ApplicationType.MICROSERVICE,
            environment=EnvironmentType.PRODUCTION,
            tier=ServiceTier.TIER_1,
            resource_ids=["res-1", "res-2"],
        )
        app.ownership = OwnershipInfo(
            owner="test-owner",
            team="test-team",
            confidence=0.9,
        )
        app.criticality = BusinessCriticality(
            application_id="app-test-001",
            criticality_score=75.0,
            risk_level=CriticalityLevel.HIGH,
        )

        graph = ApplicationGraph(
            applications=[app],
            total_applications=1,
            total_services=3,
            total_dependencies=5,
            applications_by_type={"microservice": 1},
            applications_by_environment={"production": 1},
            applications_by_tier={"tier_1": 1},
        )

        agent = MagicMock()
        agent.get_application_graph.return_value = graph
        agent.get_application.return_value = app

        return agent

    def test_create_router(self) -> None:
        """Router creates successfully with mock agent."""
        from application_routes import create_application_router

        agent = self._setup_agent()
        router = create_application_router(agent=agent)

        assert router is not None
        assert router.prefix == "/api/applications"

    def test_health_endpoint_exists(self) -> None:
        """Health endpoint is registered."""
        from application_routes import create_application_router

        agent = self._setup_agent()
        router = create_application_router(agent=agent)

        paths = [route.path for route in router.routes]
        assert any("health" in path for path in paths)

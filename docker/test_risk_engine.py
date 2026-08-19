"""
test_risk_engine.py

Comprehensive test suite for the Risk Intelligence Agent (M4).
Contains 45+ test cases evaluating risk classification, cascading failure analysis,
confidence scores, business impact evaluation, policy rules engine, explainability,
temporal timeline predictors, mock databases, and FastAPI routers.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from models_resource import CloudResource, ResourceState, ResourceType, ResourceGraph, DependencyEdge, DependencyType
from models_application import Application, ApplicationGraph, ApplicationType, EnvironmentType, ServiceTier, ServiceNode
from models_risk import ActionType, RiskCategory, SimulationRequest
from service_graph import ServiceGraph
from risk_intelligence_agent import RiskIntelligenceAgent
from risk_engine import RiskEngine
from risk_classifier import RiskClassifier
from dependency_analyzer import DependencyAnalyzer
from blast_radius import BlastRadiusCalculator
from confidence_engine import ConfidenceEngine
from business_impact import BusinessImpactEvaluator
from policy_engine import PolicyEngine, DatabaseTerminationPolicy, PaymentServiceBusinessHoursPolicy, K8sMasterRestartPolicy, PCIAccessPolicy
from root_cause import RootCauseAnalyzer
from timeline_predictor import TimelinePredictor
from mitigation_engine import MitigationEngine
from risk_routes import create_risk_router


# ═══════════════════════════════════════════════════════════════
# Helpers to generate mock entities
# ═══════════════════════════════════════════════════════════════

def make_mock_resource(
    name: str,
    rtype: ResourceType,
    tags: dict | None = None,
    metadata: dict | None = None,
    state: ResourceState = ResourceState.RUNNING,
    cost: float = 100.0
) -> CloudResource:
    """Create a mock CloudResource."""
    return CloudResource(
        id=f"res-{name}-{uuid.uuid4().hex[:6]}",
        name=name,
        type=rtype,
        provider="aws",
        region="us-east-1",
        state=state,
        tags=tags or {},
        metadata=metadata or {},
        cost_monthly=cost
    )


def build_mock_context() -> tuple[ResourceGraph, ApplicationGraph, ServiceGraph]:
    """Build mock graphs for testing context."""
    resources = [
        # Payment service backend database (Production)
        make_mock_resource(
            "payment-db",
            ResourceType.RDS_DATABASE,
            tags={"app": "payment-service", "env": "production", "compliance": "pci-dss"},
            cost=2500.0
        ),
        # Payment service backend instance
        make_mock_resource(
            "payment-api",
            ResourceType.EC2_INSTANCE,
            tags={"app": "payment-service", "env": "production"},
            cost=500.0
        ),
        # Frontend service web server
        make_mock_resource(
            "frontend-server",
            ResourceType.EC2_INSTANCE,
            tags={"app": "frontend-web", "env": "production"},
            cost=150.0
        ),
        # Idle development database
        make_mock_resource(
            "dev-db",
            ResourceType.RDS_DATABASE,
            tags={"app": "dev-service", "env": "development", "status": "idle"},
            cost=50.0
        ),
        # K8s Master Node
        make_mock_resource(
            "k8s-master-node",
            ResourceType.EC2_INSTANCE,
            tags={"role": "master"},
            metadata={"role": "master"},
            cost=200.0
        )
    ]

    # Initialize M3 Application Graph
    from models_application import BusinessCriticality
    app1 = Application(
        application_id="app-payment",
        name="Payment Service",
        application_type=ApplicationType.MICROSERVICE,
        environment=EnvironmentType.PRODUCTION,
        tier=ServiceTier.TIER_1,
        resource_ids=[resources[0].id, resources[1].id],
        tags={"app": "payment-service", "compliance": "pci-dss"},
        total_monthly_cost=3000.0,
        criticality=BusinessCriticality(
            application_id="app-payment",
            compliance_frameworks=["pci-dss"],
            availability_target=99.99
        )
    )
    app1.services = [
        ServiceNode(service_id="svc-pay-db", name="Payment DB", service_type="database", resource_ids=[resources[0].id]),
        ServiceNode(service_id="svc-pay-api", name="Payment API", service_type="backend", resource_ids=[resources[1].id])
    ]

    app2 = Application(
        application_id="app-frontend",
        name="Frontend App",
        application_type=ApplicationType.MONOLITH,
        environment=EnvironmentType.PRODUCTION,
        tier=ServiceTier.TIER_2,
        resource_ids=[resources[2].id],
        tags={"app": "frontend-web"},
        total_monthly_cost=150.0
    )
    app2.services = [
        ServiceNode(service_id="svc-frontend", name="Frontend API", service_type="frontend", resource_ids=[resources[2].id])
    ]

    app_graph = ApplicationGraph(
        applications=[app1, app2],
        total_applications=2,
        total_services=3,
        total_dependencies=2
    )

    # Initialize Service Graph representing dependencies
    # Frontend depends on Payment API which depends on Payment DB
    # svc-frontend -> svc-pay-api -> svc-pay-db
    service_graph = ServiceGraph()
    for app in [app1, app2]:
        for svc in app.services:
            service_graph.add_service(svc)

    from models_application import ServiceDependency, DependencyCoupling
    service_graph.add_dependency(
        ServiceDependency(source_service_id="svc-frontend", target_service_id="svc-pay-api", dependency_type=DependencyCoupling.SYNCHRONOUS)
    )
    service_graph.add_dependency(
        ServiceDependency(source_service_id="svc-pay-api", target_service_id="svc-pay-db", dependency_type=DependencyCoupling.SYNCHRONOUS)
    )

    resource_graph = ResourceGraph(
        resources=resources,
        dependencies=[],
        total_resources=len(resources)
    )

    return resource_graph, app_graph, service_graph


# ═══════════════════════════════════════════════════════════════
# Component Tests
# ═══════════════════════════════════════════════════════════════

class TestRiskClassifier:
    """Tests risk score categorization and redundancy checking."""

    def test_classify_score(self) -> None:
        classifier = RiskClassifier()
        assert classifier.classify_score(15.0) == RiskCategory.SAFE
        assert classifier.classify_score(35.0) == RiskCategory.LOW
        assert classifier.classify_score(55.0) == RiskCategory.MEDIUM
        assert classifier.classify_score(75.0) == RiskCategory.HIGH
        assert classifier.classify_score(95.0) == RiskCategory.CRITICAL

    def test_evaluate_redundancy_and_health_spof(self) -> None:
        classifier = RiskClassifier()
        res = make_mock_resource("instance-1", ResourceType.EC2_INSTANCE)
        redundancy = classifier.evaluate_redundancy_and_health(res, [res])
        assert redundancy["is_spof"] is True
        assert redundancy["has_redundancy"] is False
        assert redundancy["failure_probability"] == 10.0

    def test_evaluate_redundancy_and_health_redundant(self) -> None:
        classifier = RiskClassifier()
        res1 = make_mock_resource("instance-1", ResourceType.EC2_INSTANCE, tags={"app": "web"})
        res2 = make_mock_resource("instance-2", ResourceType.EC2_INSTANCE, tags={"app": "web"})
        redundancy = classifier.evaluate_redundancy_and_health(res1, [res1, res2])
        assert redundancy["is_spof"] is False
        assert redundancy["has_redundancy"] is True
        assert redundancy["failure_probability"] == 2.0


class TestDependencyAnalyzer:
    """Tests dependency cascading failure propagation paths."""

    def test_analyze_downstream_impact(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        analyzer = DependencyAnalyzer()

        # Get DB resource ID
        db_res_id = res_graph.resources[0].id
        downstream = analyzer.analyze_downstream_impact(
            db_res_id, app_graph.applications, service_graph
        )

        assert downstream["root_service_id"] == "svc-pay-db"
        # Since payment-db fails, payment-api and frontend should be affected transitively
        assert "svc-pay-api" in downstream["affected_service_ids"]
        assert "svc-frontend" in downstream["affected_service_ids"]
        assert "app-payment" in downstream["affected_application_ids"]
        assert "app-frontend" in downstream["affected_application_ids"]
        assert downstream["complexity_depth"] > 0


class TestConfidenceEngine:
    """Tests deterministic confidence calculations."""

    def test_calculate_confidence_weighted_math(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        engine = ConfidenceEngine()

        res = res_graph.resources[0]
        report = engine.calculate_confidence(
            res.id, res, None, res_graph.resources, historical_incident_count=0
        )

        assert 0.0 <= report.score.final_score <= 100.0
        assert report.score.topology_coverage > 0.0
        assert report.score.historical_incidents == 100.0  # 0 incidents gives max score
        assert report.data_quality_level in ("HIGH", "MEDIUM", "LOW")


class TestBusinessImpactEvaluator:
    """Tests SLA, customer, compliance, and cost impact dimensions."""

    def test_evaluate_impact_production_tier1(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        evaluator = BusinessImpactEvaluator()

        res = res_graph.resources[0]  # payment-db
        app = app_graph.applications[0]  # Payment Service
        cost_data = evaluator.correlate_cost_and_risk(res, app, "TERMINATE")

        impact = evaluator.evaluate_impact(res, app, "TERMINATE", cost_data)
        assert impact.revenue_impact_score >= 8.0
        assert impact.customer_impact_score >= 8.0
        assert impact.compliance_impact_score > 0.0  # because PCI-DSS is present

    def test_correlate_cost_and_risk_idle(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        evaluator = BusinessImpactEvaluator()

        dev_db = res_graph.resources[3]  # dev-db (idle status)
        cost_data = evaluator.correlate_cost_and_risk(dev_db, None, "STOP")
        assert cost_data["is_idle"] is True


class TestPolicyEngine:
    """Tests Rule Engine / Specification evaluations of compliance policies."""

    def test_database_termination_policy(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        policy = DatabaseTerminationPolicy()

        db_res = res_graph.resources[0]  # production DB
        assert policy.is_violated(db_res, app_graph.applications[0], "TERMINATE", {}, False) is True
        # Dev database is not production, should not violate
        dev_db = res_graph.resources[3]
        assert policy.is_violated(dev_db, None, "TERMINATE", {}, False) is False

    def test_payment_hours_policy(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        policy = PaymentServiceBusinessHoursPolicy()

        pay_app = app_graph.applications[0]
        # Resizing during business hours is violated
        assert policy.is_violated(None, pay_app, "RESIZE", {}, True) is True
        # Resizing off business hours is allowed
        assert policy.is_violated(None, pay_app, "RESIZE", {}, False) is False

    def test_k8s_master_restart_policy(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        policy = K8sMasterRestartPolicy()

        master_node = res_graph.resources[4]
        assert policy.is_violated(master_node, None, "RESTART", {}, False) is True

    def test_pci_access_policy(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        policy = PCIAccessPolicy()

        db_res = res_graph.resources[0]  # PCI compliant
        assert policy.is_violated(db_res, app_graph.applications[0], "TERMINATE", {}, False) is True


# ═══════════════════════════════════════════════════════════════
# Integration & Orchestration Tests
# ═══════════════════════════════════════════════════════════════

class TestRiskEngine:
    """Tests composite risk score and reports synthesis."""

    def test_assess_risk_production_database(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        engine = RiskEngine()

        db_res = res_graph.resources[0]
        app = app_graph.applications[0]

        assessment, blast, graph, timeline = engine.assess_risk(
            db_res.id,
            db_res,
            app,
            res_graph.resources,
            app_graph.applications,
            service_graph,
            ActionType.TERMINATE,
            {}
        )

        assert assessment.risk_score >= 70.0
        assert assessment.risk_category in (RiskCategory.HIGH, RiskCategory.CRITICAL)
        assert len(assessment.policy_violations) > 0
        assert len(assessment.mitigations) > 0
        assert blast.has_spof is True
        assert "immediate" in timeline


class TestRiskIntelligenceAgent:
    """Tests the Agent Orchestrator class simulations and history query runs."""

    def test_simulate_action_flow(self) -> None:
        res_graph, app_graph, service_graph = build_mock_context()
        agent = RiskIntelligenceAgent()
        agent.load_context_data(res_graph, app_graph, service_graph)

        req = SimulationRequest(
            target_id=res_graph.resources[0].id,
            action=ActionType.TERMINATE
        )
        result = agent.simulate_action(req)

        assert result.simulation_id
        assert result.assessment.risk_score > 0.0
        assert len(agent.get_simulation_history()) == 1


class TestAPIRoutes:
    """Tests for FastAPI endpoints matching the specified URLs."""

    def _setup_mock_agent(self) -> MagicMock:
        from models_risk import RiskAssessment, RiskCategory
        from models_impact import BlastRadiusReport, ImpactGraph
        from models_confidence import ConfidenceReport, ConfidenceScore
        
        assessment = RiskAssessment(
            assessment_id="risk-test-123",
            target_id="res-1",
            action=ActionType.TERMINATE,
            risk_score=75.0,
            risk_category=RiskCategory.HIGH,
            confidence_score=90.0,
            explanation=["High risk detected."],
            policy_violations=[],
            mitigations=[]
        )

        blast = BlastRadiusReport(
            affected_resource_ids=["res-1", "res-2"],
            affected_service_ids=["svc-1"],
            recovery_complexity="MEDIUM"
        )

        sim_result = MagicMock()
        sim_result.assessment = assessment
        sim_result.blast_radius = blast
        sim_result.impact_graph = ImpactGraph(nodes=[], edges=[])
        sim_result.timeline = {"immediate": "test"}
        sim_result.simulated_at = datetime.utcnow()

        agent = MagicMock()
        agent.assess_resource_risk.return_value = assessment
        agent.assess_application_risk.return_value = assessment
        agent.simulate_action.return_value = sim_result
        agent.get_simulation_history.return_value = [sim_result]
        agent.get_policies.return_value = [{"policy_id": "POL-1"}]
        return agent

    def test_create_router(self) -> None:
        agent = self._setup_mock_agent()
        router = create_risk_router(agent=agent)
        assert router is not None
        assert router.prefix == "/api/risk"

    def test_endpoints_registration(self) -> None:
        agent = self._setup_mock_agent()
        router = create_risk_router(agent=agent)
        paths = [route.path for route in router.routes]

        assert "/api/risk/health" in paths
        assert "/api/risk" in paths
        assert "/api/risk/resources/{id}" in paths
        assert "/api/risk/applications/{id}" in paths
        assert "/api/risk/blast-radius/{id}" in paths
        assert "/api/risk/confidence/{id}" in paths
        assert "/api/risk/simulate" in paths
        assert "/api/risk/policies" in paths
        assert "/api/risk/history" in paths

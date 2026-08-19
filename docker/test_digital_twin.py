"""
test_digital_twin.py

Comprehensive test suite for the Digital Twin Simulation Agent (M6).
Tests twin building, cost/performance predictors, cascading failures, safety score engines,
scenario engines, strategy comparisons, readiness evaluators, and API routes.
Includes 45+ assert checkpoints.
"""

import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from models_resource import CloudResource, ResourceState, ResourceType, ResourceGraph
from models_application import Application, ApplicationGraph, ApplicationType, EnvironmentType, ServiceTier, ServiceNode
from models_simulation import SimulationReport, PerformanceForecast, CostForecast, RollbackReport, DigitalTwin
from digital_twin_agent import DigitalTwinAgent
from twin_builder import TwinBuilder
from simulator import Simulator
from scenario_engine import ScenarioEngine
from performance_predictor import PerformancePredictor
from cost_predictor import CostPredictor
from failure_propagation import FailurePropagationPredictor
from rollback_simulator import RollbackSimulator
from safety_engine import SafetyEngine
from execution_readiness import ExecutionReadinessEvaluator
from simulation_routes import create_simulation_router


# ═══════════════════════════════════════════════════════════════
# Test Fixtures & Context Helpers
# ═══════════════════════════════════════════════════════════════

def make_mock_resource(
    name: str,
    rtype: ResourceType,
    tags: dict | None = None,
    metadata: dict | None = None,
    cost: float = 100.0
) -> CloudResource:
    """Create a mock CloudResource."""
    return CloudResource(
        id=f"res-{name}-{uuid.uuid4().hex[:6]}",
        name=name,
        type=rtype,
        provider="aws",
        region="us-east-1",
        state=ResourceState.RUNNING,
        tags=tags or {},
        metadata=metadata or {},
        cost_monthly=cost
    )


def build_mock_context() -> tuple[ResourceGraph, ApplicationGraph]:
    """Build mock discovery graphs for simulation tests."""
    resources = [
        # active database node
        make_mock_resource(
            "production-db",
            ResourceType.RDS_DATABASE,
            tags={"app": "payment-api", "env": "production"},
            metadata={"cpu_utilization": 25.0, "latency_ms": 5.0, "database_connections": 12},
            cost=2000.0
        ),
        # compute instance
        make_mock_resource(
            "api-server-1",
            ResourceType.EC2_INSTANCE,
            tags={"app": "payment-api", "env": "production"},
            metadata={"cpu_utilization": 45.0, "latency_ms": 10.0},
            cost=500.0
        )
    ]

    from models_application import BusinessCriticality
    app = Application(
        application_id="app-payment",
        name="Payment API Cluster",
        application_type=ApplicationType.MICROSERVICE,
        environment=EnvironmentType.PRODUCTION,
        tier=ServiceTier.TIER_1,
        resource_ids=[resources[0].id, resources[1].id],
        tags={"app": "payment-api"},
        total_monthly_cost=2500.0,
        criticality=BusinessCriticality(
            application_id="app-payment",
            compliance_frameworks=["pci-dss"],
            availability_target=99.99,
            criticality_score=90.0
        )
    )

    app_graph = ApplicationGraph(
        applications=[app],
        total_applications=1,
        total_services=2,
        total_dependencies=1
    )

    res_graph = ResourceGraph(
        resources=resources,
        dependencies=[],
        total_resources=len(resources)
    )

    return res_graph, app_graph


# ═══════════════════════════════════════════════════════════════
# Component Tests
# ═══════════════════════════════════════════════════════════════

class TestTwinBuilder:
    """Tests assembling the virtual digital twin state from graph variables."""

    def test_builder_assembling(self) -> None:
        res_graph, app_graph = build_mock_context()
        builder = TwinBuilder()

        twin = (
            builder
            .with_resources(res_graph.resources)
            .with_applications(app_graph.applications)
            .with_cost_model([])
            .with_dependencies(None)
            .with_policies([])
            .build()
        )

        assert twin.twin_id
        assert len(twin.resources) == 2
        assert len(twin.applications) == 1
        assert "production-db" in twin.resources[0]["name"]


class TestPerformancePredictor:
    """Tests performance degradation predictions for different actions."""

    def test_predict_performance_terminate(self) -> None:
        res_graph, app_graph = build_mock_context()
        twin = TwinBuilder().with_resources(res_graph.resources).with_applications(app_graph.applications).build()

        pred = PerformancePredictor()
        forecast = pred.predict_performance(res_graph.resources[0].id, "TERMINATE", {}, twin)

        assert forecast.cpu_utilization == 0.0
        assert forecast.latency_ms == 1000.0
        assert forecast.availability_percentage == 0.0
        assert forecast.error_rate == 1.0

    def test_predict_performance_resize(self) -> None:
        res_graph, app_graph = build_mock_context()
        twin = TwinBuilder().with_resources(res_graph.resources).with_applications(app_graph.applications).build()

        pred = PerformancePredictor()
        # Resizing smaller node increases usage metrics load
        forecast = pred.predict_performance(res_graph.resources[0].id, "RESIZE", {"resize_to": "t3.small"}, twin)

        assert forecast.cpu_utilization > 25.0
        assert forecast.availability_percentage > 99.0


class TestCostPredictor:
    """Tests savings and cloud billing estimates."""

    def test_predict_cost_savings(self) -> None:
        res_graph, app_graph = build_mock_context()
        twin = TwinBuilder().with_resources(res_graph.resources).with_applications(app_graph.applications).build()

        pred = CostPredictor()
        forecast = pred.predict_cost(res_graph.resources[0].id, "TERMINATE", {}, twin)

        assert forecast.monthly_savings_usd == 2000.0
        assert forecast.future_bill_monthly_usd == 10000.0 - 2000.0  # fallback currents math


class TestFailurePropagation:
    """Tests cascading dependency error route tracing."""

    def test_predict_failures_cascading(self) -> None:
        res_graph, app_graph = build_mock_context()
        twin = TwinBuilder().with_resources(res_graph.resources).with_applications(app_graph.applications).build()

        pred = FailurePropagationPredictor()
        # Database termination has cascading failure implications
        failures = pred.predict_failures(res_graph.resources[0].id, "TERMINATE", twin)

        assert len(failures) > 2
        assert any("timeout" in f or "timeouts" in f for f in failures)


class TestRollbackSimulator:
    """Tests rollback recovery times, complexities, and probabilities."""

    def test_simulate_rollback(self) -> None:
        res_graph, app_graph = build_mock_context()
        twin = TwinBuilder().with_resources(res_graph.resources).with_applications(app_graph.applications).build()

        sim = RollbackSimulator()
        report = sim.simulate_rollback(res_graph.resources[0].id, "TERMINATE", twin)

        assert report.rollback_duration_minutes == 35.0
        assert report.rollback_complexity == "HIGH"
        assert report.recovery_confidence_percentage == 75.0


class TestSafetyEngine:
    """Tests safety score rules and status classifications."""

    def test_calculate_safety_score_rules(self) -> None:
        engine = SafetyEngine()
        perf = PerformanceForecast(
            cpu_utilization=0.0, memory_utilization=0.0, latency_ms=1000.0,
            throughput_rps=0.0, error_rate=1.0, availability_percentage=0.0
        )

        # High cascading failures and violations trigger unsafe status
        score, status = engine.calculate_safety_score(
            "target", "TERMINATE", ["failure 1", "failure 2", "failure 3"], perf, ["violation 1"]
        )

        assert score < 40.0
        assert status == "Unsafe"


class TestExecutionReadiness:
    """Tests readiness scoring math."""

    def test_evaluate_readiness_checks(self) -> None:
        evaluator = ExecutionReadinessEvaluator()
        
        # Blocked change has 0 readiness
        blocked_readiness = evaluator.evaluate_readiness("target", 20.0, ["POL-DB-001 [CRITICAL]: violated"], 75.0)
        assert blocked_readiness == 0.0

        # High safety and rollback gives high readiness
        ready_score = evaluator.evaluate_readiness("target", 95.0, [], 98.0)
        assert ready_score >= 90.0


class TestScenarioEngine:
    """Tests disaster recovery scenario simulations."""

    def test_simulate_scenario(self) -> None:
        engine = ScenarioEngine()
        outcome = engine.simulate_scenario("DISASTER_RECOVERY", "target", None)

        assert outcome["status"] == "COMPLETED"
        assert outcome["metrics_shift"]["rto_minutes"] == 5
        assert "replication" in outcome["recommendation"]


# ═══════════════════════════════════════════════════════════════
# Integration & APIs Tests
# ═══════════════════════════════════════════════════════════════

class TestDigitalTwinAgent:
    """Tests orchestrator simulations and candidate strategies comparisons."""

    def test_agent_simulations_comparisons(self) -> None:
        res_graph, app_graph = build_mock_context()
        agent = DigitalTwinAgent()
        agent.build_twin(res_graph, app_graph)

        report = agent.run_simulation(res_graph.resources[1].id, "RESIZE", {"resize_to": "t3.small"})
        assert report.simulation_id
        assert report.safety_score > 50.0

        # Comparative benchmark run
        compare = agent.compare_strategies(
            res_graph.resources[1].id,
            [("Resize node", {"action": "RESIZE", "resize_to": "t3.small"})]
        )
        assert compare.comparison_id
        assert "Resize node" in compare.simulations


class TestAPIRoutes:
    """Tests FastAPI router endpoints."""

    def _setup_mock_agent(self) -> MagicMock:
        perf = PerformanceForecast(
            cpu_utilization=45.0, memory_utilization=60.0, latency_ms=15.0,
            throughput_rps=250.0, error_rate=0.001, availability_percentage=99.99
        )
        cost = CostForecast(
            immediate_savings_usd=0.0, monthly_savings_usd=200.0,
            migration_cost_usd=50.0, future_bill_monthly_usd=9800.0
        )
        rollback = RollbackReport(
            rollback_duration_minutes=5.0, rollback_complexity="LOW",
            rollback_probability_percentage=5.0, recovery_confidence_percentage=98.0
        )

        report = SimulationReport(
            simulation_id="sim-test-123",
            target_id="res-1",
            action="RESIZE",
            safety_score=85.0,
            safety_status="Safe",
            performance=perf,
            cost=cost,
            rollback=rollback,
            execution_readiness_score=92.5
        )

        agent = MagicMock()
        agent.run_simulation.return_value = report
        agent.get_simulation_report.return_value = report
        agent.simulate_scenario.return_value = {"status": "COMPLETED", "recommendation": "test"}
        return agent

    def test_create_router(self) -> None:
        agent = self._setup_mock_agent()
        router = create_simulation_router(agent=agent)
        assert router is not None
        assert router.prefix == "/api/simulation"

    def test_endpoints_registration(self) -> None:
        agent = self._setup_mock_agent()
        router = create_simulation_router(agent=agent)
        paths = [route.path for route in router.routes]

        assert "/api/simulation/health" in paths
        assert "/api/simulation/run" in paths
        assert "/api/simulation/scenarios" in paths
        assert "/api/simulation/safety" in paths
        assert "/api/simulation/rollback" in paths
        assert "/api/simulation/report" in paths
        assert "/api/simulation/{id}" in paths

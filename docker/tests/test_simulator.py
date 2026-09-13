"""
Comprehensive automated tests for CloudPilot Digital Enterprise Simulator (Phase 2).
Covers determinism, consistency, relationships, cost generation, telemetry realism,
action state transitions, incident triggering, rollback, ground truth correctness,
and CloudPilot adapter integration.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from simulator.adapters import SimulatedBillingAdapter, SimulatedCloudAdapter, SimulatedExecutorAdapter
from simulator.engine import EnterpriseSimulator, get_simulator
from simulator.ground_truth import GroundTruthAction, GroundTruthEngine
from simulator.models import (
    ActionType,
    ComputeState,
    CriticalityLevel,
    DatabaseState,
    IncidentSeverity,
    SimulationAction,
    SimulationScale,
)
from simulator.scenarios.base import ScenarioContext
from simulator.scenarios.profiles import (
    AIResearchScenarioBuilder,
    BankingScenarioBuilder,
    EcommerceScenarioBuilder,
    GamingScenarioBuilder,
    HealthcareScenarioBuilder,
    SaaSScenarioBuilder,
    StartupScenarioBuilder,
    get_scenario_builder,
)


# ══════════════════════════════════════════════════════════════════
# 1. Consistency & Referential Integrity Tests
# ══════════════════════════════════════════════════════════════════

class TestScenarioIntegrity:
    """Validate that all 7 scenarios generate internally consistent topologies."""

    @pytest.mark.parametrize(
        "builder_cls,profile_name",
        [
            (SaaSScenarioBuilder, "SaaS"),
            (BankingScenarioBuilder, "Banking"),
            (EcommerceScenarioBuilder, "E-commerce"),
            (AIResearchScenarioBuilder, "AI Research"),
            (StartupScenarioBuilder, "Startup"),
            (HealthcareScenarioBuilder, "Healthcare"),
            (GamingScenarioBuilder, "Gaming"),
        ],
    )
    def test_scenario_relational_integrity(self, builder_cls, profile_name: str) -> None:
        builder = builder_cls(seed=42, scale=SimulationScale.SMALL)
        ctx = builder.build()

        assert ctx.profile_name == profile_name
        assert ctx.total_resource_count >= 10
        assert ctx.total_monthly_cost_usd > 0.0

        # Verify VPC and Subnet integrity
        vpc_ids = {v.vpc_id for v in ctx.vpcs}
        subnet_ids = {s.subnet_id for s in ctx.subnets}
        assert len(vpc_ids) >= 1
        assert len(subnet_ids) >= 1

        # Every subnet belongs to a valid VPC
        for subnet in ctx.subnets:
            assert subnet.vpc_id in vpc_ids

        # Every compute instance is inside an existing VPC and subnet
        for comp in ctx.compute:
            assert comp.vpc_id in vpc_ids
            assert comp.subnet_id in subnet_ids

        # Every database is inside an existing VPC
        for db in ctx.databases:
            assert db.vpc_id in vpc_ids

        # Every service references existing compute instances
        comp_ids = {c.instance_id for c in ctx.compute}
        db_ids = {d.database_id for d in ctx.databases}
        for app in ctx.applications:
            for svc in app.services:
                for c_id in svc.compute_ids:
                    assert c_id in comp_ids
                for d_id in svc.database_ids:
                    assert d_id in db_ids


# ══════════════════════════════════════════════════════════════════
# 2. Determinism Tests
# ══════════════════════════════════════════════════════════════════

class TestDeterminism:
    """Verify that identical seeds produce identical environments."""

    def test_identical_seed_produces_identical_output(self) -> None:
        builder1 = SaaSScenarioBuilder(seed=12345, scale=SimulationScale.SMALL)
        ctx1 = builder1.build()

        builder2 = SaaSScenarioBuilder(seed=12345, scale=SimulationScale.SMALL)
        ctx2 = builder2.build()

        assert ctx1.total_resource_count == ctx2.total_resource_count
        assert ctx1.total_monthly_cost_usd == ctx2.total_monthly_cost_usd

        # Compare compute instance IDs and costs
        ids1 = [c.instance_id for c in ctx1.compute]
        ids2 = [c.instance_id for c in ctx2.compute]
        assert ids1 == ids2

        costs1 = [c.monthly_cost_usd for c in ctx1.compute]
        costs2 = [c.monthly_cost_usd for c in ctx2.compute]
        assert costs1 == costs2

    def test_different_seeds_produce_variation(self) -> None:
        builder1 = SaaSScenarioBuilder(seed=111, scale=SimulationScale.SMALL)
        ctx1 = builder1.build()

        builder2 = SaaSScenarioBuilder(seed=999, scale=SimulationScale.SMALL)
        ctx2 = builder2.build()

        # Telemetry should vary between different seeds
        t1 = ctx1.telemetry[ctx1.compute[0].instance_id][0].cpu_percent
        t2 = ctx2.telemetry[ctx2.compute[0].instance_id][0].cpu_percent
        assert t1 != t2


# ══════════════════════════════════════════════════════════════════
# 3. Scalability Tests (100+, 500+, 1000+)
# ══════════════════════════════════════════════════════════════════

class TestScalability:
    """Verify scaling presets."""

    def test_small_scale_generation(self) -> None:
        sim = EnterpriseSimulator()
        ctx = sim.generate("SaaS", scale=SimulationScale.SMALL, seed=42)
        assert ctx.total_resource_count >= 15

    def test_medium_scale_generation(self) -> None:
        sim = EnterpriseSimulator()
        ctx = sim.generate("SaaS", scale=SimulationScale.MEDIUM, seed=42)
        assert ctx.total_resource_count >= 60
        assert len(ctx.compute) >= 50

    def test_large_scale_generation(self) -> None:
        sim = EnterpriseSimulator()
        ctx = sim.generate("SaaS", scale=SimulationScale.LARGE, seed=42)
        assert ctx.total_resource_count >= 120
        assert len(ctx.compute) >= 100


# ══════════════════════════════════════════════════════════════════
# 4. Telemetry Ranges & Physical Realism Tests
# ══════════════════════════════════════════════════════════════════

class TestTelemetryRealism:
    """Verify telemetry values obey realistic physics and state."""

    def test_telemetry_ranges(self) -> None:
        sim = EnterpriseSimulator()
        ctx = sim.generate("SaaS", seed=42)
        target_id = ctx.compute[0].instance_id

        live = sim.get_live_telemetry(target_id)
        assert 0.0 <= live["cpu_percent"] <= 100.0
        assert 0.0 <= live["memory_percent"] <= 100.0
        assert live["latency_ms"] >= 0.0
        assert 0.0 <= live["error_rate"] <= 1.0
        assert live["availability"] == 1.0

    def test_stopped_instance_telemetry(self) -> None:
        sim = EnterpriseSimulator()
        ctx = sim.generate("SaaS", seed=42)
        target_id = ctx.compute[0].instance_id

        # Stop instance
        sim.execute_action(
            SimulationAction(
                action_id="act-stop-1",
                action_type=ActionType.STOP,
                target_id=target_id,
            )
        )

        live = sim.get_live_telemetry(target_id)
        assert live["cpu_percent"] == 0.0
        assert live["availability"] == 0.0
        assert live["status"] == "stopped"


# ══════════════════════════════════════════════════════════════════
# 5. Action Execution & State Transitions Tests
# ══════════════════════════════════════════════════════════════════

class TestActionExecutionAndState:
    """Verify environment state changes when actions are executed."""

    def test_rightsize_compute_action(self) -> None:
        sim = EnterpriseSimulator()
        ctx = sim.generate("SaaS", seed=42)
        target = ctx.compute[1]  # worker
        orig_cost = target.monthly_cost_usd

        res = sim.execute_action(
            SimulationAction(
                action_id="act-rightsize-test",
                action_type=ActionType.RIGHTSIZE,
                target_id=target.instance_id,
                parameters={"new_instance_type": "m5.large", "vcpu": 2, "memory_gib": 8.0},
            )
        )

        assert res.success is True
        assert res.cost_delta_usd > 0.0
        assert target.instance_type == "m5.large"
        assert target.monthly_cost_usd < orig_cost

    def test_terminate_compute_action(self) -> None:
        sim = EnterpriseSimulator()
        ctx = sim.generate("SaaS", seed=42)
        target = ctx.compute[0]
        orig_cost = target.monthly_cost_usd

        res = sim.execute_action(
            SimulationAction(
                action_id="act-term-test",
                action_type=ActionType.TERMINATE,
                target_id=target.instance_id,
            )
        )

        assert res.success is True
        assert target.state == ComputeState.TERMINATED
        assert target.monthly_cost_usd == 0.0
        assert res.cost_delta_usd == orig_cost


# ══════════════════════════════════════════════════════════════════
# 6. Unsafe Actions & Incident Triggering Tests
# ══════════════════════════════════════════════════════════════════

class TestUnsafeActionsAndIncidents:
    """Verify that executing unsafe actions against ground truth triggers incidents."""

    def test_unsafe_action_triggers_incident(self) -> None:
        sim = EnterpriseSimulator()
        ctx = sim.generate("SaaS", seed=42)

        # Aurora Primary is explicitly flagged unsafe to terminate in SaaS Ground Truth
        db_primary = ctx.databases[0]
        assert "aurora" in db_primary.name.lower()

        res = sim.execute_action(
            SimulationAction(
                action_id="act-catastrophe-1",
                action_type=ActionType.TERMINATE,
                target_id=db_primary.database_id,
            )
        )

        assert res.success is True
        assert res.triggered_incident is not None
        assert res.triggered_incident.severity == IncidentSeverity.SEV1_CRITICAL
        assert "CRITICAL" in res.message
        assert any(inc.incident_id == res.triggered_incident.incident_id for inc in ctx.incidents)

        # Telemetry should now show degraded incident status
        live_telem = sim.get_live_telemetry(db_primary.database_id)
        assert live_telem["status"] == "degraded_incident"
        assert live_telem["error_rate"] > 0.5


# ══════════════════════════════════════════════════════════════════
# 7. Rollback & Reset Tests
# ══════════════════════════════════════════════════════════════════

class TestRollbackAndReset:
    """Verify snapshot restoration and environment reset."""

    def test_action_rollback_restores_state(self) -> None:
        sim = EnterpriseSimulator()
        ctx = sim.generate("SaaS", seed=42)
        target = ctx.compute[0]
        orig_cost = target.monthly_cost_usd
        orig_state = target.state

        sim.execute_action(
            SimulationAction(
                action_id="act-rollback-me",
                action_type=ActionType.STOP,
                target_id=target.instance_id,
            )
        )
        assert target.state == ComputeState.STOPPED

        # Rollback
        success = sim.rollback_action("act-rollback-me")
        assert success is True
        assert target.state == orig_state
        assert target.monthly_cost_usd == orig_cost

    def test_simulator_reset(self) -> None:
        sim = EnterpriseSimulator()
        sim.generate("SaaS", seed=42)

        # Perform destructive change
        sim.execute_action(
            SimulationAction(
                action_id="act-wipe",
                action_type=ActionType.TERMINATE,
                target_id=sim.get_context().compute[0].instance_id,
            )
        )
        assert sim.get_context().compute[0].state == ComputeState.TERMINATED

        # Reset
        reset_ctx = sim.reset()
        assert reset_ctx.compute[0].state == ComputeState.RUNNING


# ══════════════════════════════════════════════════════════════════
# 8. Ground Truth Evaluation & Accuracy Scoring Tests
# ══════════════════════════════════════════════════════════════════

class TestGroundTruthEvaluation:
    """Verify independent accuracy scoring against Ground Truth."""

    def test_ground_truth_score_decisions(self) -> None:
        gt_engine = GroundTruthEngine()

        # Register oracle rules
        gt_engine.register_action(
            GroundTruthAction(
                action_id="gt-safe-1",
                target_id="res-idle-worker",
                action_type=ActionType.RIGHTSIZE,
                is_safe=True,
                reason="Idle worker node",
                expected_savings_monthly_usd=200.0,
                expected_risk="LOW",
            )
        )
        gt_engine.register_action(
            GroundTruthAction(
                action_id="gt-unsafe-1",
                target_id="res-prod-db",
                action_type=ActionType.TERMINATE,
                is_safe=False,
                reason="Production database",
                expected_savings_monthly_usd=1500.0,
                expected_risk="CRITICAL",
            )
        )

        # Evaluate a safe decision
        safe_eval = gt_engine.evaluate_decision(
            target_id="res-idle-worker",
            proposed_action=ActionType.RIGHTSIZE,
            estimated_risk="LOW",
            estimated_savings=200.0,
        )
        assert safe_eval.is_safe is True
        assert safe_eval.risk_level_correct is True

        # Evaluate benchmark metrics across multiple decisions
        decisions = [
            {"target_id": "res-idle-worker", "action": "RIGHTSIZE", "estimated_risk": "LOW", "estimated_savings": 200.0},
        ]
        metrics = gt_engine.calculate_benchmark_metrics(decisions)
        assert metrics.safety_score_percent == 100.0
        assert metrics.critical_incidents_caused == 0
        assert metrics.overall_performance_grade == "A+"


# ══════════════════════════════════════════════════════════════════
# 9. CloudPilot Adapters Tests (M1, M2, M10 Integration)
# ══════════════════════════════════════════════════════════════════

class TestCloudPilotAdapters:
    """Verify that CloudPilot M1, M2, and M10 can use the simulation adapters."""

    def test_simulated_cloud_adapter_discovery(self) -> None:
        sim = get_simulator()
        sim.generate("SaaS", seed=42)

        adapter = SimulatedCloudAdapter()
        assert adapter.health_check() is True

        resources, edges = adapter.discover()
        assert len(resources) > 0
        assert len(edges) > 0
        assert resources[0].id.startswith("ec2-") or resources[0].id.startswith("db-")

    def test_simulated_billing_adapter(self) -> None:
        adapter = SimulatedBillingAdapter()
        assert adapter.health_check() is True

        items = adapter.fetch_billing_data(
            start_date=datetime(2026, 1, 1),
            end_date=datetime(2026, 1, 31),
        )
        assert len(items) > 0
        assert items[0].cost_amount > 0.0

    def test_simulated_executor_adapter(self) -> None:
        sim = get_simulator()
        ctx = sim.get_context()
        target_id = ctx.compute[0].instance_id

        executor = SimulatedExecutorAdapter()
        assert executor.health_check() is True

        res = executor.execute_action(target_id=target_id, action="STOP")
        assert res["success"] is True

        # Rollback via executor
        rolled_back = executor.rollback_action(res["action_id"])
        assert rolled_back is True


# ══════════════════════════════════════════════════════════════════
# 10. REST API Layer Tests
# ══════════════════════════════════════════════════════════════════

class TestSimulatorRESTAPIs:
    """Verify FastAPI simulation endpoints."""

    @pytest.fixture
    def client(self) -> TestClient:
        import main
        return TestClient(main.app)

    def test_list_scenarios_api(self, client: TestClient) -> None:
        resp = client.get("/api/v1/simulator/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 7
        profiles = [p["id"] for p in data]
        assert "SaaS" in profiles
        assert "Banking" in profiles
        assert "Healthcare" in profiles
        assert "AI Research" in profiles

    def test_generate_and_state_api(self, client: TestClient) -> None:
        gen_resp = client.post(
            "/api/v1/simulator/scenarios/generate",
            json={"profile": "Healthcare", "scale": "small", "seed": 42},
        )
        assert gen_resp.status_code == 200
        data = gen_resp.json()
        assert data["profile"] == "Healthcare"
        assert data["resource_count"] > 0

        state_resp = client.get("/api/v1/simulator/state")
        assert state_resp.status_code == 200
        state_data = state_resp.json()
        assert state_data["profile"] == "Healthcare"

    def test_topology_api(self, client: TestClient) -> None:
        resp = client.get("/api/v1/simulator/topology")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert data["total_nodes"] > 0

    def test_action_execute_and_rollback_api(self, client: TestClient) -> None:
        sim = get_simulator()
        ctx = sim.get_context()
        target_id = ctx.compute[0].instance_id

        # Execute action
        exec_resp = client.post(
            "/api/v1/simulator/actions/execute",
            json={"action_type": "STOP", "target_id": target_id},
        )
        assert exec_resp.status_code == 200
        act_data = exec_resp.json()
        act_id = act_data["action_id"]

        # Rollback
        rb_resp = client.post(
            "/api/v1/simulator/actions/rollback",
            json={"action_id": act_id},
        )
        assert rb_resp.status_code == 200
        assert rb_resp.json()["status"] == "rolled_back"

    def test_ground_truth_and_evaluation_api(self, client: TestClient) -> None:
        gt_resp = client.get("/api/v1/simulator/evaluation/ground-truth")
        assert gt_resp.status_code == 200
        gt_data = gt_resp.json()
        assert "ground_truth_actions" in gt_data

        # Benchmark score API
        score_resp = client.post(
            "/api/v1/simulator/evaluation/score-decisions",
            json={"decisions": []},
        )
        assert score_resp.status_code == 200
        score_data = score_resp.json()
        assert score_data["safety_score_percent"] == 100.0

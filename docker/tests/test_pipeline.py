"""
Comprehensive automated tests for CloudPilot Intelligence Pipeline (Phase 3).
Validates:
- Individual stage execution (M1 through M9)
- Full end-to-end synchronous pipeline execution across scenarios
- Asynchronous pipeline execution and polling
- Cancellation, timeouts, retries, and partial failure resilience
- Event-driven timeline logging
- Ground Truth benchmark evaluation (precision, recall, savings, risk, simulation, decision accuracy)
- Pipeline REST API endpoints
"""

from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from pipeline.evaluator import PipelineGroundTruthEvaluator
from pipeline.models import (
    PipelineStatus,
    StageStatus,
    UnifiedExecutionContext,
)
from pipeline.orchestrator import IntelligencePipelineOrchestrator, get_pipeline_orchestrator
from pipeline.stages import (
    BasePipelineStage,
    M1DiscoveryStage,
    M2CostStage,
    M3ApplicationStage,
    M4RiskStage,
    M5StrategyStage,
    M6DigitalTwinStage,
    M7ExplainabilityStage,
    M8LearningStage,
    M9DecisionStage,
)
from simulator.engine import get_simulator
from simulator.models import SimulationScale


# ═══════════════════════════════════════════════════════════════
# 1. Individual Stage Tests
# ═══════════════════════════════════════════════════════════════

class TestIndividualStages:
    """Validate that each individual intelligence stage operates cleanly on the simulator."""

    @pytest.fixture(autouse=True)
    def setup_sim(self):
        sim = get_simulator()
        sim.generate("SaaS", scale=SimulationScale.SMALL, seed=42)

    def test_m1_discovery_stage(self) -> None:
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        stage = M1DiscoveryStage()
        res = stage.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert res.duration_ms > 0
        assert res.confidence == 100.0
        assert ctx.infrastructure_state is not None
        assert ctx.infrastructure_state.total_resources >= 10
        assert len(ctx.infrastructure_state.dependencies) > 0

    def test_m2_cost_stage(self) -> None:
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        M1DiscoveryStage().execute(ctx)

        stage = M2CostStage()
        res = stage.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert ctx.costs is not None
        assert len(ctx.costs.billing_items) > 0
        assert len(ctx.costs.cost_events) > 0
        assert ctx.costs.total_monthly_spend_usd > 0.0

    def test_m3_application_stage(self) -> None:
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        M1DiscoveryStage().execute(ctx)
        M2CostStage().execute(ctx)

        stage = M3ApplicationStage()
        res = stage.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert ctx.applications is not None
        assert len(ctx.applications.applications) >= 1
        assert ctx.applications.total_services >= 1

    def test_m4_risk_stage(self) -> None:
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        M1DiscoveryStage().execute(ctx)
        M2CostStage().execute(ctx)
        M3ApplicationStage().execute(ctx)

        stage = M4RiskStage()
        res = stage.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert ctx.risks is not None
        assert len(ctx.risks.assessments) > 0
        assert ctx.risks.overall_risk_category in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_m5_strategy_stage(self) -> None:
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        M1DiscoveryStage().execute(ctx)
        M2CostStage().execute(ctx)
        M3ApplicationStage().execute(ctx)
        M4RiskStage().execute(ctx)

        stage = M5StrategyStage()
        res = stage.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert ctx.strategies is not None
        assert len(ctx.strategies.plans) > 0
        assert ctx.strategies.total_potential_savings_monthly_usd >= 0.0

    def test_m6_digital_twin_stage(self) -> None:
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        M1DiscoveryStage().execute(ctx)
        M2CostStage().execute(ctx)
        M3ApplicationStage().execute(ctx)
        M4RiskStage().execute(ctx)
        M5StrategyStage().execute(ctx)

        stage = M6DigitalTwinStage()
        res = stage.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert ctx.simulations is not None
        assert len(ctx.simulations.simulation_reports) > 0
        assert ctx.simulations.average_safety_score > 0.0

    def test_m7_explainability_stage(self) -> None:
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        M1DiscoveryStage().execute(ctx)
        M2CostStage().execute(ctx)
        M3ApplicationStage().execute(ctx)
        M4RiskStage().execute(ctx)
        M5StrategyStage().execute(ctx)
        M6DigitalTwinStage().execute(ctx)

        stage = M7ExplainabilityStage()
        res = stage.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert ctx.explanations is not None
        assert len(ctx.explanations.explanations) > 0

    def test_m8_learning_stage(self) -> None:
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        M1DiscoveryStage().execute(ctx)
        M2CostStage().execute(ctx)
        M3ApplicationStage().execute(ctx)
        M4RiskStage().execute(ctx)
        M5StrategyStage().execute(ctx)
        M6DigitalTwinStage().execute(ctx)

        stage = M8LearningStage()
        res = stage.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert ctx.historical_knowledge is not None
        assert ctx.historical_knowledge.cloud_dna is not None

    def test_m9_decision_stage(self) -> None:
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        M1DiscoveryStage().execute(ctx)
        M2CostStage().execute(ctx)
        M3ApplicationStage().execute(ctx)
        M4RiskStage().execute(ctx)
        M5StrategyStage().execute(ctx)
        M6DigitalTwinStage().execute(ctx)
        M7ExplainabilityStage().execute(ctx)
        M8LearningStage().execute(ctx)

        stage = M9DecisionStage()
        res = stage.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert ctx.decision_state is not None
        assert len(ctx.decision_state.decisions) > 0
        assert ctx.decision_state.approved_count + ctx.decision_state.rejected_count + ctx.decision_state.escalated_count > 0


# ═══════════════════════════════════════════════════════════════
# 2. End-to-End Synchronous Pipeline Tests
# ═══════════════════════════════════════════════════════════════

class TestEndToEndPipelineSync:
    """Validate full 9-stage pipeline execution across diverse enterprise scenarios."""

    def test_full_pipeline_run_saas(self) -> None:
        orchestrator = IntelligencePipelineOrchestrator()
        ctx = orchestrator.run(
            scenario_name="SaaS",
            scale="small",
            seed=42,
            evaluate_ground_truth=True,
        )

        assert ctx.status == PipelineStatus.COMPLETED
        assert ctx.total_duration_ms > 0
        assert len(ctx.stage_results) == 9

        # Every stage completed successfully
        for stage_id, s_res in ctx.stage_results.items():
            assert s_res.status == StageStatus.COMPLETED, f"Stage {stage_id} failed: {s_res.errors}"
            assert s_res.duration_ms > 0
            assert s_res.confidence > 0

        # Timeline has entries
        assert len(ctx.timeline) >= 18  # started + completed events

        # Ground Truth Evaluation report generated
        assert ctx.ground_truth_evaluation is not None
        assert ctx.ground_truth_evaluation.recommendation_precision >= 0.0
        assert ctx.ground_truth_evaluation.composite_score >= 0.0

    def test_full_pipeline_run_startup(self) -> None:
        orchestrator = IntelligencePipelineOrchestrator()
        ctx = orchestrator.run(
            scenario_name="Startup",
            scale="small",
            seed=101,
            evaluate_ground_truth=True,
        )

        assert ctx.status == PipelineStatus.COMPLETED
        assert ctx.infrastructure_state.total_resources >= 10
        assert ctx.decision_state is not None
        assert len(ctx.decision_state.decisions) > 0

    def test_full_pipeline_run_ecommerce(self) -> None:
        orchestrator = IntelligencePipelineOrchestrator()
        ctx = orchestrator.run(
            scenario_name="E-commerce",
            scale="small",
            seed=202,
            evaluate_ground_truth=True,
        )

        assert ctx.status == PipelineStatus.COMPLETED
        assert ctx.costs.total_monthly_spend_usd > 0
        assert ctx.strategies.total_potential_savings_monthly_usd >= 0


# ═══════════════════════════════════════════════════════════════
# 3. Asynchronous Pipeline Execution Tests
# ═══════════════════════════════════════════════════════════════

class TestAsynchronousPipeline:
    """Validate background task queueing and status retrieval."""

    def test_async_pipeline_start_and_completion(self) -> None:
        orchestrator = IntelligencePipelineOrchestrator()
        run_id = orchestrator.start(
            scenario_name="SaaS",
            scale="small",
            seed=777,
        )

        assert run_id is not None
        run_ctx = orchestrator.get_run(run_id)
        assert run_ctx is not None

        # Poll for completion (max 20 seconds)
        start_wait = time.time()
        while time.time() - start_wait < 20.0:
            if run_ctx.status in (PipelineStatus.COMPLETED, PipelineStatus.FAILED):
                break
            time.sleep(0.2)

        assert run_ctx.status == PipelineStatus.COMPLETED
        assert len(run_ctx.stage_results) == 9


# ═══════════════════════════════════════════════════════════════
# 4. Orchestration Resilience: Cancellation, Retries, Failures
# ═══════════════════════════════════════════════════════════════

class TestOrchestrationResilience:
    """Validate robustness against timeouts, cancellation, and partial failures."""

    def test_pipeline_cancellation(self) -> None:
        orchestrator = IntelligencePipelineOrchestrator()
        run_id = orchestrator.start(scenario_name="Banking", scale="small", seed=888)

        # Cancel immediately
        cancelled = orchestrator.cancel_run(run_id)
        assert cancelled is True

        time.sleep(1.0)
        run_ctx = orchestrator.get_run(run_id)
        assert run_ctx.status in (PipelineStatus.CANCELLED, PipelineStatus.COMPLETED)

    def test_stage_retry_mechanism(self) -> None:
        class FlakyStage(BasePipelineStage):
            stage_id = "flaky_stage"
            stage_name = "Flaky Stage"
            is_critical = False
            attempts = 0

            def __init__(self):
                super().__init__(is_critical=False, max_retries=2)

            def _run(self, context: UnifiedExecutionContext):
                FlakyStage.attempts += 1
                if FlakyStage.attempts == 1:
                    raise RuntimeError("Transient network glitch")
                return M1DiscoveryStage()._run(context)

        FlakyStage.attempts = 0
        ctx = UnifiedExecutionContext(scenario_name="SaaS", scale="small", seed=42)
        flaky = FlakyStage()
        res = flaky.execute(ctx)

        assert res.status == StageStatus.COMPLETED
        assert FlakyStage.attempts == 2

    def test_partial_failure_non_critical_stage(self) -> None:
        class BrokenNonCriticalStage(BasePipelineStage):
            stage_id = "broken_optional_stage"
            stage_name = "Broken Optional Stage"
            is_critical = False

            def _run(self, context: UnifiedExecutionContext):
                raise ValueError("Optional service offline")

        orchestrator = IntelligencePipelineOrchestrator()
        custom_stages = [
            M1DiscoveryStage(),
            BrokenNonCriticalStage(),
            M2CostStage(),
        ]

        ctx = orchestrator.run(
            scenario_name="SaaS",
            scale="small",
            seed=42,
            continue_on_partial_failure=True,
            custom_stages=custom_stages,
            evaluate_ground_truth=False,
        )

        assert ctx.status == PipelineStatus.COMPLETED
        assert ctx.stage_results["broken_optional_stage"].status == StageStatus.DEGRADED
        assert ctx.stage_results["m2_cost"].status == StageStatus.COMPLETED

    def test_pipeline_timeout_enforcement(self) -> None:
        class SlowStage(BasePipelineStage):
            stage_id = "slow_stage"
            stage_name = "Slow Stage"
            is_critical = True

            def _run(self, context: UnifiedExecutionContext):
                time.sleep(1.5)
                return M1DiscoveryStage()._run(context)

        orchestrator = IntelligencePipelineOrchestrator()
        custom_stages = [SlowStage(), M2CostStage()]

        ctx = orchestrator.run(
            scenario_name="SaaS",
            scale="small",
            seed=42,
            timeout_seconds=0.5,  # Force immediate timeout
            custom_stages=custom_stages,
            evaluate_ground_truth=False,
        )

        assert ctx.status == PipelineStatus.TIMEOUT


# ═══════════════════════════════════════════════════════════════
# 5. Ground Truth Evaluation Tests
# ═══════════════════════════════════════════════════════════════

class TestGroundTruthEvaluation:
    """Validate accuracy scoring against simulator Ground Truth."""

    def test_ground_truth_evaluator_metrics(self) -> None:
        orchestrator = IntelligencePipelineOrchestrator()
        ctx = orchestrator.run(scenario_name="SaaS", scale="small", seed=42)

        evaluator = PipelineGroundTruthEvaluator()
        sim = get_simulator()
        sim_ctx = sim.get_context()

        report = evaluator.evaluate(ctx, sim_ctx.ground_truth)

        assert report.recommendation_precision >= 0.0
        assert report.recommendation_recall >= 0.0
        assert report.savings_prediction_accuracy >= 0.0
        assert report.risk_prediction_accuracy >= 0.0
        assert report.simulation_accuracy >= 0.0
        assert report.decision_accuracy >= 0.0
        assert 0.0 <= report.composite_score <= 100.0


# ═══════════════════════════════════════════════════════════════
# 6. Pipeline REST API Tests
# ═══════════════════════════════════════════════════════════════

class TestPipelineRESTAPIs:
    """Validate FastAPI pipeline endpoints under /api/v1/pipeline."""

    @pytest.fixture
    def client(self) -> TestClient:
        import main
        return TestClient(main.app)

    def test_api_run_sync(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/pipeline/run",
            json={"scenario": "Startup", "scale": "small", "seed": 42},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "COMPLETED"
        assert len(data["stages"]) == 9
        assert "m1_discovery" in data["stages"]
        assert "m9_decision" in data["stages"]

    def test_api_run_async_and_inspect(self, client: TestClient) -> None:
        start_resp = client.post(
            "/api/v1/pipeline/runs",
            json={"scenario": "Healthcare", "scale": "small", "seed": 99},
        )
        assert start_resp.status_code == 202
        data = start_resp.json()
        run_id = data["run_id"]
        assert data["status"] == "PENDING"

        # Inspect run
        get_resp = client.get(f"/api/v1/pipeline/runs/{run_id}")
        assert get_resp.status_code == 200
        run_details = get_resp.json()
        assert run_details["run_id"] == run_id

        # List runs
        list_resp = client.get("/api/v1/pipeline/runs")
        assert list_resp.status_code == 200
        runs_list = list_resp.json()
        assert any(r["run_id"] == run_id for r in runs_list)

    def test_api_timeline_and_evaluation(self, client: TestClient) -> None:
        # Run sync first
        run_resp = client.post(
            "/api/v1/pipeline/run",
            json={"scenario": "Gaming", "scale": "small", "seed": 123},
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run_id"]

        # Timeline API
        tl_resp = client.get(f"/api/v1/pipeline/runs/{run_id}/timeline")
        assert tl_resp.status_code == 200
        timeline = tl_resp.json()
        assert len(timeline) > 0
        assert timeline[0]["action"] == "PIPELINE_STARTED"

        # Evaluation API
        eval_resp = client.get(f"/api/v1/pipeline/runs/{run_id}/evaluation")
        assert eval_resp.status_code == 200
        eval_data = eval_resp.json()
        assert "composite_score" in eval_data
        assert eval_data["composite_score"] >= 0.0

"""
Intelligence Pipeline Orchestration Engine.
Coordinates end-to-end execution across M1-M9 stages with synchronous and asynchronous modes,
timeouts, retries, cancellation tokens, partial failure resilience, and ground truth benchmarking.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from pipeline.evaluator import PipelineGroundTruthEvaluator
from pipeline.models import PipelineStatus, StageStatus, UnifiedExecutionContext
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

logger = logging.getLogger("cloudpilot.pipeline.orchestrator")


class IntelligencePipelineOrchestrator:
    """
    Production-grade orchestrator for the CloudPilot Intelligence Pipeline.
    Manages stage lifecycle, state propagation, asynchronous tasks, and audit logs.
    """

    def __init__(self, thread_pool_size: int = 4) -> None:
        self._runs: Dict[str, UnifiedExecutionContext] = {}
        self._cancel_tokens: Dict[str, threading.Event] = {}
        self._executor = ThreadPoolExecutor(max_workers=thread_pool_size, thread_name_prefix="pipeline-worker")
        self._evaluator = PipelineGroundTruthEvaluator()
        self._lock = threading.Lock()
        logger.info("IntelligencePipelineOrchestrator initialized with %d worker threads", thread_pool_size)

    def _build_default_stages(self) -> List[BasePipelineStage]:
        """Construct sequential list of M1-M9 intelligence stages."""
        return [
            M1DiscoveryStage(),
            M2CostStage(),
            M3ApplicationStage(),
            M4RiskStage(),
            M5StrategyStage(),
            M6DigitalTwinStage(),
            M7ExplainabilityStage(),
            M8LearningStage(),
            M9DecisionStage(),
        ]

    def run(
        self,
        scenario_name: str = "SaaS",
        scale: str = "small",
        seed: int = 42,
        timeout_seconds: float = 120.0,
        continue_on_partial_failure: bool = True,
        evaluate_ground_truth: bool = True,
        custom_stages: Optional[List[BasePipelineStage]] = None,
        run_id: Optional[str] = None,
    ) -> UnifiedExecutionContext:
        """
        Execute the intelligence pipeline synchronously from end to end.
        """
        # Ensure active simulator context matches requested scenario
        sim = get_simulator()
        scale_enum = SimulationScale(scale.lower()) if isinstance(scale, str) else scale
        sim_ctx = sim.generate(profile=scenario_name, scale=scale_enum, seed=seed)

        with self._lock:
            if run_id and run_id in self._runs:
                context = self._runs[run_id]
                context.status = PipelineStatus.RUNNING
                context.started_at = datetime.now(timezone.utc)
                cancel_token = self._cancel_tokens.get(run_id, threading.Event())
            else:
                context = UnifiedExecutionContext(
                    run_id=run_id or f"run-{int(time.time() * 1000)}-{seed}",
                    scenario_name=scenario_name,
                    scale=scale_enum.value if hasattr(scale_enum, "value") else str(scale_enum),
                    seed=seed,
                    status=PipelineStatus.RUNNING,
                    started_at=datetime.now(timezone.utc),
                )
                cancel_token = threading.Event()
                self._runs[context.run_id] = context
                self._cancel_tokens[context.run_id] = cancel_token

        context.add_timeline_event(
            agent_name="PipelineOrchestrator",
            action="PIPELINE_STARTED",
            status="INFO",
            details={"scenario": scenario_name, "scale": scale, "seed": seed},
        )

        stages = custom_stages or self._build_default_stages()
        start_time = time.perf_counter()

        try:
            for stage in stages:
                # 1. Check Cancellation
                if cancel_token.is_set():
                    logger.warning("Pipeline %s cancelled before stage %s", context.run_id, stage.stage_id)
                    context.status = PipelineStatus.CANCELLED
                    context.add_timeline_event(
                        agent_name="PipelineOrchestrator",
                        action="PIPELINE_CANCELLED",
                        status="WARNING",
                        stage_id=stage.stage_id,
                    )
                    break

                # 2. Check Pipeline Timeout
                elapsed = time.perf_counter() - start_time
                if elapsed > timeout_seconds:
                    logger.error("Pipeline %s timed out after %.1f seconds", context.run_id, elapsed)
                    context.status = PipelineStatus.TIMEOUT
                    context.add_timeline_event(
                        agent_name="PipelineOrchestrator",
                        action="PIPELINE_TIMEOUT",
                        status="ERROR",
                        stage_id=stage.stage_id,
                        details={"elapsed_seconds": elapsed, "timeout_limit": timeout_seconds},
                    )
                    break

                # 3. Execute Stage
                stage_result = stage.execute(context, cancel_token=cancel_token)

                # 4. Evaluate Stage Failure
                if stage_result.status == StageStatus.FAILED:
                    if stage.is_critical and not continue_on_partial_failure:
                        logger.error("Critical stage %s failed; halting pipeline %s", stage.stage_id, context.run_id)
                        context.status = PipelineStatus.FAILED
                        break
                    else:
                        logger.warning("Non-critical stage %s failed or degraded; continuing pipeline", stage.stage_id)

            # 5. Evaluate Against Ground Truth if pipeline completed normally
            if context.status == PipelineStatus.RUNNING:
                context.status = PipelineStatus.COMPLETED
                if evaluate_ground_truth and sim_ctx.ground_truth:
                    try:
                        self._evaluator.evaluate(context, sim_ctx.ground_truth)
                    except Exception as eval_err:
                        logger.error("Ground truth evaluation error: %s", eval_err, exc_info=True)

            context.completed_at = datetime.now(timezone.utc)
            context.total_duration_ms = (time.perf_counter() - start_time) * 1000

            context.add_timeline_event(
                agent_name="PipelineOrchestrator",
                action="PIPELINE_FINISHED",
                status="SUCCESS" if context.status == PipelineStatus.COMPLETED else "ERROR",
                details={
                    "final_status": context.status.value,
                    "duration_ms": context.total_duration_ms,
                    "stages_completed": sum(1 for s in context.stage_results.values() if s.status == StageStatus.COMPLETED),
                },
            )
            logger.info("Pipeline %s completed with status %s in %.1fms", context.run_id, context.status.value, context.total_duration_ms)
            return context

        except Exception as e:
            logger.error("Unhandled fatal exception in pipeline %s: %s", context.run_id, e, exc_info=True)
            context.status = PipelineStatus.FAILED
            context.completed_at = datetime.now(timezone.utc)
            context.total_duration_ms = (time.perf_counter() - start_time) * 1000
            return context

    def start(
        self,
        scenario_name: str = "SaaS",
        scale: str = "small",
        seed: int = 42,
        timeout_seconds: float = 120.0,
        continue_on_partial_failure: bool = True,
        evaluate_ground_truth: bool = True,
    ) -> str:
        """
        Execute the intelligence pipeline asynchronously in the background.
        Returns the unique run_id immediately.
        """
        run_id = f"run-{int(time.time())}-{seed}"
        context = UnifiedExecutionContext(
            run_id=run_id,
            scenario_name=scenario_name,
            scale=scale,
            seed=seed,
            status=PipelineStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        cancel_token = threading.Event()
        with self._lock:
            self._runs[run_id] = context
            self._cancel_tokens[run_id] = cancel_token

        def _worker():
            self.run(
                scenario_name=scenario_name,
                scale=scale,
                seed=seed,
                timeout_seconds=timeout_seconds,
                continue_on_partial_failure=continue_on_partial_failure,
                evaluate_ground_truth=evaluate_ground_truth,
                run_id=run_id,
            )

        self._executor.submit(_worker)
        logger.info("Asynchronous pipeline task queued with run_id: %s", run_id)
        return run_id

    def get_run(self, run_id: str) -> Optional[UnifiedExecutionContext]:
        """Retrieve execution context by run_id."""
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self) -> List[Dict[str, Any]]:
        """List all pipeline runs with summary metrics."""
        with self._lock:
            return [
                {
                    "run_id": r.run_id,
                    "scenario": r.scenario_name,
                    "scale": r.scale,
                    "seed": r.seed,
                    "status": r.status.value,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "total_duration_ms": r.total_duration_ms,
                    "stages_completed": sum(1 for s in r.stage_results.values() if s.status == StageStatus.COMPLETED),
                    "composite_score": r.ground_truth_evaluation.composite_score if r.ground_truth_evaluation else None,
                }
                for r in reversed(list(self._runs.values()))
            ]

    def cancel_run(self, run_id: str) -> bool:
        """Cancel an ongoing or pending pipeline run."""
        with self._lock:
            token = self._cancel_tokens.get(run_id)
            if token and not token.is_set():
                token.set()
                run_ctx = self._runs.get(run_id)
                if run_ctx and run_ctx.status in (PipelineStatus.RUNNING, PipelineStatus.PENDING):
                    run_ctx.status = PipelineStatus.CANCELLED
                logger.info("Signaled cancellation for pipeline run %s", run_id)
                return True
        return False


# Global singleton
_ORCHESTRATOR: Optional[IntelligencePipelineOrchestrator] = None


def get_pipeline_orchestrator() -> IntelligencePipelineOrchestrator:
    """Singleton provider for IntelligencePipelineOrchestrator."""
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = IntelligencePipelineOrchestrator()
    return _ORCHESTRATOR

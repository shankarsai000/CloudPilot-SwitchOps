"""
Simulator Component (Digital Twin M6)

Coordinates predictors and safety scoring engines to run simulations against the virtual DigitalTwin.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from models_simulation import SimulationReport, DigitalTwin
from performance_predictor import PerformancePredictor
from cost_predictor import CostPredictor
from failure_propagation import FailurePropagationPredictor
from rollback_simulator import RollbackSimulator
from safety_engine import SafetyEngine
from execution_readiness import ExecutionReadinessEvaluator

logger = logging.getLogger(__name__)


class Simulator:
    """Core simulation orchestrator."""

    def __init__(
        self,
        performance_predictor: Optional[PerformancePredictor] = None,
        cost_predictor: Optional[CostPredictor] = None,
        failure_predictor: Optional[FailurePropagationPredictor] = None,
        rollback_simulator: Optional[RollbackSimulator] = None,
        safety_engine: Optional[SafetyEngine] = None,
        readiness_evaluator: Optional[ExecutionReadinessEvaluator] = None,
    ) -> None:
        """Initialize Simulator component."""
        self.performance_predictor = performance_predictor or PerformancePredictor()
        self.cost_predictor = cost_predictor or CostPredictor()
        self.failure_predictor = failure_predictor or FailurePropagationPredictor()
        self.rollback_simulator = rollback_simulator or RollbackSimulator()
        self.safety_engine = safety_engine or SafetyEngine()
        self.readiness_evaluator = readiness_evaluator or ExecutionReadinessEvaluator()

    def run_simulation(
        self,
        target_id: str,
        action: str,
        parameters: dict[str, Any],
        twin_context: DigitalTwin,
        policy_violations: list[str] = None,
    ) -> SimulationReport:
        """Execute a simulated action run against the twin state variables.

        Args:
            target_id: Affected resource or application ID
            action: Action simulated
            parameters: Action parameters
            twin_context: Mapped DigitalTwin context
            policy_violations: Pre-calculated compliance/policy violations (from M4/M5)

        Returns:
            SimulationReport object
        """
        violations = policy_violations or []

        # 1. Performance predictions
        perf = self.performance_predictor.predict_performance(target_id, action, parameters, twin_context)

        # 2. Cost predictions
        cost = self.cost_predictor.predict_cost(target_id, action, parameters, twin_context)

        # 3. Cascading failure checks
        failures = self.failure_predictor.predict_failures(target_id, action, twin_context)

        # 4. Rollback simulations
        rollback = self.rollback_simulator.simulate_rollback(target_id, action, twin_context)

        # 5. Safety score metrics
        safety_score, safety_status = self.safety_engine.calculate_safety_score(
            target_id, action, failures, perf, violations
        )

        # 6. Execution readiness
        readiness = self.readiness_evaluator.evaluate_readiness(
            target_id, safety_score, violations, rollback.recovery_confidence_percentage
        )

        return SimulationReport(
            simulation_id=f"sim-{uuid.uuid4().hex[:12]}",
            target_id=target_id,
            action=action,
            safety_score=safety_score,
            safety_status=safety_status,
            performance=perf,
            cost=cost,
            rollback=rollback,
            cascading_failures=failures,
            execution_readiness_score=round(readiness, 1),
        )

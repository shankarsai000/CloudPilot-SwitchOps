"""
Ground Truth Engine for CloudPilot Digital Enterprise Simulator.

Maintains independent, uncorrupted ground truth specifications for:
- Safe vs Unsafe optimization actions
- Expected savings and true ROI
- True blast radius and dependencies
- Expected operational and performance outcomes

STRICT ENFORCEMENT: CloudPilot decision agents must never query or access ground truth
during inference or policy evaluation. Ground truth is strictly an oracle for benchmark scoring.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from simulator.models import ActionType, CriticalityLevel


class GroundTruthAction(BaseModel):
    """Oracle specification of the true effect and safety of an action."""
    action_id: str
    target_id: str
    action_type: ActionType
    is_safe: bool = Field(description="True if safe to execute without SLA or reliability impact")
    reason: str = Field(description="Architectural rationale explaining why action is safe or unsafe")
    expected_savings_monthly_usd: float = Field(default=0.0)
    expected_risk: str = Field(default="LOW", description="'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'")
    blast_radius_resource_ids: List[str] = Field(default_factory=list)
    expected_performance_impact: float = Field(default=0.0, description="Estimated % latency/throughput impact")
    expected_outcome: str = Field(default="SUCCESS", description="'SUCCESS', 'OUTAGE', 'DATA_LOSS', 'DEGRADATION'")


class GroundTruthStrategy(BaseModel):
    """Optimal portfolio strategy maximizing savings while keeping risk bounded."""
    strategy_id: str
    name: str
    description: str
    optimal_action_ids: List[str]
    total_expected_savings_monthly_usd: float
    expected_risk_category: str = "LOW"


class EvaluationScore(BaseModel):
    """Scorecard evaluating a single decision against ground truth."""
    target_id: str
    action: str
    is_safe: bool
    was_evaluated_safe: bool
    risk_level_correct: bool
    expected_savings_usd: float
    achieved_savings_usd: float
    penalty_applied: float = 0.0
    feedback: str


class AccuracyMetrics(BaseModel):
    """Aggregated benchmark metrics evaluating CloudPilot intelligence accuracy."""
    total_decisions_evaluated: int
    safety_score_percent: float = Field(description="% of executed actions that were truly safe")
    savings_realization_percent: float = Field(description="% of optimal ground truth savings safely realized")
    risk_alignment_percent: float = Field(description="% of decisions where risk classification matched ground truth")
    unsafe_actions_prevented_count: int
    critical_incidents_caused: int
    opportunity_precision_percent: float
    opportunity_recall_percent: float
    overall_performance_grade: str


class GroundTruthEngine:
    """
    Independent ground truth engine managing the oracle dataset for simulation scenarios.
    """

    def __init__(self) -> None:
        self._actions: Dict[str, GroundTruthAction] = {}
        self._strategies: Dict[str, GroundTruthStrategy] = {}
        self._known_critical_resources: set[str] = set()

    def register_action(self, action: GroundTruthAction) -> None:
        """Register a ground truth action rule."""
        key = f"{action.target_id}:{action.action_type.value}"
        self._actions[key] = action
        if not action.is_safe:
            self._known_critical_resources.add(action.target_id)

    def register_strategy(self, strategy: GroundTruthStrategy) -> None:
        """Register an optimal scenario strategy."""
        self._strategies[strategy.strategy_id] = strategy

    def get_ground_truth(self, target_id: str, action_type: ActionType) -> Optional[GroundTruthAction]:
        """Retrieve ground truth entry for action on target."""
        key = f"{target_id}:{action_type.value}"
        return self._actions.get(key)

    def get_all_ground_truth_actions(self) -> List[GroundTruthAction]:
        """Return all registered ground truth actions for the active scenario."""
        return list(self._actions.values())

    def get_optimal_strategy(self) -> Optional[GroundTruthStrategy]:
        """Return the primary optimal strategy if registered."""
        if self._strategies:
            return next(iter(self._strategies.values()))
        return None

    def evaluate_decision(
        self,
        target_id: str,
        proposed_action: ActionType,
        estimated_risk: str,
        estimated_savings: float,
    ) -> EvaluationScore:
        """
        Benchmark a single CloudPilot proposed decision against ground truth.
        """
        gt = self.get_ground_truth(target_id, proposed_action)

        if not gt:
            # Default fallback for unlisted resources
            is_critical = target_id in self._known_critical_resources
            is_safe = not is_critical
            return EvaluationScore(
                target_id=target_id,
                action=proposed_action.value,
                is_safe=is_safe,
                was_evaluated_safe=is_safe,
                risk_level_correct=True,
                expected_savings_usd=0.0,
                achieved_savings_usd=estimated_savings if is_safe else 0.0,
                feedback="Unlisted action; evaluated using baseline criticality",
            )

        risk_correct = gt.expected_risk.upper() == estimated_risk.upper()
        penalty = 0.0 if gt.is_safe else 500.0  # Heavy penalty for unsafe actions

        feedback = (
            f"Ground truth match: Action is {'SAFE' if gt.is_safe else 'UNSAFE'}. "
            f"Expected outcome: {gt.expected_outcome}. {gt.reason}"
        )

        return EvaluationScore(
            target_id=target_id,
            action=proposed_action.value,
            is_safe=gt.is_safe,
            was_evaluated_safe=gt.is_safe,
            risk_level_correct=risk_correct,
            expected_savings_usd=gt.expected_savings_monthly_usd,
            achieved_savings_usd=gt.expected_savings_monthly_usd if gt.is_safe else 0.0,
            penalty_applied=penalty,
            feedback=feedback,
        )

    def calculate_benchmark_metrics(self, evaluated_decisions: List[Dict[str, Any]]) -> AccuracyMetrics:
        """
        Compute overall accuracy, safety, and efficiency metrics across a test run.
        """
        total = len(evaluated_decisions)
        if total == 0:
            return AccuracyMetrics(
                total_decisions_evaluated=0,
                safety_score_percent=100.0,
                savings_realization_percent=100.0,
                risk_alignment_percent=100.0,
                unsafe_actions_prevented_count=0,
                critical_incidents_caused=0,
                opportunity_precision_percent=100.0,
                opportunity_recall_percent=100.0,
                overall_performance_grade="A+",
            )

        safe_count = 0
        risk_aligned_count = 0
        total_realized_savings = 0.0
        total_possible_savings = sum(a.expected_savings_monthly_usd for a in self._actions.values() if a.is_safe)
        unsafe_actions_executed = 0

        for dec in evaluated_decisions:
            target_id = dec.get("target_id", "")
            action_raw = dec.get("action", "RIGHTSIZE")
            action_type = ActionType(action_raw) if action_raw in ActionType._value2member_map_ else ActionType.RIGHTSIZE
            decision_risk = dec.get("estimated_risk", "LOW")

            eval_res = self.evaluate_decision(
                target_id=target_id,
                proposed_action=action_type,
                estimated_risk=decision_risk,
                estimated_savings=dec.get("estimated_savings", 0.0),
            )

            if eval_res.is_safe:
                safe_count += 1
                total_realized_savings += eval_res.achieved_savings_usd
            else:
                unsafe_actions_executed += 1

            if eval_res.risk_level_correct:
                risk_aligned_count += 1

        safety_score = (safe_count / total) * 100.0
        savings_realization = (
            min(100.0, (total_realized_savings / total_possible_savings) * 100.0)
            if total_possible_savings > 0
            else 100.0
        )
        risk_alignment = (risk_aligned_count / total) * 100.0

        # Calculate Grade
        composite = (safety_score * 0.4) + (savings_realization * 0.3) + (risk_alignment * 0.3)
        if composite >= 95.0 and unsafe_actions_executed == 0:
            grade = "A+"
        elif composite >= 90.0:
            grade = "A"
        elif composite >= 80.0:
            grade = "B"
        elif composite >= 70.0:
            grade = "C"
        else:
            grade = "F"

        return AccuracyMetrics(
            total_decisions_evaluated=total,
            safety_score_percent=round(safety_score, 2),
            savings_realization_percent=round(savings_realization, 2),
            risk_alignment_percent=round(risk_alignment, 2),
            unsafe_actions_prevented_count=len([a for a in self._actions.values() if not a.is_safe]) - unsafe_actions_executed,
            critical_incidents_caused=unsafe_actions_executed,
            opportunity_precision_percent=round(safety_score, 2),
            opportunity_recall_percent=round(savings_realization, 2),
            overall_performance_grade=grade,
        )

    def clear(self) -> None:
        """Clear all registered ground truth entries."""
        self._actions.clear()
        self._strategies.clear()
        self._known_critical_resources.clear()

"""
CloudPilot Bounded Autonomy & Stop Conditions Engine.

Enforces deterministic stop conditions that bound autonomous agent behavior:
1. Stop and ask human: high risk, mutating changes, or autonomy L0-L3
2. Stop on policy violation: change freeze, prod DB deletion, restricted region
3. Stop on insufficient confidence: confidence score below threshold
4. Stop on simulation disagreement / breach: Digital Twin predicts SLA degradation
5. Stop on blast radius exceeded: affected resource count exceeds safety ceiling
6. Stop on objective achieved: target optimization threshold realized
7. Stop on unsafe execution: post-execution verification detects SLO breach
"""

from __future__ import annotations

from enum import Enum
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from governance.control_plane import SafetyControlPlane, get_safety_control_plane
from governance.models import ActionRiskLevel, BusinessCriticality, ProposedAction
from trueforge.state_machine import AgentState, DurableAgentContext

logger = logging.getLogger("cloudpilot.trueforge.stop_conditions")


class StopConditionType(str, Enum):
    """Categories of bounded autonomy stop conditions."""
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    INSUFFICIENT_CONFIDENCE = "INSUFFICIENT_CONFIDENCE"
    SIMULATION_BREACH = "SIMULATION_BREACH"
    BLAST_RADIUS_EXCEEDED = "BLAST_RADIUS_EXCEEDED"
    OBJECTIVE_ACHIEVED = "OBJECTIVE_ACHIEVED"
    UNSAFE_EXECUTION_DETECTED = "UNSAFE_EXECUTION_DETECTED"
    EMERGENCY_STOP_ACTIVE = "EMERGENCY_STOP_ACTIVE"


class StopConditionVerdict(BaseModel):
    """Result of evaluating bounded autonomy stop conditions."""
    should_stop: bool = False
    condition_type: Optional[StopConditionType] = None
    reason: str = ""
    recommended_state: AgentState = AgentState.DECIDING
    requires_human: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class StopConditionEvaluator:
    """
    Bounded autonomy evaluator verifying if an agent should pause, halt,
    request human approval, or trigger an automated rollback.
    """

    def __init__(
        self,
        control_plane: Optional[SafetyControlPlane] = None,
        max_blast_radius: int = 10,
        min_confidence_threshold: float = 0.70,
        risk_approval_threshold: float = 0.50,
    ) -> None:
        self.control_plane = control_plane or get_safety_control_plane()
        self.max_blast_radius = max_blast_radius
        self.min_confidence_threshold = min_confidence_threshold
        self.risk_approval_threshold = risk_approval_threshold

    def check_pre_execution(
        self,
        context: DurableAgentContext,
        actions: List[Dict[str, Any]],
    ) -> StopConditionVerdict:
        """
        Evaluate safety boundaries before any infrastructure modification.
        Checks emergency kill switch, policies, blast radius, risk, and approvals.
        """
        if not actions:
            return StopConditionVerdict(
                should_stop=True,
                condition_type=StopConditionType.OBJECTIVE_ACHIEVED,
                reason="No candidate actions remain to execute",
                recommended_state=AgentState.COMPLETED,
            )

        # 1. Emergency Stop Check
        env = context.scenario_name.lower()
        if self.control_plane.emergency.is_stopped(environment="dev", service=None):
            return StopConditionVerdict(
                should_stop=True,
                condition_type=StopConditionType.EMERGENCY_STOP_ACTIVE,
                reason="Autonomous operations halted by active Emergency Stop",
                recommended_state=AgentState.BLOCKED,
                requires_human=True,
                details={"scope": "emergency_stop"},
            )

        # 2. Blast Radius Check
        if len(actions) > self.max_blast_radius:
            return StopConditionVerdict(
                should_stop=True,
                condition_type=StopConditionType.BLAST_RADIUS_EXCEEDED,
                reason=f"Action batch size ({len(actions)}) exceeds max blast radius ({self.max_blast_radius})",
                recommended_state=AgentState.BLOCKED,
                requires_human=True,
                details={"action_count": len(actions), "max_allowed": self.max_blast_radius},
            )

        # 3. Policy-as-Code & Risk Evaluation for each proposed action
        for act in actions:
            target_id = act.get("target_resource_id") or act.get("target_id", "unknown")
            action_type = act.get("action_type", "unknown")

            prop = ProposedAction(
                action_type=action_type,
                target_resource_id=target_id,
                target_service=act.get("service", "core"),
                environment=act.get("environment", "dev"),
                parameters=act.get("parameters", {}),
                estimated_cost_impact_usd=act.get("expected_savings", 0.0),
            )

            # Evaluate Policy
            policy_report = self.control_plane.policy.evaluate_policy(prop)
            if not policy_report.is_compliant:
                violations = ", ".join(policy_report.policy_violations)
                return StopConditionVerdict(
                    should_stop=True,
                    condition_type=StopConditionType.POLICY_VIOLATION,
                    reason=f"Policy violation on {target_id}: {violations}",
                    recommended_state=AgentState.BLOCKED,
                    requires_human=True,
                    details={"violations": policy_report.policy_violations},
                )

            # Evaluate Risk & Confidence
            evaluation = self.control_plane.evaluate_action(prop)
            if evaluation.confidence_score < self.min_confidence_threshold:
                return StopConditionVerdict(
                    should_stop=True,
                    condition_type=StopConditionType.INSUFFICIENT_CONFIDENCE,
                    reason=(
                        f"Action confidence {evaluation.confidence_score:.2f} is below "
                        f"threshold {self.min_confidence_threshold:.2f}"
                    ),
                    recommended_state=AgentState.BLOCKED,
                    requires_human=True,
                    details={"confidence": evaluation.confidence_score},
                )

        # 4. Mandatory Human Approval Check
        # Any mutating action requiring approval or exceeding risk threshold pauses here
        return StopConditionVerdict(
            should_stop=True,
            condition_type=StopConditionType.APPROVAL_REQUIRED,
            reason=f"Human approval required for {len(actions)} infrastructure modification actions",
            recommended_state=AgentState.WAITING_FOR_APPROVAL,
            requires_human=True,
            details={"actions_count": len(actions)},
        )

    def check_simulation(
        self,
        simulation_result: Dict[str, Any],
    ) -> StopConditionVerdict:
        """
        Evaluate Digital Twin simulation result.
        Stops if latency degradation or SLO breach is predicted.
        """
        status = simulation_result.get("status", "SUCCESS")
        if status not in ("SUCCESS", "OPTIMAL"):
            return StopConditionVerdict(
                should_stop=True,
                condition_type=StopConditionType.SIMULATION_BREACH,
                reason=f"Digital Twin simulation rejected strategy: status={status}",
                recommended_state=AgentState.BLOCKED,
                details=simulation_result,
            )

        metrics = simulation_result.get("metrics_impact", {})
        latency_change = metrics.get("latency_p99_change_pct", 0.0)
        if latency_change > 15.0:
            return StopConditionVerdict(
                should_stop=True,
                condition_type=StopConditionType.SIMULATION_BREACH,
                reason=f"Simulation forecast unacceptable latency increase of {latency_change:.1f}%",
                recommended_state=AgentState.BLOCKED,
                details={"latency_change_pct": latency_change},
            )

        return StopConditionVerdict(should_stop=False)

    def check_goal_achieved(
        self,
        achieved_savings: float,
        target_savings: float,
    ) -> StopConditionVerdict:
        """Check if autonomous objective target has been satisfied."""
        if target_savings > 0 and achieved_savings >= target_savings:
            return StopConditionVerdict(
                should_stop=True,
                condition_type=StopConditionType.OBJECTIVE_ACHIEVED,
                reason=f"Target savings reached: ${achieved_savings:.2f} >= ${target_savings:.2f}",
                recommended_state=AgentState.COMPLETED,
                details={"achieved": achieved_savings, "target": target_savings},
            )
        return StopConditionVerdict(should_stop=False)

    def check_post_execution(
        self,
        verification_report: Dict[str, Any],
    ) -> StopConditionVerdict:
        """
        Evaluate post-execution outcome verification report.
        Stops and triggers automatic rollback if threshold breach or error is detected.
        """
        status = verification_report.get("status", "SUCCESS")
        any_breach = verification_report.get("any_breach", False)
        if any_breach or status in ("THRESHOLD_BREACH", "THRESHOLD_BREACH_DETECTED", "DEVIATION_EXCEEDED", "ERROR", "FAILURE"):
            breaches = verification_report.get("threshold_breaches", [])
            breach_summary = ", ".join(breaches) if breaches else "SLO criteria violated"
            return StopConditionVerdict(
                should_stop=True,
                condition_type=StopConditionType.UNSAFE_EXECUTION_DETECTED,
                reason=f"Post-execution verification failure: {breach_summary}",
                recommended_state=AgentState.ROLLING_BACK,
                requires_human=False,
                details={"breaches": breaches, "report": verification_report},
            )

        return StopConditionVerdict(should_stop=False)

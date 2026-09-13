"""
Multi-Factor Action Evaluator.

Evaluates proposed operations across all 9 required dimensions:
1. Risk
2. Confidence
3. Business Criticality
4. Policy-as-Code Compliance
5. Blast Radius
6. Reversibility
7. Simulation Result
8. Historical Success
9. Required Approval Routing
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from governance.models import (
    ActionEvaluation,
    ActionRiskLevel,
    ApprovalRoute,
    AutonomyLevel,
    BusinessCriticality,
    PolicyEvaluationReport,
    ProposedAction,
    ReversibilityType,
)
from governance.policy import PolicyAsCodeEngine, get_policy_engine


class MultiFactorActionEvaluator:
    """
    Evaluates infrastructure operations across 9 distinct safety and risk dimensions.
    """

    def __init__(self, policy_engine: Optional[PolicyAsCodeEngine] = None) -> None:
        self.policy_engine = policy_engine or get_policy_engine()

    def evaluate(
        self,
        action: ProposedAction,
        current_autonomy: AutonomyLevel = AutonomyLevel.L3_APPROVAL,
        evidence: Optional[Dict[str, Any]] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> ActionEvaluation:
        """
        Evaluate an action against all 9 dimensions and determine execution authorization.
        """
        ctx = context_data or {}
        evi = evidence or {}

        # -------------------------------------------------------------
        # Dimension 3: Business Criticality
        # -------------------------------------------------------------
        criticality = self._determine_criticality(action, ctx)

        # -------------------------------------------------------------
        # Dimension 6: Reversibility
        # -------------------------------------------------------------
        reversibility = self._determine_reversibility(action)

        # -------------------------------------------------------------
        # Dimension 5: Blast Radius
        # -------------------------------------------------------------
        dep_count, blast_score, blast_level = self._compute_blast_radius(action, ctx, criticality)

        # -------------------------------------------------------------
        # Dimension 4: Policy-as-Code Compliance
        # -------------------------------------------------------------
        region = action.parameters.get("region", ctx.get("region", "us-east-1"))
        frameworks = ctx.get("compliance_frameworks", [])
        policy_report = self.policy_engine.evaluate_policy(
            action=action,
            criticality=criticality,
            reversibility=reversibility,
            region=region,
            compliance_frameworks=frameworks,
        )

        # -------------------------------------------------------------
        # Dimension 7: Simulation Result
        # -------------------------------------------------------------
        sim_data = evi.get("simulation", {})
        slo_impact = float(sim_data.get("predicted_slo_impact_pct", 0.0))
        headroom_healthy = bool(sim_data.get("headroom_healthy", True))
        sim_verified = slo_impact <= 0.05 and headroom_healthy

        # -------------------------------------------------------------
        # Dimension 8: Historical Success
        # -------------------------------------------------------------
        hist_rate = float(evi.get("historical_success_rate", 0.95))
        hist_count = int(evi.get("historical_executions_count", 15))

        # -------------------------------------------------------------
        # Dimension 2: Confidence Score & Breakdown
        # -------------------------------------------------------------
        confidence_score, conf_breakdown = self._compute_confidence(
            action, evi, policy_report, sim_verified, hist_rate
        )

        # -------------------------------------------------------------
        # Dimension 1: Risk Level & Score
        # -------------------------------------------------------------
        risk_level, risk_score = self._compute_risk(
            action, criticality, reversibility, blast_score, policy_report, sim_verified
        )

        # -------------------------------------------------------------
        # Dimension 9: Required Approval Route
        # -------------------------------------------------------------
        is_blocked = not policy_report.is_compliant or any(
            "PROD_DATABASE_PROTECTION" in v for v in policy_report.policy_violations
        )

        req_approval = self._determine_approval_route(
            action=action,
            criticality=criticality,
            reversibility=reversibility,
            risk_level=risk_level,
            policy_report=policy_report,
            is_blocked=is_blocked,
        )

        # -------------------------------------------------------------
        # Overall Autonomy Level Authorization Verdict
        # -------------------------------------------------------------
        can_auto, req_appr, verdict = self._determine_authorization(
            current_autonomy=current_autonomy,
            risk_level=risk_level,
            reversibility=reversibility,
            criticality=criticality,
            policy_report=policy_report,
            blast_score=blast_score,
            confidence_score=confidence_score,
            required_approval=req_approval,
            is_blocked=is_blocked,
        )

        return ActionEvaluation(
            action_id=action.action_id,
            target_resource_id=action.target_resource_id,
            action_type=action.action_type,
            environment=action.environment,
            risk_level=risk_level,
            risk_score=risk_score,
            confidence_score=confidence_score,
            confidence_breakdown=conf_breakdown,
            business_criticality=criticality,
            policy_report=policy_report,
            blast_radius_level=blast_level,
            dependent_services_count=dep_count,
            blast_radius_score=blast_score,
            reversibility=reversibility,
            simulation_verified=sim_verified,
            predicted_slo_impact_pct=slo_impact,
            predicted_headroom_healthy=headroom_healthy,
            historical_success_rate=hist_rate,
            historical_executions_count=hist_count,
            required_approval=req_approval,
            can_auto_execute=can_auto,
            requires_approval=req_appr,
            is_blocked=is_blocked,
            verdict_reason=verdict,
            evaluated_at=datetime.now(timezone.utc),
        )

    # -------------------------------------------------------------------------
    # Internal Evaluation Helpers
    # -------------------------------------------------------------------------
    def _determine_criticality(self, action: ProposedAction, ctx: Dict[str, Any]) -> BusinessCriticality:
        svc = (action.target_service or "").lower()
        env = (action.environment or "dev").lower()

        # Check explicit tier tag in parameters or context
        tier_tag = action.parameters.get("tier", ctx.get("tier", "")).lower()
        if "tier_1" in tier_tag or "tier-1" in tier_tag or "critical" in tier_tag:
            return BusinessCriticality.TIER_1_MISSION_CRITICAL
        if "tier_2" in tier_tag or "tier-2" in tier_tag or "important" in tier_tag:
            return BusinessCriticality.TIER_2_IMPORTANT
        if "tier_3" in tier_tag or "tier-3" in tier_tag or "internal" in tier_tag:
            return BusinessCriticality.TIER_3_INTERNAL

        # Known critical services
        if any(c_name in svc for c_name in ("payment", "auth", "checkout", "order", "banking", "billing", "core")):
            return BusinessCriticality.TIER_1_MISSION_CRITICAL if env in ("prod", "production") else BusinessCriticality.TIER_2_IMPORTANT

        if env in ("prod", "production"):
            return BusinessCriticality.TIER_2_IMPORTANT

        return BusinessCriticality.DEV_TEST

    def _determine_reversibility(self, action: ProposedAction) -> ReversibilityType:
        act = action.action_type.lower()
        # Irreversible keywords: delete, terminate, destroy, drop, purge, wipe
        if any(kw in act for kw in ("terminate", "delete", "destroy", "drop", "purge", "wipe")):
            return ReversibilityType.IRREVERSIBLE
        return ReversibilityType.REVERSIBLE

    def _compute_blast_radius(
        self,
        action: ProposedAction,
        ctx: Dict[str, Any],
        criticality: BusinessCriticality,
    ) -> tuple[int, float, ActionRiskLevel]:
        dep_services = ctx.get("dependent_services", [])
        dep_count = len(dep_services) if isinstance(dep_services, list) else int(ctx.get("dependent_count", 0))

        if criticality == BusinessCriticality.TIER_1_MISSION_CRITICAL:
            score = 0.85
            level = ActionRiskLevel.CRITICAL
        elif dep_count > 3:
            score = 0.65
            level = ActionRiskLevel.HIGH
        elif dep_count >= 1:
            score = 0.30
            level = ActionRiskLevel.MEDIUM
        else:
            score = 0.05
            level = ActionRiskLevel.SAFE
        return dep_count, round(score, 2), level

    def _compute_confidence(
        self,
        action: ProposedAction,
        evidence: Dict[str, Any],
        policy_report: PolicyEvaluationReport,
        sim_verified: bool,
        hist_rate: float,
    ) -> tuple[float, Dict[str, float]]:
        infra_score = 95.0 if evidence.get("infrastructure") or action.target_resource_id else 60.0
        app_score = 90.0 if evidence.get("application") or action.target_service != "unknown" else 65.0
        sim_score = 95.0 if sim_verified else 40.0
        hist_score = round(hist_rate * 100.0, 1)
        policy_score = 98.0 if policy_report.is_compliant else 30.0

        final = (
            (infra_score * 0.25)
            + (app_score * 0.20)
            + (sim_score * 0.25)
            + (hist_score * 0.15)
            + (policy_score * 0.15)
        )
        breakdown = {
            "infrastructure": infra_score,
            "application": app_score,
            "simulation": sim_score,
            "history": hist_score,
            "policy": policy_score,
        }
        return round(final, 1), breakdown

    def _compute_risk(
        self,
        action: ProposedAction,
        criticality: BusinessCriticality,
        reversibility: ReversibilityType,
        blast_score: float,
        policy_report: PolicyEvaluationReport,
        sim_verified: bool,
    ) -> tuple[ActionRiskLevel, float]:
        if not policy_report.is_compliant:
            return ActionRiskLevel.CRITICAL, 0.95

        if criticality == BusinessCriticality.TIER_1_MISSION_CRITICAL:
            if reversibility == ReversibilityType.IRREVERSIBLE:
                return ActionRiskLevel.CRITICAL, 0.90
            return ActionRiskLevel.HIGH, 0.70

        if reversibility == ReversibilityType.IRREVERSIBLE:
            return ActionRiskLevel.HIGH, 0.65

        if blast_score > 0.5:
            return ActionRiskLevel.HIGH, 0.60
        elif blast_score > 0.25:
            return ActionRiskLevel.MEDIUM, 0.35

        if not sim_verified:
            return ActionRiskLevel.HIGH, 0.75

        return ActionRiskLevel.SAFE, 0.10

    def _determine_approval_route(
        self,
        action: ProposedAction,
        criticality: BusinessCriticality,
        reversibility: ReversibilityType,
        risk_level: ActionRiskLevel,
        policy_report: PolicyEvaluationReport,
        is_blocked: bool,
    ) -> ApprovalRoute:
        if is_blocked:
            return ApprovalRoute.BLOCKED

        is_prod = action.environment.lower() in ("prod", "production") or criticality == BusinessCriticality.TIER_1_MISSION_CRITICAL
        if is_prod and reversibility == ReversibilityType.IRREVERSIBLE:
            return ApprovalRoute.EXECUTIVE_APPROVAL

        if criticality == BusinessCriticality.TIER_1_MISSION_CRITICAL or risk_level == ActionRiskLevel.CRITICAL:
            return ApprovalRoute.EXECUTIVE_APPROVAL

        if "sg" in action.action_type.lower() or "firewall" in action.action_type.lower():
            return ApprovalRoute.SECURITY_TEAM

        if is_prod or criticality == BusinessCriticality.TIER_2_IMPORTANT:
            return ApprovalRoute.SRE_TEAM

        if reversibility == ReversibilityType.REVERSIBLE and risk_level in (ActionRiskLevel.SAFE, ActionRiskLevel.LOW) and not is_prod:
            return ApprovalRoute.AUTO_EXECUTE

        return ApprovalRoute.ENGINEERING_LEAD

    def _determine_authorization(
        self,
        current_autonomy: AutonomyLevel,
        risk_level: ActionRiskLevel,
        reversibility: ReversibilityType,
        criticality: BusinessCriticality,
        policy_report: PolicyEvaluationReport,
        blast_score: float,
        confidence_score: float,
        required_approval: ApprovalRoute,
        is_blocked: bool,
    ) -> tuple[bool, bool, str]:
        if is_blocked:
            return False, False, f"BLOCKED: Action violates mandatory policy: {', '.join(policy_report.policy_violations)}"

        # Strict Irreversibility Rule: No irreversible action may execute without satisfying approval policy
        if reversibility == ReversibilityType.IRREVERSIBLE and required_approval != ApprovalRoute.AUTO_EXECUTE:
            if current_autonomy in (AutonomyLevel.L4_LIMITED, AutonomyLevel.L5_FULL):
                return False, True, "IRREVERSIBLE ACTION: Autonomous execution denied — requires human authorization"

        # L0: Observe only
        if current_autonomy == AutonomyLevel.L0_OBSERVE:
            return False, False, "AUTONOMY L0: Observe-only mode — all execution and modification is disabled"

        # L1: Recommend only
        if current_autonomy == AutonomyLevel.L1_RECOMMEND:
            return False, False, "AUTONOMY L1: Recommend-only mode — execution disabled"

        # L2: Simulate only
        if current_autonomy == AutonomyLevel.L2_SIMULATE:
            return False, False, "AUTONOMY L2: Simulate-only mode — execution disabled"

        # L3: Execute with Human Approval
        if current_autonomy == AutonomyLevel.L3_APPROVAL:
            return False, True, "AUTONOMY L3: Human approval gate required before execution"

        # L4: Limited Autonomous Execution
        if current_autonomy == AutonomyLevel.L4_LIMITED:
            is_safe_action = (
                risk_level in (ActionRiskLevel.SAFE, ActionRiskLevel.LOW)
                and reversibility == ReversibilityType.REVERSIBLE
                and criticality in (BusinessCriticality.DEV_TEST, BusinessCriticality.TIER_3_INTERNAL)
                and blast_score <= 0.35
                and confidence_score >= 75.0
            )
            if is_safe_action:
                return True, False, "AUTONOMY L4: Authorized for autonomous execution (safe, reversible, non-critical)"
            return False, True, f"AUTONOMY L4: Action exceeds autonomous bounds ({risk_level.value}, {reversibility.value}) — requires human approval"

        # L5: Full Autonomous Execution
        if current_autonomy == AutonomyLevel.L5_FULL:
            is_critical_prod = criticality == BusinessCriticality.TIER_1_MISSION_CRITICAL or reversibility == ReversibilityType.IRREVERSIBLE
            if is_critical_prod:
                return False, True, "AUTONOMY L5: Safety ceiling — Tier-1 or irreversible modifications require human approval"
            if blast_score <= 0.60 and confidence_score >= 70.0:
                return True, False, "AUTONOMY L5: Authorized for autonomous execution within policy bounds"
            return False, True, "AUTONOMY L5: Blast radius or confidence bounds exceeded — requires approval"

        return False, True, "Approval required by default"


_evaluator_instance: Optional[MultiFactorActionEvaluator] = None


def get_action_evaluator() -> MultiFactorActionEvaluator:
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = MultiFactorActionEvaluator()
    return _evaluator_instance

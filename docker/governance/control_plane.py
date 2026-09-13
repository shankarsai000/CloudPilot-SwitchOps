"""
CloudPilot Safety & Autonomy Control Plane — Central Orchestrator.

Unifies:
- Progressive Autonomy Management & Automatic Demotion
- Multi-Factor (9-Dimension) Action Evaluation
- Policy-as-Code & Irreversibility Enforcement
- Emergency Stop (Kill Switch)
- Action Concurrency Locks & Idempotency
- Rate Limits, Budgets, & Blast Radius Limits
- Approval Routing & Human-in-the-Loop Gates
- Cryptographic Immutable Audit Trail
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from governance.approvals import ApprovalRouter, get_approval_router
from governance.audit import ImmutableAuditTrail, get_audit_trail
from governance.autonomy import AutonomyLevelManager, get_autonomy_manager
from governance.emergency import EmergencyStopManager, get_emergency_stop_manager
from governance.evaluator import MultiFactorActionEvaluator, get_action_evaluator
from governance.limits import (
    BlastRadiusGovernor,
    ExecutionBudgetTracker,
    RateLimiter,
    get_blast_radius_governor,
    get_budget_tracker,
    get_rate_limiter,
)
from governance.locks import (
    ActionLockManager,
    IdempotencyManager,
    get_action_lock_manager,
    get_idempotency_manager,
)
from governance.models import (
    ActionEvaluation,
    ApprovalRequest,
    ApprovalRoute,
    ApprovalStatus,
    AuditRecord,
    AutonomyLevel,
    ProposedAction,
    ReversibilityType,
)
from governance.policy import PolicyAsCodeEngine, get_policy_engine

logger = logging.getLogger(__name__)


class SafetyControlPlane:
    """
    Central safety governance controller.
    Validates, gates, audits, and authorizes every infrastructure change.
    """

    def __init__(
        self,
        autonomy_manager: Optional[AutonomyLevelManager] = None,
        evaluator: Optional[MultiFactorActionEvaluator] = None,
        policy_engine: Optional[PolicyAsCodeEngine] = None,
        emergency_stop: Optional[EmergencyStopManager] = None,
        lock_manager: Optional[ActionLockManager] = None,
        idempotency_manager: Optional[IdempotencyManager] = None,
        rate_limiter: Optional[RateLimiter] = None,
        budget_tracker: Optional[ExecutionBudgetTracker] = None,
        blast_governor: Optional[BlastRadiusGovernor] = None,
        approval_router: Optional[ApprovalRouter] = None,
        audit_trail: Optional[ImmutableAuditTrail] = None,
    ) -> None:
        self.autonomy = autonomy_manager or get_autonomy_manager()
        self.evaluator = evaluator or get_action_evaluator()
        self.policy = policy_engine or get_policy_engine()
        self.emergency = emergency_stop or get_emergency_stop_manager()
        self.locks = lock_manager or get_action_lock_manager()
        self.idempotency = idempotency_manager or get_idempotency_manager()
        self.rate_limiter = rate_limiter or get_rate_limiter()
        self.budget = budget_tracker or get_budget_tracker()
        self.blast = blast_governor or get_blast_radius_governor()
        self.approvals = approval_router or get_approval_router()
        self.audit = audit_trail or get_audit_trail()

    # -------------------------------------------------------------------------
    # Evaluation & Routing
    # -------------------------------------------------------------------------
    def evaluate_action(
        self,
        action: ProposedAction,
        evidence: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ActionEvaluation:
        """
        Evaluate an action against all 9 dimensions and current autonomy level.
        """
        current_lvl = self.autonomy.get_level()
        return self.evaluator.evaluate(
            action=action,
            current_autonomy=current_lvl,
            evidence=evidence,
            context_data=context,
        )

    def request_approval(
        self,
        action: ProposedAction,
        evaluation: ActionEvaluation,
        route: Optional[ApprovalRoute] = None,
        ttl_hours: Optional[int] = None,
    ) -> ApprovalRequest:
        """Create a tracked human approval request."""
        return self.approvals.create_approval_request(
            action=action,
            evaluation=evaluation,
            route=route,
            ttl_hours=ttl_hours,
        )

    def decide_approval(
        self,
        request_id: str,
        approver: str,
        role: str,
        approved: bool,
        reason: Optional[str] = None,
    ) -> Tuple[bool, Optional[ApprovalRequest], str]:
        """Submit an approval or rejection decision."""
        return self.approvals.submit_decision(
            request_id=request_id,
            approver=approver,
            role=role,
            approved=approved,
            reason=reason,
        )

    # -------------------------------------------------------------------------
    # Execution Pre-Flight Safety Verification
    # -------------------------------------------------------------------------
    def authorize_execution(
        self,
        action: ProposedAction,
        evaluation: Optional[ActionEvaluation] = None,
        approval_request_id: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, ActionEvaluation]:
        """
        Comprehensive pre-flight authorization check across all safety subsystems.
        Returns (is_authorized, reason, evaluation).
        """
        # 1. Emergency Stop Check
        if self.emergency.is_stopped(environment=action.environment, service=action.target_service):
            stop_reason = self.emergency.get_stop_reason(action.environment, action.target_service)
            eval_res = evaluation or self.evaluate_action(action, evidence, context)
            return False, f"EXECUTION BLOCKED: {stop_reason}", eval_res

        # 2. Evaluate 9 dimensions if not provided
        eval_res = evaluation or self.evaluate_action(action, evidence, context)

        # 3. Autonomy Level L0-L2 Gate (Immediate Denial)
        current_lvl = self.autonomy.get_level()
        if current_lvl in (AutonomyLevel.L0_OBSERVE, AutonomyLevel.L1_RECOMMEND, AutonomyLevel.L2_SIMULATE):
            return False, f"DENIED: Autonomy level {current_lvl.value} does not permit execution ({eval_res.verdict_reason})", eval_res

        # 4. Strict Irreversibility Rule: No irreversible action may execute without an approved human request
        if eval_res.reversibility == ReversibilityType.IRREVERSIBLE:
            if not approval_request_id:
                return False, "DENIED: Irreversible action strictly requires human approval request", eval_res

        # 5. Policy violations check
        if not eval_res.policy_report.is_compliant:
            violation_text = ", ".join(eval_res.policy_report.policy_violations)
            # Severe policy violation triggers automatic demotion
            self.autonomy.trigger_policy_violation_demotion(violation_text)
            return False, f"POLICY VIOLATION: {violation_text}", eval_res

        # 6. Check resource lock
        if self.locks.is_locked(action.target_resource_id):
            lock = self.locks.get_lock(action.target_resource_id)
            holder = lock.held_by if lock else "unknown"
            return False, f"RESOURCE LOCKED: Target {action.target_resource_id} is locked by operation '{holder}'", eval_res

        # 7. Check idempotency (duplicate execution prevention)
        idempotency_key = self.idempotency.generate_key(
            action_type=action.action_type,
            target_resource_id=action.target_resource_id,
            parameters=action.parameters,
        )
        cached = self.idempotency.check_idempotency(idempotency_key)
        if cached:
            return False, f"IDEMPOTENCY CONFLICT: Duplicate action already executed with status '{cached.status}'", eval_res

        # 8. Check Rate Limit
        rate_ok, rate_msg = self.rate_limiter.check_rate_limit(action.environment)
        if not rate_ok:
            return False, rate_msg, eval_res

        # 9. Check Execution Budget
        is_destruct = eval_res.reversibility == ReversibilityType.IRREVERSIBLE
        budget_ok, budget_msg = self.budget.check_budget(
            cost_impact_usd=action.estimated_cost_impact_usd,
            destruction_count=1 if is_destruct else 0,
        )
        if not budget_ok:
            return False, budget_msg, eval_res

        # 10. Check Blast Radius Limit
        is_auto = eval_res.can_auto_execute and not approval_request_id
        blast_ok, blast_msg = self.blast.check_blast_radius(
            dependent_services_count=eval_res.dependent_services_count,
            blast_radius_score=eval_res.blast_radius_score,
            is_autonomous=is_auto,
        )
        if not blast_ok:
            return False, blast_msg, eval_res

        # 11. Approval Verification or Autonomy Execution Check
        if approval_request_id:
            req = self.approvals.get_request(approval_request_id)
            if not req:
                return False, f"APPROVAL ERROR: Request '{approval_request_id}' not found", eval_res
            if req.status == ApprovalStatus.EXPIRED:
                return False, f"APPROVAL EXPIRED: Request '{approval_request_id}' has expired and cannot be used", eval_res
            if req.status == ApprovalStatus.CONFLICTED:
                return False, f"APPROVAL CONFLICTED: Conflicting decisions detected for '{approval_request_id}'", eval_res
            if req.status != ApprovalStatus.APPROVED:
                return False, f"APPROVAL REQUIRED: Request status is '{req.status.value}', not APPROVED", eval_res
            return True, f"Authorized by human approval ({req.required_route.value})", eval_res

        # Otherwise, check if current autonomy level permits autonomous execution
        if eval_res.can_auto_execute:
            return True, f"Authorized for autonomous execution under {current_lvl.value}", eval_res

        return False, f"APPROVAL REQUIRED: Action requires human approval under {current_lvl.value} ({eval_res.required_approval.value})", eval_res

    # -------------------------------------------------------------------------
    # Safe Execution Wrapper
    # -------------------------------------------------------------------------
    def execute_with_safety_guards(
        self,
        action: ProposedAction,
        execution_callable: Callable[[], Dict[str, Any]],
        actor: str = "CloudPilot-Autonomous-Agent",
        objective: str = "Autonomous Infrastructure Optimization",
        plan: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        code: Optional[str] = None,
        approval_request_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Dict[str, Any], Optional[AuditRecord]]:
        """
        Executes an action wrapped in all safety mechanisms:
        Lock acquisition -> Pre-flight Authorization -> Execution -> Outcome Tracking ->
        Automatic Demotion check -> Idempotency caching -> Cryptographic Audit record.
        """
        # 1. Pre-flight Authorization
        authorized, auth_reason, evaluation = self.authorize_execution(
            action=action,
            approval_request_id=approval_request_id,
            evidence=evidence,
            context=context,
        )

        if not authorized:
            # Audit the rejection
            audit_entry = self.audit.record_action(
                actor=actor,
                objective=objective,
                plan=plan,
                evidence=evidence,
                policy_evaluation=evaluation.policy_report.model_dump(mode="json"),
                approval={"status": "REJECTED_BY_SAFETY_GUARD", "reason": auth_reason},
                code=code,
                execution_result={"status": "AUTHORIZATION_DENIED", "error": auth_reason},
            )
            return False, {"status": "DENIED", "error": auth_reason}, audit_entry

        # 2. Acquire resource lock
        lock = self.locks.acquire_lock(
            resource_id=action.target_resource_id,
            action_type=action.action_type,
            held_by=actor,
        )
        if not lock:
            err = f"Failed to acquire lock for resource {action.target_resource_id}"
            return False, {"status": "LOCK_FAILED", "error": err}, None

        # 3. Execute callable under safety envelope
        exec_success = False
        exec_result: Dict[str, Any] = {}
        try:
            exec_result = execution_callable() or {}
            exec_success = exec_result.get("status") in ("SUCCESS", "OK", "APPLIED") or exec_result.get("exit_code") == 0
            if "status" not in exec_result:
                exec_result["status"] = "SUCCESS" if exec_success else "COMPLETED"
        except Exception as err:
            logger.exception("Error during execution of action %s", action.action_id)
            exec_success = False
            exec_result = {"status": "ERROR", "error": str(err)}
        finally:
            # Always release lock
            self.locks.release_lock(action.target_resource_id, held_by=actor)

        # 4. Update Rate Limits and Budgets upon execution
        self.rate_limiter.record_action(action.environment)
        self.budget.record_spend(
            cost_impact_usd=action.estimated_cost_impact_usd,
            destruction_count=1 if evaluation.reversibility == ReversibilityType.IRREVERSIBLE else 0,
        )

        # 5. Update Idempotency Cache
        idempotency_key = self.idempotency.generate_key(
            action_type=action.action_type,
            target_resource_id=action.target_resource_id,
            parameters=action.parameters,
        )
        self.idempotency.record_execution(
            idempotency_key=idempotency_key,
            action_id=action.action_id,
            status="SUCCESS" if exec_success else "FAILED",
            result_data=exec_result,
        )

        # 6. Update Demotion Metrics & Check for Demotion Triggers
        if exec_success:
            self.autonomy.demotion_controller.record_success(evaluation.confidence_score)
        else:
            self.autonomy.demotion_controller.record_failure(exec_result.get("error", "Execution failure"))

        # Apply automatic demotion if thresholds exceeded
        demotion_event = self.autonomy.check_and_apply_automatic_demotion()

        # 7. Record Cryptographic Hash-Chained Audit Block
        approval_meta = None
        if approval_request_id:
            req = self.approvals.get_request(approval_request_id)
            if req:
                approval_meta = req.model_dump(mode="json")

        audit_entry = self.audit.record_action(
            actor=actor,
            objective=objective,
            plan=plan,
            evidence=evidence,
            policy_evaluation=evaluation.policy_report.model_dump(mode="json"),
            approval=approval_meta,
            code=code,
            execution_result={
                **exec_result,
                "demotion_triggered": demotion_event.model_dump(mode="json") if demotion_event else None,
            },
        )

        return exec_success, exec_result, audit_entry


_control_plane_instance: Optional[SafetyControlPlane] = None


def get_safety_control_plane() -> SafetyControlPlane:
    global _control_plane_instance
    if _control_plane_instance is None:
        _control_plane_instance = SafetyControlPlane()
    return _control_plane_instance

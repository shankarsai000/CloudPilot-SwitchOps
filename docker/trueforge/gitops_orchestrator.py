"""
Controlled GitOps Execution Orchestrator.

Bridges TrueForge Autonomous Agent recommendations and AWS discoveries with
the 6-stage GitOps declarative delivery engine (Plan -> Review -> Approval -> Apply -> Verify -> Rollback).

Enforces:
1. Declarative Terraform state modifications only (no ad-hoc runtime shell/CLI mutations).
2. Static policy validation and blast radius evaluation.
3. Strict approval checkpoints with cryptographic audit hashes.
4. Concurrency locking during apply.
5. 5-dimension outcome verification.
6. Deterministic automated rollback upon any metric regression or SLA breach.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from typing import Any, Dict, List, Optional
import uuid

from governance.control_plane import get_safety_control_plane
from governance.models import ProposedAction
from providers.gitops_terraform import (
    GitOpsExecutionRecord,
    GitOpsPlan,
    GitOpsStage,
    GitOpsTerraformEngine,
    get_gitops_engine,
)
from providers.models import CloudProvider, ProviderError, ReadOnlyViolationError
from trueforge.aws_agent import AWSCostOptimizationCandidate

logger = logging.getLogger("cloudpilot.trueforge.gitops_orchestrator")


class ControlledGitOpsOrchestrator:
    """
    Orchestrates the 6-stage declarative GitOps lifecycle for CloudPilot agent missions.
    """

    def __init__(
        self,
        gitops_engine: Optional[GitOpsTerraformEngine] = None,
    ) -> None:
        self.engine = gitops_engine or get_gitops_engine()
        self.safety_plane = get_safety_control_plane()
        logger.info("ControlledGitOpsOrchestrator initialized with 6-stage GitOps lifecycle engine")

    # -------------------------------------------------------------------------
    # Stage 1: Plan Formulation
    # -------------------------------------------------------------------------
    def plan_from_candidate(
        self,
        candidate: AWSCostOptimizationCandidate,
        workspace: str = "production-core",
        provider: CloudProvider = CloudProvider.AWS,
    ) -> GitOpsExecutionRecord:
        """Formulate a GitOpsPlan from an AWS Read-Only Agent optimization candidate."""
        record = self.engine.stage_plan(
            workspace=workspace,
            provider=provider,
            target_resource=candidate.resource_id,
            action=candidate.action_type,
            hcl_diff=candidate.gitops_remediation_hcl,
            estimated_cost_delta=-candidate.estimated_monthly_savings,
            resources_to_add=0,
            resources_to_change=1,
            resources_to_destroy=0,
        )
        logger.info("Formulated GitOps Plan %s for %s", record.plan.plan_id, candidate.resource_id)
        return record

    def plan_from_action(
        self,
        action: ProposedAction,
        workspace: str = "cloudpilot-infra",
        provider: CloudProvider = CloudProvider.KUBERNETES,
        hcl_diff: Optional[str] = None,
    ) -> GitOpsExecutionRecord:
        """Formulate a GitOpsPlan from a TrueForge ProposedAction."""
        record = self.engine.stage_plan(
            workspace=workspace,
            provider=provider,
            target_resource=action.target_resource_id,
            action=action.action_type,
            hcl_diff=hcl_diff or f"# Scaled {action.target_resource_id} via GitOps",
            estimated_cost_delta=action.estimated_cost_impact_usd,
            resources_to_add=0,
            resources_to_change=1,
            resources_to_destroy=0,
        )
        logger.info("Formulated GitOps Plan %s for action %s", record.plan.plan_id, action.action_id)
        return record

    # -------------------------------------------------------------------------
    # Stage 2: Static Review & Policy Linting
    # -------------------------------------------------------------------------
    def review_plan(self, plan_id: str) -> GitOpsExecutionRecord:
        """Execute syntax check, drift detection, and static policy validation."""
        return self.engine.stage_review(plan_id)

    # -------------------------------------------------------------------------
    # Stage 3: Approval Gating
    # -------------------------------------------------------------------------
    def evaluate_approval_gate(
        self,
        plan_id: str,
        operator: str = "cloudpilot-agent",
        force_auto: bool = False,
    ) -> GitOpsExecutionRecord:
        """Pass plan through CloudPilot Safety Control Plane to determine approval requirement."""
        return self.engine.stage_approval(plan_id=plan_id, operator=operator, force_auto=force_auto)

    def approve_or_reject(
        self,
        plan_id: str,
        decision: str,  # "APPROVED" or "REJECTED"
        operator: str = "operator@cloudpilot.ai",
        reason: str = "Operator sign-off via GitOps Orchestrator",
    ) -> GitOpsExecutionRecord:
        """Record explicit human operator decision for gated plan."""
        return self.engine.record_human_decision(
            plan_id=plan_id,
            decision=decision,
            operator=operator,
            reason=reason,
        )

    # -------------------------------------------------------------------------
    # Stage 4: Controlled Apply
    # -------------------------------------------------------------------------
    def apply_plan(
        self,
        plan_id: str,
        operator: str = "cloudpilot-gitops-runner",
    ) -> GitOpsExecutionRecord:
        """
        Execute Terraform Apply under concurrency locks and safety guardrails.
        Guards: Read-only providers (e.g. AWS) raise ReadOnlyViolationError if attempted directly.
        """
        return self.engine.stage_apply(plan_id=plan_id, operator=operator)

    # -------------------------------------------------------------------------
    # Stage 5: Outcome Verification
    # -------------------------------------------------------------------------
    def verify_outcome(self, plan_id: str) -> GitOpsExecutionRecord:
        """Run post-apply 5-dimension outcome verification."""
        return self.engine.stage_verify(plan_id=plan_id)

    # -------------------------------------------------------------------------
    # Stage 6: Deterministic Rollback
    # -------------------------------------------------------------------------
    def rollback_plan(
        self,
        plan_id: str,
        reason: str = "Automated SLA preservation rollback",
    ) -> GitOpsExecutionRecord:
        """Execute deterministic rollback by reverting state snapshot."""
        return self.engine.stage_rollback(plan_id=plan_id, reason=reason)

    # -------------------------------------------------------------------------
    # Complete Pipeline Runner
    # -------------------------------------------------------------------------
    def run_pipeline(
        self,
        plan_id: str,
        auto_approve: bool = False,
        operator: str = "operator@cloudpilot.ai",
        simulate_failure_trigger_rollback: bool = False,
    ) -> GitOpsExecutionRecord:
        """
        Execute the full 6-stage lifecycle sequentially:
        Plan -> Review -> Approval -> Apply -> Verify -> (Rollback if needed).
        """
        # 1. Review
        record = self.review_plan(plan_id)

        # 2. Approval
        record = self.evaluate_approval_gate(plan_id, operator=operator, force_auto=auto_approve)
        if record.approval_status == "PENDING_HUMAN_APPROVAL":
            if auto_approve:
                record = self.approve_or_reject(plan_id, "APPROVED", operator=operator)
            else:
                logger.info("Pipeline paused: Plan %s is PENDING_HUMAN_APPROVAL", plan_id)
                return record

        if record.approval_status != "APPROVED":
            logger.warning("Pipeline halted: Plan %s was %s", plan_id, record.approval_status)
            return record

        # 3. Apply
        record = self.apply_plan(plan_id, operator=operator)

        # 4. Verify
        record = self.verify_outcome(plan_id)

        # 5. Rollback if regression detected or simulated
        verification_status = record.verification_report.get("overall_status") if record.verification_report else "UNKNOWN"
        needs_rollback = simulate_failure_trigger_rollback or (verification_status in ("BREACH_SLO", "REGRESSION"))

        if needs_rollback:
            logger.warning("Triggering automated rollback for plan %s due to verification verdict: %s", plan_id, verification_status)
            record = self.rollback_plan(plan_id, reason="SLA breach detected during outcome verification")

        return record


# Global singleton
_gitops_orchestrator: Optional[ControlledGitOpsOrchestrator] = None


def get_gitops_orchestrator() -> ControlledGitOpsOrchestrator:
    """Get or create singleton ControlledGitOpsOrchestrator."""
    global _gitops_orchestrator
    if _gitops_orchestrator is None:
        _gitops_orchestrator = ControlledGitOpsOrchestrator()
    return _gitops_orchestrator

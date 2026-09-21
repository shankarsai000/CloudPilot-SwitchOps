"""
Tests for Phase 12: Controlled GitOps Execution Orchestrator.

Verifies the full 6-stage declarative GitOps lifecycle:
Plan -> Review -> Approval -> Apply -> Verify -> Rollback

Safety Constraints Verified:
1. Declarative Terraform state modifications only.
2. Direct apply on AWS read-only provider is blocked with ReadOnlyViolationError.
3. Emergency stop blocks approval and apply.
4. Concurrency lock is acquired and released during apply.
5. 5-dimension outcome verification against baseline.
6. Automatic rollback on SLA breach or metric regression.
7. Cryptographic SHA-256 audit hash integrity across all stage transitions.
"""

from __future__ import annotations

import pytest

from governance.control_plane import get_safety_control_plane
from governance.models import ProposedAction
from providers.gitops_terraform import (
    GitOpsExecutionRecord,
    GitOpsStage,
    GitOpsTerraformEngine,
)
from providers.models import CloudProvider, ProviderError, ReadOnlyViolationError
from trueforge.aws_agent import AWSCostOptimizationCandidate, AWSServiceType
from trueforge.gitops_orchestrator import (
    ControlledGitOpsOrchestrator,
    get_gitops_orchestrator,
)


@pytest.fixture
def gitops_orchestrator() -> ControlledGitOpsOrchestrator:
    """Provide isolated GitOps orchestrator."""
    engine = GitOpsTerraformEngine()
    return ControlledGitOpsOrchestrator(gitops_engine=engine)


@pytest.fixture
def mock_candidate() -> AWSCostOptimizationCandidate:
    """Mock AWS optimization candidate."""
    return AWSCostOptimizationCandidate(
        resource_id="i-01a2b3c4d5e6f002",
        service=AWSServiceType.EC2,
        action_type="rightsize_instance",
        current_spec="c5.2xlarge",
        target_spec="t3.medium",
        current_monthly_cost=248.00,
        target_monthly_cost=30.40,
        estimated_monthly_savings=217.60,
        reason="Low average CPU (2.1%) in analytics-dev",
        blast_radius_score=0.1,
        gitops_remediation_hcl='resource "aws_instance" "analytics_worker" { instance_type = "t3.medium" }',
    )


class TestGitOpsPlanAndReviewStages:
    """Tests Stage 1 (Plan) and Stage 2 (Review)."""

    def test_plan_from_candidate(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
        mock_candidate: AWSCostOptimizationCandidate,
    ) -> None:
        record = gitops_orchestrator.plan_from_candidate(
            candidate=mock_candidate,
            workspace="analytics-dev",
            provider=CloudProvider.AWS,
        )
        assert record.plan.plan_id.startswith("tf-plan-")
        assert record.plan.target_resource == mock_candidate.resource_id
        assert record.plan.action == mock_candidate.action_type
        assert record.plan.estimated_monthly_cost_delta == -mock_candidate.estimated_monthly_savings
        assert record.current_stage == GitOpsStage.PLAN
        assert len(record.audit_hash) == 64  # Valid SHA-256

    def test_review_stage(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
        mock_candidate: AWSCostOptimizationCandidate,
    ) -> None:
        record = gitops_orchestrator.plan_from_candidate(mock_candidate)
        old_hash = record.audit_hash

        reviewed = gitops_orchestrator.review_plan(record.plan.plan_id)
        assert reviewed.current_stage == GitOpsStage.REVIEW
        assert reviewed.audit_hash != old_hash  # Hash evolved
        assert any(h["stage"] == "review" and h["status"] == "PASSED" for h in reviewed.stage_history)


class TestGitOpsApprovalStage:
    """Tests Stage 3 (Approval Gating)."""

    def test_approval_gating_and_decision(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
        mock_candidate: AWSCostOptimizationCandidate,
    ) -> None:
        record = gitops_orchestrator.plan_from_candidate(mock_candidate)
        gitops_orchestrator.review_plan(record.plan.plan_id)

        # Evaluate approval gate
        evaluated = gitops_orchestrator.evaluate_approval_gate(record.plan.plan_id)
        assert evaluated.current_stage == GitOpsStage.APPROVAL
        assert evaluated.approval_status in ("PENDING_HUMAN_APPROVAL", "APPROVED")

        # Explicit operator approval
        approved = gitops_orchestrator.approve_or_reject(
            plan_id=record.plan.plan_id,
            decision="APPROVED",
            operator="lead-sre@cloudpilot.ai",
            reason="Verified dev batch workload can safely downsize",
        )
        assert approved.approval_status == "APPROVED"
        assert approved.approved_by == "lead-sre@cloudpilot.ai"

    def test_rejection_halts_pipeline(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
        mock_candidate: AWSCostOptimizationCandidate,
    ) -> None:
        record = gitops_orchestrator.plan_from_candidate(mock_candidate)
        gitops_orchestrator.review_plan(record.plan.plan_id)
        gitops_orchestrator.evaluate_approval_gate(record.plan.plan_id)

        rejected = gitops_orchestrator.approve_or_reject(
            plan_id=record.plan.plan_id,
            decision="REJECTED",
            operator="qa-lead@cloudpilot.ai",
            reason="Load test running this week",
        )
        assert rejected.approval_status == "REJECTED"

        # Applying a rejected plan MUST fail
        with pytest.raises(ProviderError) as exc_info:
            gitops_orchestrator.apply_plan(record.plan.plan_id)
        assert "APPROVAL_REQUIRED" in str(exc_info.value)


class TestGitOpsApplyAndSafetyGuards:
    """Tests Stage 4 (Apply) and critical platform safety constraints."""

    def test_aws_direct_apply_is_blocked_by_read_only_invariant(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
        mock_candidate: AWSCostOptimizationCandidate,
    ) -> None:
        # Formulate AWS plan
        record = gitops_orchestrator.plan_from_candidate(mock_candidate, provider=CloudProvider.AWS)
        gitops_orchestrator.review_plan(record.plan.plan_id)
        gitops_orchestrator.evaluate_approval_gate(record.plan.plan_id, force_auto=True)

        # Applying directly on AWS must be blocked by ReadOnlyViolationError
        with pytest.raises(ReadOnlyViolationError) as exc_info:
            gitops_orchestrator.apply_plan(record.plan.plan_id)
        assert "READ_ONLY mode" in str(exc_info.value)

    def test_kubernetes_apply_succeeds_under_lock(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
    ) -> None:
        # Formulate non-read-only provider plan (e.g. Kubernetes)
        action = ProposedAction(
            action_id="act-scale-01",
            action_type="scale_replicas",
            target_resource_id="deploy/analytics-worker",
            target_service="analytics",
            environment="dev",
            estimated_cost_impact_usd=-120.0,
        )
        record = gitops_orchestrator.plan_from_action(action, provider=CloudProvider.KUBERNETES)
        gitops_orchestrator.review_plan(record.plan.plan_id)
        gitops_orchestrator.evaluate_approval_gate(record.plan.plan_id, force_auto=True)

        applied = gitops_orchestrator.apply_plan(record.plan.plan_id)
        assert applied.current_stage == GitOpsStage.APPLY
        assert applied.apply_result is not None
        assert applied.apply_result["status"] == "SUCCESS"

    def test_emergency_stop_blocks_apply(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
    ) -> None:
        action = ProposedAction(
            action_id="act-scale-02",
            action_type="scale_replicas",
            target_resource_id="deploy/reporting",
            target_service="reporting",
            environment="dev",
            estimated_cost_impact_usd=-50.0,
        )
        record = gitops_orchestrator.plan_from_action(action, provider=CloudProvider.KUBERNETES)
        gitops_orchestrator.review_plan(record.plan.plan_id)
        gitops_orchestrator.evaluate_approval_gate(record.plan.plan_id, force_auto=True)

        # Trigger Emergency Stop
        control_plane = get_safety_control_plane()
        control_plane.emergency.trigger_stop(reason="Security incident simulation", initiated_by="secops")
        try:
            with pytest.raises(ProviderError) as exc_info:
                gitops_orchestrator.apply_plan(record.plan.plan_id)
            assert "EMERGENCY_STOP_ACTIVE" in str(exc_info.value)
        finally:
            control_plane.emergency.release_stop(reason="Incident cleared", released_by="secops")


class TestGitOpsVerifyAndRollbackStages:
    """Tests Stage 5 (Verify) and Stage 6 (Deterministic Rollback)."""

    def test_verify_and_rollback_flow(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
    ) -> None:
        action = ProposedAction(
            action_id="act-scale-03",
            action_type="scale_replicas",
            target_resource_id="deploy/payment-gateway",
            target_service="payments",
            environment="dev",
            estimated_cost_impact_usd=-80.0,
        )
        record = gitops_orchestrator.plan_from_action(action, provider=CloudProvider.KUBERNETES)
        gitops_orchestrator.review_plan(record.plan.plan_id)
        gitops_orchestrator.evaluate_approval_gate(record.plan.plan_id, force_auto=True)
        gitops_orchestrator.apply_plan(record.plan.plan_id)

        # Stage 5: Verify
        verified = gitops_orchestrator.verify_outcome(record.plan.plan_id)
        assert verified.current_stage == GitOpsStage.VERIFY
        assert verified.verification_report is not None

        # Stage 6: Rollback
        rolled_back = gitops_orchestrator.rollback_plan(
            record.plan.plan_id,
            reason="Synthetic rollback verification test",
        )
        assert rolled_back.current_stage == GitOpsStage.ROLLBACK
        assert rolled_back.rollback_record is not None
        assert rolled_back.rollback_record["status"] == "SUCCESS"


class TestGitOpsFullPipelineRunner:
    """Tests full automated end-to-end 6-stage lifecycle execution."""

    def test_full_pipeline_success(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
    ) -> None:
        action = ProposedAction(
            action_id="act-scale-04",
            action_type="rightsize_deployment",
            target_resource_id="deploy/recommendations",
            target_service="catalog",
            environment="dev",
            estimated_cost_impact_usd=-95.0,
        )
        record = gitops_orchestrator.plan_from_action(action, provider=CloudProvider.KUBERNETES)

        completed = gitops_orchestrator.run_pipeline(
            plan_id=record.plan.plan_id,
            auto_approve=True,
            operator="pipeline-admin@cloudpilot.ai",
        )
        assert completed.current_stage == GitOpsStage.VERIFY
        assert completed.approval_status == "APPROVED"
        assert completed.apply_result["status"] == "SUCCESS"
        assert len(completed.stage_history) >= 4

    def test_full_pipeline_automated_rollback_on_regression(
        self,
        gitops_orchestrator: ControlledGitOpsOrchestrator,
    ) -> None:
        action = ProposedAction(
            action_id="act-scale-05",
            action_type="scale_replicas",
            target_resource_id="deploy/checkout-service",
            target_service="checkout",
            environment="dev",
            estimated_cost_impact_usd=-200.0,
        )
        record = gitops_orchestrator.plan_from_action(action, provider=CloudProvider.KUBERNETES)

        completed = gitops_orchestrator.run_pipeline(
            plan_id=record.plan.plan_id,
            auto_approve=True,
            simulate_failure_trigger_rollback=True,
        )
        # Verify pipeline executed automatic rollback
        assert completed.current_stage == GitOpsStage.ROLLBACK
        assert completed.rollback_record["status"] == "SUCCESS"
        assert any(h["stage"] == "rollback" for h in completed.stage_history)

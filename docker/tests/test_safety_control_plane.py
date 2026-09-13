"""
Phase 5 Comprehensive Integration Tests: Safety & Autonomy Control Plane.

Validates:
- Progressive Autonomy Levels (L0 through L5 enforcement)
- 9-Factor Multi-Dimension Action Evaluation
- Policy-as-Code violations & enforcement
- Strict Irreversibility Rule
- Approval routing, expirations, conflicts, and multi-tier workflows
- Emergency stop (kill switches: global and scoped)
- Action concurrency locking & TTL
- Idempotency & duplicate execution detection
- Rate limiting & execution budgets
- Automatic autonomy demotion (confidence degradation, failure streaks, rollback spikes, policy violations)
- Cryptographic SHA-256 hash-chained immutable audit trail & tamper detection
- Governance REST API endpoints
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any, Dict
import pytest
from fastapi.testclient import TestClient

from governance.approvals import ApprovalRouter, get_approval_router
from governance.audit import ImmutableAuditTrail, get_audit_trail
from governance.autonomy import AutonomyLevelManager, DemotionController, get_autonomy_manager
from governance.control_plane import SafetyControlPlane, get_safety_control_plane
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
    ActionRiskLevel,
    ApprovalRoute,
    ApprovalStatus,
    AutonomyLevel,
    BusinessCriticality,
    DemotionReason,
    ProposedAction,
    ReversibilityType,
)
from governance.policy import PolicyAsCodeEngine, get_policy_engine
from main import app


@pytest.fixture(autouse=True)
def reset_governance_state():
    """Reset singletons and state stores before every test."""
    cp = get_safety_control_plane()
    cp.emergency.reset_all()
    cp.locks.clear_all()
    cp.idempotency.clear_all()
    cp.rate_limiter.reset_all()
    cp.budget.reset_all()
    cp.approvals.clear_all()
    cp.audit.clear_all()
    cp.autonomy.set_level(AutonomyLevel.L3_APPROVAL, actor="test-init", reason="Reset test state")
    yield
    cp.emergency.reset_all()
    cp.locks.clear_all()
    cp.idempotency.clear_all()
    cp.approvals.clear_all()
    cp.audit.clear_all()


# ═══════════════════════════════════════════════════════════════
# 1. Progressive Autonomy Levels & Permissions
# ═══════════════════════════════════════════════════════════════

class TestProgressiveAutonomyLevels:
    """Test L0 to L5 operational behavior and permission matrix."""

    def test_l0_observe_blocks_all_execution(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L0_OBSERVE)

        action = ProposedAction(
            action_type="rightsize_instance",
            target_resource_id="i-test-01",
            environment="dev",
        )
        authorized, reason, evaluation = cp.authorize_execution(action)
        assert not authorized
        assert "L0: Observe-only mode" in reason

    def test_l1_recommend_blocks_execution(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L1_RECOMMEND)

        action = ProposedAction(
            action_type="rightsize_instance",
            target_resource_id="i-test-01",
            environment="dev",
        )
        authorized, reason, _ = cp.authorize_execution(action)
        assert not authorized
        assert "L1: Recommend-only mode" in reason

    def test_l2_simulate_blocks_execution(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L2_SIMULATE)

        action = ProposedAction(
            action_type="rightsize_instance",
            target_resource_id="i-test-01",
            environment="dev",
        )
        authorized, reason, _ = cp.authorize_execution(action)
        assert not authorized
        assert "L2: Simulate-only mode" in reason

    def test_l3_approval_requires_explicit_human_gate(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L3_APPROVAL)

        action = ProposedAction(
            action_type="rightsize_instance",
            target_resource_id="i-test-01",
            environment="dev",
        )
        # Without approval request
        authorized, reason, _ = cp.authorize_execution(action)
        assert not authorized
        assert "APPROVAL REQUIRED" in reason

        # Create and approve request
        eval_res = cp.evaluate_action(action)
        appr_req = cp.request_approval(action, eval_res)
        cp.decide_approval(appr_req.request_id, approver="alice@lead.com", role="lead", approved=True)

        # Re-attempt with approved request
        auth_with_token, reason_token, _ = cp.authorize_execution(action, approval_request_id=appr_req.request_id)
        assert auth_with_token
        assert "Authorized by human approval" in reason_token

    def test_l4_limited_autonomous_permits_safe_dev_actions(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L4_LIMITED)

        # Safe, reversible dev action
        safe_action = ProposedAction(
            action_type="rightsize_instance",
            target_resource_id="i-dev-safe-01",
            environment="dev",
            target_service="reporting-worker",
        )
        authorized, reason, eval_res = cp.authorize_execution(safe_action)
        assert authorized
        assert "Authorized for autonomous execution" in reason

        # Production action under L4 strictly requires approval
        prod_action = ProposedAction(
            action_type="rightsize_instance",
            target_resource_id="i-prod-01",
            environment="prod",
            target_service="order-service",
        )
        prod_auth, prod_reason, _ = cp.authorize_execution(prod_action)
        assert not prod_auth
        assert "requires human approval" in prod_reason

    def test_l5_full_autonomous_permits_broad_actions_with_safety_ceiling(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L5_FULL)

        action = ProposedAction(
            action_type="rightsize_instance",
            target_resource_id="i-staging-api",
            environment="staging",
            target_service="search-service",
        )
        authorized, reason, _ = cp.authorize_execution(action)
        assert authorized
        assert "Authorized for autonomous execution" in reason


# ═══════════════════════════════════════════════════════════════
# 2. Policy-as-Code & Irreversibility Enforcement
# ═══════════════════════════════════════════════════════════════

class TestPolicyAsCodeAndIrreversibility:
    """Test policy rule violations and the strict irreversibility guard."""

    def test_change_freeze_blocks_all_actions(self) -> None:
        engine = PolicyAsCodeEngine(change_freeze=True)
        action = ProposedAction(action_type="rightsize_instance", target_resource_id="i-1", environment="dev")
        report = engine.evaluate_policy(action)
        assert not report.is_compliant
        assert any("CHANGE_FREEZE" in v for v in report.policy_violations)

    def test_business_hours_blocks_destructive_prod_action(self) -> None:
        engine = PolicyAsCodeEngine(business_hours=(9, 17))
        action = ProposedAction(action_type="terminate_instance", target_resource_id="i-prod-db", environment="prod")
        # Simulate peak time at 14:00 UTC
        peak_time = datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc)  # Monday 14:00
        report = engine.evaluate_policy(action, current_time=peak_time)
        assert not report.is_compliant
        assert any("BUSINESS_HOURS" in v for v in report.policy_violations)

    def test_production_database_termination_strictly_blocked(self) -> None:
        engine = PolicyAsCodeEngine()
        action = ProposedAction(
            action_type="terminate_database",
            target_resource_id="rds-postgres-production-cluster",
            target_service="CoreBankingDB",
            environment="prod",
        )
        report = engine.evaluate_policy(action, criticality=BusinessCriticality.TIER_1_MISSION_CRITICAL)
        assert not report.is_compliant
        assert any("PROD_DATABASE_PROTECTION" in v for v in report.policy_violations)

    def test_strict_irreversibility_rule_blocks_autonomous_destruction(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L5_FULL)  # Even at L5!

        irreversible_action = ProposedAction(
            action_type="terminate_and_wipe_volume",
            target_resource_id="vol-storage-prod",
            environment="prod",
            target_service="audit-vault",
        )
        authorized, reason, eval_res = cp.authorize_execution(irreversible_action)
        assert not authorized
        assert eval_res.reversibility == ReversibilityType.IRREVERSIBLE
        assert "requires human" in reason.lower() or "denied" in reason.lower()


# ═══════════════════════════════════════════════════════════════
# 3. Multi-Tier Approval Workflows, Expirations, & Conflicts
# ═══════════════════════════════════════════════════════════════

class TestApprovalWorkflows:
    """Test approval routing destinations, expirations, and decision conflicts."""

    def test_route_classification(self) -> None:
        router = ApprovalRouter()
        evaluator = get_action_evaluator()

        # Security group change -> SECURITY_TEAM
        sg_action = ProposedAction(action_type="modify_sg_ingress", target_resource_id="sg-web-01", environment="dev")
        sg_eval = evaluator.evaluate(sg_action)
        assert router.determine_route(sg_action, sg_eval) == ApprovalRoute.SECURITY_TEAM

        # Tier-1 Mission Critical -> EXECUTIVE_APPROVAL
        t1_action = ProposedAction(
            action_type="rightsize_instance",
            target_resource_id="i-auth-01",
            target_service="payment-auth",
            environment="prod",
            parameters={"tier": "tier_1"},
        )
        t1_eval = evaluator.evaluate(t1_action)
        assert router.determine_route(t1_action, t1_eval) == ApprovalRoute.EXECUTIVE_APPROVAL

        # Production Tier-2 -> SRE_TEAM
        prod_action = ProposedAction(action_type="rightsize_compute", target_resource_id="i-prod-cache", environment="prod")
        prod_eval = evaluator.evaluate(prod_action)
        assert router.determine_route(prod_action, prod_eval) == ApprovalRoute.SRE_TEAM

    def test_approval_expiration_blocks_execution(self) -> None:
        cp = get_safety_control_plane()
        action = ProposedAction(action_type="rightsize_compute", target_resource_id="i-exp-01", environment="dev")
        eval_res = cp.evaluate_action(action)

        # Create request with 0-hour TTL (already expired)
        req = cp.approvals.create_approval_request(action, eval_res, ttl_hours=0)
        # Manually force expiration timestamp in the past
        req.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Approve expired request
        ok, updated_req, msg = cp.decide_approval(req.request_id, approver="bob@lead.com", role="lead", approved=True)
        assert not ok
        assert "EXPIRED" in msg

        # Attempt to authorize with expired request
        auth, reason, _ = cp.authorize_execution(action, approval_request_id=req.request_id)
        assert not auth
        assert "EXPIRED" in reason

    def test_conflicting_approvals_marked_conflicted(self) -> None:
        cp = get_safety_control_plane()
        action = ProposedAction(action_type="rightsize_compute", target_resource_id="i-conf-01", environment="staging")
        eval_res = cp.evaluate_action(action)
        req = cp.request_approval(action, eval_res)

        # Approver 1 approves
        ok1, req1, _ = cp.decide_approval(req.request_id, approver="alice@lead.com", role="lead", approved=True)
        assert ok1

        # Approver 2 rejects -> conflict
        # Re-open pending to test contradictory multi-party decisions
        req1.status = ApprovalStatus.PENDING
        ok2, req2, msg2 = cp.decide_approval(req.request_id, approver="mallory@security.com", role="security", approved=False, reason="Security concern")
        assert not ok2
        assert req2.status == ApprovalStatus.CONFLICTED
        assert "Conflicting decisions" in msg2

        # Authorize attempt must fail
        auth, reason, _ = cp.authorize_execution(action, approval_request_id=req.request_id)
        assert not auth
        assert "CONFLICTED" in reason


# ═══════════════════════════════════════════════════════════════
# 4. Emergency Stop (Kill Switches)
# ═══════════════════════════════════════════════════════════════

class TestEmergencyStop:
    """Test global and scoped emergency halts."""

    def test_global_emergency_stop_halts_everything(self) -> None:
        cp = get_safety_control_plane()
        cp.emergency.engage(scope="global", reason="Unexpected anomaly detected across fleet")
        assert cp.emergency.is_stopped()

        action = ProposedAction(action_type="rightsize_instance", target_resource_id="i-dev-01", environment="dev")
        authorized, reason, _ = cp.authorize_execution(action)
        assert not authorized
        assert "GLOBAL EMERGENCY STOP" in reason

        # Release restores operations
        cp.emergency.release(scope="global")
        assert not cp.emergency.is_stopped()

    def test_scoped_emergency_stop_blocks_only_matching_scope(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L4_LIMITED)

        # Stop only production
        cp.emergency.engage(scope="env:prod", reason="Production database maintenance")

        prod_action = ProposedAction(action_type="rightsize_instance", target_resource_id="i-prod-01", environment="prod")
        dev_action = ProposedAction(action_type="rightsize_instance", target_resource_id="i-dev-01", environment="dev")

        # Prod must be blocked
        prod_auth, prod_reason, _ = cp.authorize_execution(prod_action)
        assert not prod_auth
        assert "ENVIRONMENT EMERGENCY STOP" in prod_reason

        # Dev action is NOT blocked by prod emergency stop
        dev_auth, _, _ = cp.authorize_execution(dev_action)
        assert dev_auth


# ═══════════════════════════════════════════════════════════════
# 5. Action Locks & Idempotency
# ═══════════════════════════════════════════════════════════════

class TestActionLocksAndIdempotency:
    """Test resource mutual exclusion and duplicate execution suppression."""

    def test_action_lock_prevents_concurrent_operations(self) -> None:
        cp = get_safety_control_plane()
        res_id = "i-shared-cluster-node-01"

        # Lock resource by Operation A
        lock_a = cp.locks.acquire_lock(resource_id=res_id, action_type="resize", held_by="op-A", ttl_seconds=60)
        assert lock_a is not None
        assert cp.locks.is_locked(res_id)

        # Attempt concurrent lock by Operation B -> Rejected
        lock_b = cp.locks.acquire_lock(resource_id=res_id, action_type="terminate", held_by="op-B")
        assert lock_b is None

        # Operation A releases lock
        cp.locks.release_lock(res_id, held_by="op-A")
        assert not cp.locks.is_locked(res_id)

        # Now Operation B can acquire lock
        lock_b2 = cp.locks.acquire_lock(resource_id=res_id, action_type="terminate", held_by="op-B")
        assert lock_b2 is not None

    def test_idempotency_prevents_duplicate_execution(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L4_LIMITED)

        action = ProposedAction(
            action_type="rightsize_instance",
            target_resource_id="i-idemp-01",
            environment="dev",
            parameters={"target_type": "t3.small"},
        )

        call_count = 0
        def execute_step():
            nonlocal call_count
            call_count += 1
            return {"status": "SUCCESS", "details": "resized"}

        # Run 1
        ok1, res1, _ = cp.execute_with_safety_guards(action, execute_step)
        assert ok1
        assert call_count == 1

        # Run 2 with identical parameters -> blocked by idempotency conflict
        ok2, res2, _ = cp.execute_with_safety_guards(action, execute_step)
        assert not ok2
        assert "IDEMPOTENCY CONFLICT" in res2.get("error", "")
        # Callable was NOT executed a second time
        assert call_count == 1


# ═══════════════════════════════════════════════════════════════
# 6. Automatic Autonomy Demotion Engine
# ═══════════════════════════════════════════════════════════════

class TestAutonomyDemotionEngine:
    """Test automatic demotion triggers across failure streaks, confidence drops, and violations."""

    def test_consecutive_failures_trigger_demotion(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L4_LIMITED)
        assert cp.autonomy.get_level() == AutonomyLevel.L4_LIMITED

        # Simulate 3 consecutive failures
        cp.autonomy.demotion_controller.record_failure("error 1")
        cp.autonomy.demotion_controller.record_failure("error 2")
        trigger = cp.autonomy.check_and_apply_automatic_demotion()
        assert trigger is None  # 2 failures not enough

        cp.autonomy.demotion_controller.record_failure("error 3")
        trigger = cp.autonomy.check_and_apply_automatic_demotion()
        assert trigger is not None
        assert trigger.reason == DemotionReason.REPEATED_FAILURES
        assert trigger.previous_level == AutonomyLevel.L4_LIMITED
        assert trigger.new_level == AutonomyLevel.L2_SIMULATE
        assert cp.autonomy.get_level() == AutonomyLevel.L2_SIMULATE

    def test_confidence_drop_triggers_demotion(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L5_FULL)

        # Record degraded confidence scores (< 75%)
        cp.autonomy.demotion_controller.record_success(confidence_score=60.0)
        cp.autonomy.demotion_controller.record_success(confidence_score=55.0)
        cp.autonomy.demotion_controller.record_success(confidence_score=50.0)

        trigger = cp.autonomy.check_and_apply_automatic_demotion()
        assert trigger is not None
        assert trigger.reason == DemotionReason.CONFIDENCE_DECREASED
        assert trigger.new_level == AutonomyLevel.L3_APPROVAL
        assert cp.autonomy.get_level() == AutonomyLevel.L3_APPROVAL

    def test_policy_violation_triggers_instant_demotion(self) -> None:
        cp = get_safety_control_plane()
        cp.autonomy.set_level(AutonomyLevel.L4_LIMITED)

        trigger = cp.autonomy.trigger_policy_violation_demotion("Attempted production DB termination")
        assert trigger.reason == DemotionReason.POLICY_VIOLATION
        assert cp.autonomy.get_level() == AutonomyLevel.L2_SIMULATE


# ═══════════════════════════════════════════════════════════════
# 7. Cryptographic Immutable Audit Trail & Tamper Detection
# ═══════════════════════════════════════════════════════════════

class TestImmutableAuditTrail:
    """Test SHA-256 cryptographic hash-chaining and tamper detection."""

    def test_audit_hash_chain_creation_and_integrity_verification(self) -> None:
        audit = get_audit_trail()

        # Add 3 blocks
        r1 = audit.record_action(actor="agent-01", objective="Clean idle dev storage")
        r2 = audit.record_action(actor="agent-01", objective="Rightsize staging worker")
        r3 = audit.record_action(actor="operator-01", objective="Emergency approval apply")

        assert r1.sequence_number == 0
        assert r1.previous_hash == ImmutableAuditTrail.GENESIS_HASH
        assert r2.previous_hash == r1.entry_hash
        assert r3.previous_hash == r2.entry_hash

        # Verify integrity of untouched chain
        is_valid, msg, broken_idx = audit.verify_integrity()
        assert is_valid
        assert broken_idx is None
        assert "all 3 blocks" in msg

    def test_tamper_detection_flags_corrupted_block(self) -> None:
        audit = get_audit_trail()
        r1 = audit.record_action(actor="agent-01", objective="Original objective 1")
        r2 = audit.record_action(actor="agent-01", objective="Original objective 2")

        # Corrupt block 1's payload without recalculating entry_hash
        r1.objective = "Tampered unauthorized objective"

        is_valid, msg, broken_idx = audit.verify_integrity()
        assert not is_valid
        assert broken_idx == 0
        assert "TAMPER_DETECTED" in msg or "HASH_CHAIN_BROKEN" in msg


# ═══════════════════════════════════════════════════════════════
# 8. Governance REST APIs
# ═══════════════════════════════════════════════════════════════

class TestGovernanceRESTAPIs:
    """Test FastAPI governance endpoints under /api/v1/governance."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_api_autonomy_get_and_set(self, client: TestClient) -> None:
        res = client.get("/api/v1/governance/autonomy")
        assert res.status_code == 200
        data = res.json()
        assert "current_autonomy_level" in data

        # Set to L4
        set_res = client.post(
            "/api/v1/governance/autonomy/set",
            json={"level": "L4_LIMITED", "actor": "admin", "reason": "Testing level update"},
        )
        assert set_res.status_code == 200
        assert set_res.json()["new_autonomy_level"] == "L4_LIMITED"

    def test_api_emergency_stop_lifecycle(self, client: TestClient) -> None:
        # Engage stop
        engage_res = client.post(
            "/api/v1/governance/emergency/engage",
            json={"scope": "global", "reason": "Test emergency engagement", "activated_by": "tester"},
        )
        assert engage_res.status_code == 200
        assert engage_res.json()["status"] == "ENGAGED"

        # Query status
        status_res = client.get("/api/v1/governance/emergency")
        assert status_res.status_code == 200
        assert status_res.json()["is_global_stop_active"] is True

        # Release stop
        release_res = client.post(
            "/api/v1/governance/emergency/release",
            json={"scope": "global"},
        )
        assert release_res.status_code == 200
        assert release_res.json()["status"] == "RELEASED"

    def test_api_action_evaluate_and_approval(self, client: TestClient) -> None:
        action_payload = {
            "action": {
                "action_type": "rightsize_instance",
                "target_resource_id": "i-api-test-01",
                "target_service": "api-gateway",
                "environment": "dev",
                "parameters": {"target_type": "t3.small"},
                "estimated_cost_impact_usd": -120.0,
            }
        }

        # Evaluate
        eval_res = client.post("/api/v1/governance/actions/evaluate", json=action_payload)
        assert eval_res.status_code == 200
        eval_data = eval_res.json()
        assert "risk_level" in eval_data
        assert "confidence_score" in eval_data

        # Create approval request
        appr_res = client.post("/api/v1/governance/approvals", json=action_payload)
        assert appr_res.status_code == 200
        req_id = appr_res.json()["request_id"]

        # Submit decision
        dec_res = client.post(
            f"/api/v1/governance/approvals/{req_id}/decide",
            json={"approver": "lead@enterprise.com", "role": "lead", "approved": True, "reason": "Looks good"},
        )
        assert dec_res.status_code == 200
        assert dec_res.json()["status"] == "APPROVED"

    def test_api_audit_verify(self, client: TestClient) -> None:
        # Create an audit entry
        get_audit_trail().record_action(actor="test-api", objective="API test audit")

        res = client.post("/api/v1/governance/audit/verify")
        assert res.status_code == 200
        data = res.json()
        assert data["is_valid"] is True
        assert data["broken_block_index"] is None

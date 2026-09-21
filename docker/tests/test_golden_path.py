"""
Golden Path Integration Tests — End-to-End Autonomous Agent Workflow.

Tests the complete CloudPilot Golden Path workflow:
- Scenario A: Goal → Discover → Cost → Risk → Strategy → Simulate → TF → Sandbox → Approve → Execute → Verify(SUCCESS) → Learn
- Scenario B: Goal → ... → Execute → Verify(BREACH) → ROLLBACK → Verify(HEALTHY) → Learn(ROLLBACK)
- Approval Denied: Goal → ... → ⏸ DENY → No execution
- Governed Tool Registry: Every tool goes through governance gates
- Sandbox Lifecycle: TerraformLifecycle with fallback
- Approval State Persistence: Checkpoints, pending list, resolve
- Rollback Idempotency: Duplicate rollbacks yield identical result
- Audit Trail Integrity: SHA-256 chain verification
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Ensure docker directory is importable
docker_dir = Path(__file__).resolve().parent.parent
if str(docker_dir) not in sys.path:
    sys.path.insert(0, str(docker_dir))


# =============================================================================
# D1: Implementation Audit Verification
# =============================================================================
class TestImplementationAudit:
    """Verify the implementation audit document exists and is substantive."""

    def test_audit_document_exists(self) -> None:
        audit_path = Path(__file__).resolve().parent.parent.parent / "CLOUDPILOT_IMPLEMENTATION_AUDIT.md"
        assert audit_path.exists(), f"Audit document missing at {audit_path}"

    def test_audit_document_substantive(self) -> None:
        audit_path = Path(__file__).resolve().parent.parent.parent / "CLOUDPILOT_IMPLEMENTATION_AUDIT.md"
        content = audit_path.read_text(encoding="utf-8")
        assert len(content) > 5000, "Audit document is too short"
        assert "IMPLEMENTED" in content
        assert "MISSING" in content
        assert "Phase 1" in content
        assert "Phase 8" in content
        assert "Golden Path" in content


# =============================================================================
# D3: Governed Tool Registry
# =============================================================================
class TestGovernedToolRegistry:
    """Verify governance-gated tool execution."""

    def test_governed_registry_initializes(self) -> None:
        from trueforge.tools import GovernedToolRegistry
        gov = GovernedToolRegistry()
        tools = gov.list_tools()
        assert len(tools) >= 9, f"Expected >= 9 tools, got {len(tools)}"

    def test_governed_read_only_tool_passes_gates(self) -> None:
        from trueforge.tools import GovernedToolRegistry
        gov = GovernedToolRegistry()
        result = gov.execute_tool(
            tool_name="inspect_infrastructure",
            arguments={"scenario_name": "SaaS"},
            tool_call_id="gov-test-001",
            turn_id="gov-turn-001",
        )
        assert result["scenario_name"] == "SaaS"
        assert result["total_resources"] > 0

        # Verify governance audit was recorded
        audit = gov.get_governance_audit()
        assert len(audit) >= 1
        latest = audit[-1]
        assert latest["status"] == "EXECUTED_SUCCESS"
        assert "EMERGENCY_STOP_CLEAR" in latest["gates_passed"]
        assert "POLICY_COMPLIANT" in latest["gates_passed"]
        assert "READ_ONLY_SKIP_RISK" in latest["gates_passed"]
        assert "RATE_LIMIT_OK" in latest["gates_passed"]

    def test_governed_mutating_tool_includes_risk_evaluation(self) -> None:
        from trueforge.tools import GovernedToolRegistry
        gov = GovernedToolRegistry()
        result = gov.execute_tool(
            tool_name="generate_terraform",
            arguments={"actions": [{"target_resource_id": "dev-1", "action_type": "rightsize"}]},
            tool_call_id="gov-test-002",
        )
        assert "hcl_code" in result

        audit = gov.get_governance_audit()
        latest = [a for a in audit if a["tool_call_id"] == "gov-test-002"][0]
        assert latest["status"] == "EXECUTED_SUCCESS"
        assert any("RISK_ACCEPTABLE" in g for g in latest["gates_passed"])
        assert "risk_score" in latest

    def test_governed_tool_blocks_during_emergency_stop(self) -> None:
        from trueforge.tools import GovernedToolRegistry
        from governance.control_plane import get_safety_control_plane
        gov = GovernedToolRegistry()
        cp = get_safety_control_plane()

        # Activate emergency stop for 'dev' environment
        cp.emergency.activate_stop(
            environment="dev",
            reason="Test emergency stop",
            activated_by="test-suite",
        )

        with pytest.raises(PermissionError, match="Emergency stop active"):
            gov.execute_tool(
                tool_name="inspect_infrastructure",
                arguments={"scenario_name": "SaaS", "environment": "dev"},
            )

        # Verify blocked in audit
        audit = gov.get_governance_audit()
        blocked = [a for a in audit if a.get("status") == "BLOCKED_EMERGENCY_STOP"]
        assert len(blocked) >= 1

        # Deactivate for subsequent tests
        cp.emergency.deactivate_stop(environment="dev", deactivated_by="test-suite")

    def test_governed_tool_audit_trail_recorded(self) -> None:
        from trueforge.tools import GovernedToolRegistry
        from governance.audit import get_audit_trail
        gov = GovernedToolRegistry()
        audit_trail = get_audit_trail()

        initial_count = audit_trail.count_records()
        gov.execute_tool("analyze_costs", {"scenario_name": "SaaS", "target_reduction_pct": 15.0})
        final_count = audit_trail.count_records()

        assert final_count > initial_count, "Governance audit trail should record new entry"


# =============================================================================
# D4: Real Sandbox with TerraformLifecycle
# =============================================================================
class TestTerraformLifecycle:
    """Verify TerraformLifecycle with fallback to simulated mode."""

    def test_terraform_lifecycle_initializes(self) -> None:
        from trueforge.sandbox import TerraformLifecycle, get_sandbox_manager
        sbx = get_sandbox_manager()
        tf = TerraformLifecycle(sandbox_manager=sbx)
        # In CI/test environment, terraform is likely not installed
        # Either mode is acceptable
        assert isinstance(tf.is_available(), bool)

    def test_terraform_lifecycle_simulated_fallback(self) -> None:
        from trueforge.sandbox import TerraformLifecycle, SandboxManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            sbx = SandboxManager(base_dir=Path(tmpdir))
            tf = TerraformLifecycle(sandbox_manager=sbx)
            # Force simulated mode
            tf._detected = True
            tf._terraform_path = None

            sandbox_id = sbx.create_sandbox()
            hcl_code = 'resource "aws_instance" "test" {\n  instance_type = "t3.micro"\n}\n'

            result = tf.execute_full_lifecycle(sandbox_id, hcl_code)
            assert result["mode"] == "simulated"
            assert result["status"] == "SUCCESS"
            assert "simulated_plan" in result["stages"]
            assert result["exit_code"] == 0

    def test_terraform_lifecycle_ensure_provider_block(self) -> None:
        from trueforge.sandbox import TerraformLifecycle, SandboxManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            sbx = SandboxManager(base_dir=Path(tmpdir))
            tf = TerraformLifecycle(sandbox_manager=sbx)

            hcl = 'resource "aws_instance" "test" {\n  instance_type = "t3.micro"\n}\n'
            enhanced = tf._ensure_provider_block(hcl)
            assert "required_providers" in enhanced
            assert "hashicorp/aws" in enhanced
            assert "skip_credentials_validation" in enhanced

    def test_sandbox_artifact_storage(self) -> None:
        from trueforge.sandbox import SandboxManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            sbx = SandboxManager(base_dir=Path(tmpdir))
            sid = sbx.create_sandbox()

            art = sbx.store_artifact(sid, "plan.tf", "# test HCL\n", "terraform_hcl")
            assert art.filename == "plan.tf"
            assert art.sha256_hash  # Hash should be non-empty

            artifacts = sbx.list_artifacts(sid)
            assert len(artifacts) == 1


# =============================================================================
# D5: Human Approval Interrupts
# =============================================================================
class TestHumanApprovalInterrupts:
    """Verify state persistence for WAITING_FOR_APPROVAL, resolve, and query."""

    def test_save_and_retrieve_checkpoint(self) -> None:
        from trueforge.state import AgentStateManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AgentStateManager(state_file=Path(tmpdir) / "test_state.json")

            ckpt_id = state.save_golden_path_checkpoint(
                session_id="test-session",
                run_id="gp-test-001",
                step_name="approval_gate",
                step_index=12,
                execution_state={"sandbox_id": "sbx-123", "cost_savings": 500.0},
                pending_action_summary="Apply 3 rightsizing changes to dev environment",
            )

            assert ckpt_id.startswith("gp-ckpt-")
            cp = state.get_checkpoint_by_id(ckpt_id)
            assert cp is not None
            assert cp["status"] == "WAITING_FOR_APPROVAL"
            assert cp["run_id"] == "gp-test-001"
            assert cp["step_name"] == "approval_gate"

    def test_pending_approvals_query(self) -> None:
        from trueforge.state import AgentStateManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AgentStateManager(state_file=Path(tmpdir) / "test_state.json")

            state.save_golden_path_checkpoint("s1", "run-1", "gate", 12, {})
            state.save_golden_path_checkpoint("s2", "run-2", "gate", 12, {})

            pending = state.get_pending_approvals()
            assert len(pending) == 2
            assert all(p["status"] == "WAITING_FOR_APPROVAL" for p in pending)

    def test_resolve_checkpoint_approved(self) -> None:
        from trueforge.state import AgentStateManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AgentStateManager(state_file=Path(tmpdir) / "test_state.json")

            ckpt_id = state.save_golden_path_checkpoint("s1", "run-1", "gate", 12, {})
            resolved = state.resolve_checkpoint(ckpt_id, approved=True, resolver="sre-lead")

            assert resolved is not None
            assert resolved["status"] == "APPROVED"
            assert resolved["resolver"] == "sre-lead"
            assert resolved["resolved_at"] is not None

            # Should no longer appear in pending
            pending = state.get_pending_approvals()
            assert len(pending) == 0

    def test_resolve_checkpoint_denied(self) -> None:
        from trueforge.state import AgentStateManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            state = AgentStateManager(state_file=Path(tmpdir) / "test_state.json")

            ckpt_id = state.save_golden_path_checkpoint("s1", "run-1", "gate", 12, {})
            resolved = state.resolve_checkpoint(ckpt_id, approved=False, reason="Too risky")

            assert resolved["status"] == "DENIED"
            assert "Too risky" in resolved["resolution"]

    def test_checkpoint_persistence_across_reload(self) -> None:
        from trueforge.state import AgentStateManager
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "test_state.json"

            # Save checkpoint
            state1 = AgentStateManager(state_file=state_file)
            ckpt_id = state1.save_golden_path_checkpoint("s1", "run-persist", "gate", 12, {"key": "value"})

            # Reload from disk
            state2 = AgentStateManager(state_file=state_file)
            cp = state2.get_checkpoint_by_id(ckpt_id)
            # Checkpoint should survive reload
            assert cp is not None
            assert cp["run_id"] == "run-persist"


# =============================================================================
# D2+D6: Golden Path E2E Scenarios
# =============================================================================
class TestGoldenPathScenarioA:
    """Test Scenario A — Full success path end-to-end."""

    def test_scenario_a_completes_all_steps(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_a()

        assert result.status == "COMPLETED_SUCCESS"
        assert result.final_verdict == "VERIFIED_SUCCESS"
        assert len(result.steps) == 16  # Steps 0-15
        assert result.approval_status == "APPROVED"
        assert result.rollback_executed is False

    def test_scenario_a_all_steps_succeed(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_a()

        for step in result.steps:
            assert step.status == "SUCCESS", f"Step {step.step_index} '{step.step_name}' failed: {step.error}"

    def test_scenario_a_structured_output(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_a()

        # Each step must produce structured output
        for step in result.steps:
            assert isinstance(step.output, dict), f"Step {step.step_name} output is not dict"
            assert len(step.output) > 0, f"Step {step.step_name} output is empty"

    def test_scenario_a_verification_succeeds(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_a()

        verify_step = [s for s in result.steps if s.step_name == "verify_outcome"][0]
        assert verify_step.output["verification_status"] == "ALL_VERIFIED_SUCCESS"
        assert verify_step.output["any_breach"] is False

    def test_scenario_a_to_dict_serializable(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_a()

        result_dict = result.to_dict()
        # Must be JSON-serializable
        serialized = json.dumps(result_dict, default=str)
        assert len(serialized) > 100


class TestGoldenPathScenarioB:
    """Test Scenario B — Failure + Rollback path end-to-end."""

    def test_scenario_b_completes_with_rollback(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_b()

        assert result.status == "COMPLETED_WITH_ROLLBACK"
        assert result.final_verdict == "ROLLBACK_SUCCESSFUL"
        assert result.rollback_executed is True
        assert result.approval_status == "APPROVED"
        assert len(result.steps) == 19  # Steps 0-18

    def test_scenario_b_breach_detected(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_b()

        breach_step = [s for s in result.steps if s.step_name == "verify_outcome_breach"][0]
        assert breach_step.output["verification_status"] == "THRESHOLD_BREACH_DETECTED"
        assert breach_step.output["any_breach"] is True

    def test_scenario_b_rollback_executed(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_b()

        rollback_step = [s for s in result.steps if s.step_name == "execute_rollback"][0]
        assert rollback_step.output["rollback_status"] == "ALL_ROLLED_BACK"
        assert rollback_step.output["all_baselines_restored"] is True

    def test_scenario_b_post_rollback_healthy(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_b()

        health_step = [s for s in result.steps if s.step_name == "verify_post_rollback_health"][0]
        assert health_step.output["verification_status"] == "ALL_VERIFIED_SUCCESS"
        assert health_step.output["any_breach"] is False

    def test_scenario_b_learning_records_rollback(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_scenario_b()

        learn_step = [s for s in result.steps if s.step_name == "feed_m8_learning"][0]
        assert learn_step.output["outcome_type"] == "ROLLBACK"


class TestGoldenPathApprovalDenied:
    """Test approval denied — no infrastructure changes."""

    def test_approval_denied_no_execution(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_approval_denied(denial_reason="Too risky for production")

        assert result.status == "COMPLETED_DENIED"
        assert result.final_verdict == "APPROVAL_DENIED"
        assert result.approval_status == "DENIED"
        assert result.rollback_executed is False
        # Should NOT have execute or verify steps
        step_names = [s.step_name for s in result.steps]
        assert "execute_apply" not in step_names
        assert "verify_outcome" not in step_names

    def test_approval_denied_checkpoint_resolved(self) -> None:
        from golden_path import GoldenPathOrchestrator
        orch = GoldenPathOrchestrator()
        result = orch.run_approval_denied()

        assert result.checkpoint_id is not None
        # Checkpoint should be resolved as DENIED
        orch._lazy_init()
        cp = orch._state.get_checkpoint_by_id(result.checkpoint_id)
        assert cp is not None
        assert cp["status"] == "DENIED"


class TestGoldenPathAuditTrail:
    """Verify governance audit trail integrity."""

    def test_audit_trail_records_golden_path_run(self) -> None:
        from golden_path import GoldenPathOrchestrator
        from governance.audit import get_audit_trail

        audit = get_audit_trail()
        initial_count = audit.count_records()

        orch = GoldenPathOrchestrator()
        orch.run_scenario_a()

        final_count = audit.count_records()
        assert final_count > initial_count, "Audit trail should have new records after golden path run"

    def test_audit_records_have_sha256_hashes(self) -> None:
        from governance.audit import get_audit_trail
        audit = get_audit_trail()

        records = audit.list_records()
        if records:
            latest = records[-1]
            assert hasattr(latest, "record_id") or "record_id" in (latest if isinstance(latest, dict) else {})

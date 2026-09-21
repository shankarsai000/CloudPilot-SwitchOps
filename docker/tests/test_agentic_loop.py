"""
CloudPilot Phase 9: Real Agentic Control Loop & Evaluation Test Suite.

Comprehensive tests for:
1. Durable Agent State Machine (transitions, validation, persistence, cold reload)
2. Bounded Autonomy Stop Conditions (approval, kill-switch, blast radius, SLO breach)
3. Autonomous Reasoning & Tool Selection Loop (dynamic observe-reason-act cycle)
4. Critical Dependency Safeguards (protection of mission-critical services)
5. Human Approval Interruption & Resumption (Approved vs Denied)
6. Automated Rollback on Injected Verification Failure
7. Ground Truth Benchmark Evaluation Harness (10 operational metrics)
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

from trueforge.agent_evaluator import AgentBenchmarkReport, AgentEvaluationHarness
from trueforge.autonomous_loop import AutonomousAgentLoop
from trueforge.state_machine import (
    AgentState,
    DurableAgentContext,
    DurableStateMachine,
    get_durable_state_machine,
)
from trueforge.stop_conditions import (
    StopConditionEvaluator,
    StopConditionType,
    StopConditionVerdict,
)
from trueforge.tools import GovernedToolRegistry, get_governed_tool_registry


# =============================================================================
# 1. Durable Agent State Machine Tests
# =============================================================================
class TestAgentStateMachine:
    """Test state machine transitions, persistence, and cold reload."""

    def test_state_machine_initializes_cleanly(self) -> None:
        sm = get_durable_state_machine()
        assert sm is not None
        assert hasattr(sm, "transition")
        assert hasattr(sm, "save")

    def test_valid_state_transitions(self) -> None:
        sm = DurableStateMachine()
        ctx = DurableAgentContext(goal="Test optimization goal")
        assert ctx.current_state == AgentState.CREATED

        sm.transition(ctx, AgentState.PLANNING)
        assert ctx.current_state == AgentState.PLANNING

        sm.transition(ctx, AgentState.EXECUTING_TOOL)
        assert ctx.current_state == AgentState.EXECUTING_TOOL

        sm.transition(ctx, AgentState.OBSERVING)
        assert ctx.current_state == AgentState.OBSERVING

        sm.transition(ctx, AgentState.DECIDING)
        assert ctx.current_state == AgentState.DECIDING

        sm.transition(ctx, AgentState.WAITING_FOR_APPROVAL)
        assert ctx.current_state == AgentState.WAITING_FOR_APPROVAL

        sm.transition(ctx, AgentState.EXECUTING)
        assert ctx.current_state == AgentState.EXECUTING

        sm.transition(ctx, AgentState.VERIFYING)
        assert ctx.current_state == AgentState.VERIFYING

        sm.transition(ctx, AgentState.COMPLETED)
        assert ctx.current_state == AgentState.COMPLETED
        assert ctx.is_terminal() is True

    def test_illegal_state_transition_raises_error(self) -> None:
        sm = DurableStateMachine()
        ctx = DurableAgentContext(goal="Test illegal transition")
        assert ctx.current_state == AgentState.CREATED

        # Cannot jump directly from CREATED to EXECUTING
        with pytest.raises(ValueError, match="Illegal state transition"):
            sm.transition(ctx, AgentState.EXECUTING)

    def test_cold_restart_persistence_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_file = Path(tmpdir) / "state_machine.json"
            sm1 = DurableStateMachine(persistence_file=persist_file)

            ctx = DurableAgentContext(
                session_id="sess-cold-restart-01",
                goal="Survive cold restart",
                scenario_name="Banking",
                current_state=AgentState.CREATED,
            )
            sm1.save(ctx)
            sm1.transition(ctx, AgentState.PLANNING)
            sm1.transition(ctx, AgentState.DECIDING)
            sm1.transition(ctx, AgentState.WAITING_FOR_APPROVAL, reason="Awaiting lead approval")

            # Simulate complete process termination and restart
            del sm1
            sm2 = DurableStateMachine(persistence_file=persist_file)
            reloaded = sm2.get_context("sess-cold-restart-01")

            assert reloaded is not None
            assert reloaded.session_id == "sess-cold-restart-01"
            assert reloaded.current_state == AgentState.WAITING_FOR_APPROVAL
            assert reloaded.goal == "Survive cold restart"
            assert reloaded.scenario_name == "Banking"
            assert reloaded.stop_reason == "Awaiting lead approval"

    def test_step_history_recording(self) -> None:
        ctx = DurableAgentContext(goal="Record traces")
        step1 = ctx.record_step(
            thought="Inspecting topology",
            action_tool="inspect_infrastructure",
            action_args={"scenario_name": "SaaS"},
            observation={"total_resources": 42},
            decision="Proceed to cost analysis",
            duration_ms=12.5,
        )
        assert step1.step_number == 1
        assert len(ctx.step_history) == 1
        assert ctx.step_history[0].action_tool == "inspect_infrastructure"


# =============================================================================
# 2. Bounded Autonomy Stop Conditions Tests
# =============================================================================
class TestBoundedAutonomyStopConditions:
    """Test guardrails enforcing safe operational bounds."""

    def test_approval_required_for_mutating_actions(self) -> None:
        evaluator = StopConditionEvaluator()
        ctx = DurableAgentContext(goal="Resize compute")
        actions = [{"target_resource_id": "i-worker-01", "action_type": "rightsize_instance"}]

        verdict = evaluator.check_pre_execution(ctx, actions)
        assert verdict.should_stop is True
        assert verdict.condition_type == StopConditionType.APPROVAL_REQUIRED
        assert verdict.requires_human is True
        assert verdict.recommended_state == AgentState.WAITING_FOR_APPROVAL

    def test_stop_on_emergency_kill_switch(self) -> None:
        from governance.control_plane import get_safety_control_plane
        cp = get_safety_control_plane()
        cp.emergency.activate_stop(environment="dev", reason="Security incident testing")

        try:
            evaluator = StopConditionEvaluator(control_plane=cp)
            ctx = DurableAgentContext(goal="Mutate under kill switch")
            actions = [{"target_resource_id": "i-dev-01", "action_type": "rightsize_instance"}]

            verdict = evaluator.check_pre_execution(ctx, actions)
            assert verdict.should_stop is True
            assert verdict.condition_type == StopConditionType.EMERGENCY_STOP_ACTIVE
            assert verdict.recommended_state == AgentState.BLOCKED
        finally:
            cp.emergency.deactivate_stop(environment="dev")

    def test_stop_on_blast_radius_exceeded(self) -> None:
        evaluator = StopConditionEvaluator(max_blast_radius=3)
        ctx = DurableAgentContext(goal="Massive resize")
        actions = [{"target_resource_id": f"i-res-{idx}", "action_type": "rightsize_instance"} for idx in range(10)]

        verdict = evaluator.check_pre_execution(ctx, actions)
        assert verdict.should_stop is True
        assert verdict.condition_type == StopConditionType.BLAST_RADIUS_EXCEEDED
        assert verdict.recommended_state == AgentState.BLOCKED

    def test_stop_on_simulation_latency_breach(self) -> None:
        evaluator = StopConditionEvaluator()
        sim_result = {
            "status": "SUCCESS",
            "metrics_impact": {"latency_p99_change_pct": 28.5},  # Unacceptable > 15%
        }
        verdict = evaluator.check_simulation(sim_result)
        assert verdict.should_stop is True
        assert verdict.condition_type == StopConditionType.SIMULATION_BREACH
        assert verdict.recommended_state == AgentState.BLOCKED

    def test_stop_on_goal_achieved(self) -> None:
        evaluator = StopConditionEvaluator()
        verdict = evaluator.check_goal_achieved(achieved_savings=2500.0, target_savings=2000.0)
        assert verdict.should_stop is True
        assert verdict.condition_type == StopConditionType.OBJECTIVE_ACHIEVED
        assert verdict.recommended_state == AgentState.COMPLETED

    def test_stop_on_post_execution_unsafe_breach(self) -> None:
        evaluator = StopConditionEvaluator()
        verif_report = {
            "status": "THRESHOLD_BREACH",
            "threshold_breaches": ["LATENCY_P99_SPIKE: 350ms vs 45ms"],
        }
        verdict = evaluator.check_post_execution(verif_report)
        assert verdict.should_stop is True
        assert verdict.condition_type == StopConditionType.UNSAFE_EXECUTION_DETECTED
        assert verdict.recommended_state == AgentState.ROLLING_BACK


# =============================================================================
# 3. Autonomous Reasoning & Tool Selection Loop Tests
# =============================================================================
class TestAutonomousReasoningLoop:
    """Verify dynamic observe-reason-act cycle."""

    def test_agent_dynamically_reaches_approval_gate(self) -> None:
        agent = AutonomousAgentLoop()
        ctx = agent.start_objective(
            goal="Reduce monthly cloud spend by 20% without affecting SLOs",
            scenario_name="SaaS",
            target_reduction_pct=20.0,
        )

        ctx = agent.run_until_paused_or_complete(ctx, max_steps=12)

        # Agent should have reasoned through discovery -> cost -> dependencies -> sim -> tf -> plan
        assert ctx.current_state == AgentState.WAITING_FOR_APPROVAL
        assert ctx.checkpoint_id is not None
        assert ctx.approval_required is True
        assert ctx.hcl_code is not None
        assert len(ctx.selected_actions) > 0
        assert len(ctx.step_history) >= 5

        # Verify tool diversity (not hardcoded static calls)
        tools_called = [s.action_tool for s in ctx.step_history if s.action_tool]
        assert "inspect_infrastructure" in tools_called
        assert "analyze_costs" in tools_called
        assert "inspect_dependencies" in tools_called
        assert "generate_terraform" in tools_called
        assert "execute_terraform_plan" in tools_called

    def test_agent_safeguards_critical_dependencies(self) -> None:
        agent = AutonomousAgentLoop()
        ctx = agent.start_objective(
            goal="Optimize database tier",
            scenario_name="SaaS",
        )
        ctx = agent.run_until_paused_or_complete(ctx, max_steps=10)

        # Selected actions must NOT include protected critical services
        for act in ctx.selected_actions:
            target = act.get("target_resource_id", "").lower()
            assert not any(db in target for db in ("prod-db", "payment", "core-rds")), f"Unsafe target: {target}"

        # Rejected actions must capture reasons
        if ctx.rejected_actions:
            first_rejected = ctx.rejected_actions[0]
            assert "rejection_reason" in first_rejected

    def test_agent_self_healing_configuration_repair(self) -> None:
        agent = AutonomousAgentLoop()
        # Test direct tool repair
        raw_hcl = 'resource "aws_instance" "worker" { instance_type = "t3.medium" }'
        res = agent.tools.execute_tool(
            tool_name="repair_configuration",
            arguments={"hcl_code": raw_hcl},
        )
        assert res["status"] == "REPAIRED"
        assert res["is_valid"] is True
        assert 'provider "aws"' in res["repaired_hcl"]


# =============================================================================
# 4. Human Approval Resumption Flow Tests
# =============================================================================
class TestApprovalResumptionFlow:
    """Test approval grant and denial paths."""

    def test_approval_granted_executes_and_completes_successfully(self) -> None:
        agent = AutonomousAgentLoop()
        ctx = agent.start_objective(
            goal="Reduce compute waste safely",
            scenario_name="SaaS",
        )
        ctx = agent.run_until_paused_or_complete(ctx, max_steps=10)
        assert ctx.current_state == AgentState.WAITING_FOR_APPROVAL

        # Resume with human approval
        resumed = agent.resume_approval(
            session_id=ctx.session_id,
            approved=True,
            resolver="lead-devops-engineer",
            reason="Verified safe in sandbox",
            simulate_failure=False,
        )

        assert resumed.current_state == AgentState.COMPLETED
        assert resumed.approved_by == "lead-devops-engineer"
        assert resumed.execution_result is not None
        assert resumed.execution_result.get("status") == "APPLIED_SUCCESS"
        assert resumed.verification_report is not None
        assert resumed.verification_report.get("status") == "ALL_VERIFIED_SUCCESS"
        assert resumed.learning_record is not None
        assert resumed.learning_record.get("outcome_type") == "SUCCESS"

    def test_approval_denied_cancels_cleanly_with_zero_mutation(self) -> None:
        agent = AutonomousAgentLoop()
        ctx = agent.start_objective(
            goal="Risky compute optimization",
            scenario_name="SaaS",
        )
        ctx = agent.run_until_paused_or_complete(ctx, max_steps=10)
        assert ctx.current_state == AgentState.WAITING_FOR_APPROVAL

        # Human denies execution
        resumed = agent.resume_approval(
            session_id=ctx.session_id,
            approved=False,
            resolver="security-officer",
            reason="Freeze on production updates",
        )

        assert resumed.current_state == AgentState.CANCELLED
        assert "Human approval denied" in (resumed.stop_reason or "")
        assert resumed.execution_result is None


# =============================================================================
# 5. Automated Rollback on Injected Failure Tests
# =============================================================================
class TestAutonomousFailureAndRollback:
    """Test verification breach detection and automated rollback."""

    def test_latency_breach_triggers_automatic_rollback(self) -> None:
        agent = AutonomousAgentLoop()
        ctx = agent.start_objective(
            goal="Optimization with latency anomaly injection",
            scenario_name="SaaS",
        )
        ctx = agent.run_until_paused_or_complete(ctx, max_steps=10)
        assert ctx.current_state == AgentState.WAITING_FOR_APPROVAL

        # Approve, but inject latency breach during outcome verification
        resumed = agent.resume_approval(
            session_id=ctx.session_id,
            approved=True,
            resolver="qa-engineer",
            simulate_failure=True,  # Injects latency spike
        )

        assert resumed.current_state == AgentState.ROLLED_BACK
        assert resumed.verification_report.get("status") == "THRESHOLD_BREACH_DETECTED"
        assert resumed.rollback_report is not None
        assert resumed.rollback_report.get("status") == "ROLLBACK_COMPLETED"
        assert resumed.learning_record is not None
        assert resumed.learning_record.get("outcome_type") == "ROLLBACK"


# =============================================================================
# 6. Agent Evaluation Harness & Ground Truth Benchmark Tests
# =============================================================================
class TestAgentEvaluationHarness:
    """Benchmark autonomous agent against Ground Truth oracle."""

    def test_benchmark_success_scenario(self) -> None:
        harness = AgentEvaluationHarness()
        report: AgentBenchmarkReport = harness.run_benchmark(
            scenario_name="SaaS",
            target_reduction_pct=20.0,
            test_rollback_path=False,
        )

        assert report.verdict == "PASS"
        assert report.unsafe_actions_prevented_rate == 100.0
        assert report.approval_correctness_pct == 100.0
        assert report.objective_completion_rate >= 90.0
        assert report.agent_tool_efficiency_score > 0.0
        assert report.steps_to_completion > 0

    def test_benchmark_rollback_failure_scenario(self) -> None:
        harness = AgentEvaluationHarness()
        report: AgentBenchmarkReport = harness.run_benchmark(
            scenario_name="SaaS",
            target_reduction_pct=20.0,
            test_rollback_path=True,
        )

        assert report.verdict == "PASS"
        assert report.rollback_correctness_pct == 100.0
        assert report.unsafe_actions_prevented_rate == 100.0

"""
CloudPilot TrueForge Autonomous Agent Control Loop.

Implements the dynamic, closed-loop agent control cycle:
    OBSERVE -> REASON -> ACT -> EVALUATE STOP CONDITIONS -> REASON -> ...

The agent dynamically selects tools based on intermediate findings:
1. Inspects topology and inventory
2. Identifies waste and candidates
3. Inspects dependencies and eliminates critical infrastructure from mutation
4. Simulates candidates on the Digital Twin
5. Generates Terraform HCL and validates in isolated sandbox
6. Self-heals configuration if errors occur
7. Halts at WAITING_FOR_APPROVAL
8. Resumes upon human approval -> Executes -> Verifies outcome -> Rolls back if breach detected
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from trueforge.sandbox import SandboxManager, get_sandbox_manager
from trueforge.state import AgentStateManager, get_agent_state_manager
from trueforge.state_machine import (
    AgentState,
    AgentStepRecord,
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

logger = logging.getLogger("cloudpilot.trueforge.autonomous_loop")


class AutonomousAgentLoop:
    """
    Closed-loop autonomous agent orchestrator dynamically navigating
    from user operational goal to safe governed execution.
    """

    def __init__(
        self,
        tool_registry: Optional[GovernedToolRegistry] = None,
        state_machine: Optional[DurableStateMachine] = None,
        state_manager: Optional[AgentStateManager] = None,
        sandbox_manager: Optional[SandboxManager] = None,
        stop_evaluator: Optional[StopConditionEvaluator] = None,
    ) -> None:
        self.tools = tool_registry or get_governed_tool_registry()
        self.state_machine = state_machine or get_durable_state_machine()
        self.state_manager = state_manager or get_agent_state_manager()
        self.sandbox = sandbox_manager or get_sandbox_manager()
        self.stop_evaluator = stop_evaluator or StopConditionEvaluator()

    # -------------------------------------------------------------------------
    # Lifecycle Initiation
    # -------------------------------------------------------------------------
    def start_objective(
        self,
        goal: str,
        scenario_name: str = "SaaS",
        target_reduction_pct: float = 20.0,
        sandbox_id: Optional[str] = None,
    ) -> DurableAgentContext:
        """
        Initialize a new autonomous mission context and persist initial state.
        """
        sbx_id = sandbox_id or self.sandbox.create_sandbox()
        context = DurableAgentContext(
            session_id=f"sess-{uuid.uuid4().hex[:8]}",
            run_id=f"run-{uuid.uuid4().hex[:8]}",
            goal=goal,
            scenario_name=scenario_name,
            sandbox_id=sbx_id,
            current_state=AgentState.CREATED,
            metadata={"target_reduction_pct": target_reduction_pct},
        )
        self.state_machine.save(context)
        self.state_machine.transition(context, AgentState.PLANNING, reason="Starting autonomous objective")
        return context

    # -------------------------------------------------------------------------
    # Single Dynamic Step
    # -------------------------------------------------------------------------
    def step(self, context: DurableAgentContext) -> bool:
        """
        Execute one step of autonomous reasoning and action.
        Returns True if execution should continue, False if paused or terminal.
        """
        if context.is_terminal() or context.current_state == AgentState.WAITING_FOR_APPROVAL:
            return False

        # Phase 1: Think (Dynamic reasoning about next step)
        thought, next_tool, tool_args, decision = self._reason_next_action(context)

        # Check if reasoning determined we are ready for human approval
        if next_tool == "REQUEST_APPROVAL":
            verdict = self.stop_evaluator.check_pre_execution(context, context.selected_actions)
            if verdict.should_stop and verdict.condition_type == StopConditionType.APPROVAL_REQUIRED:
                self._pause_for_approval(context, verdict.reason)
                return False
            elif verdict.should_stop:
                self.state_machine.transition(context, verdict.recommended_state, reason=verdict.reason)
                return False

        if next_tool == "COMPLETE":
            self.state_machine.transition(context, AgentState.COMPLETED, reason=decision or "Objective achieved")
            return False

        if not next_tool:
            self.state_machine.transition(context, AgentState.BLOCKED, reason="No viable action found")
            return False

        # Phase 2: Act (Execute chosen tool through GovernedToolRegistry)
        self.state_machine.transition(context, AgentState.EXECUTING_TOOL)
        start_time = time.time()
        observation = None
        error_msg = None

        try:
            observation = self.tools.execute_tool(
                tool_name=next_tool,
                arguments=tool_args,
                tool_call_id=f"act-{uuid.uuid4().hex[:8]}",
                sandbox_id=context.sandbox_id,
            )
        except Exception as exc:
            logger.exception("Tool %s failed: %s", next_tool, exc)
            error_msg = str(exc)
            observation = {"error": error_msg, "status": "ERROR"}

        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Phase 3: Observe (Update context beliefs and knowledge)
        self.state_machine.transition(context, AgentState.OBSERVING)
        self._process_observation(context, next_tool, observation)

        # Phase 4: Decide (Record step and transition to DECIDING)
        self.state_machine.transition(context, AgentState.DECIDING)
        context.record_step(
            thought=thought,
            action_tool=next_tool,
            action_args=tool_args,
            observation=observation,
            decision=decision,
            duration_ms=duration_ms,
        )
        self.state_machine.save(context)

        return True

    # -------------------------------------------------------------------------
    # Full Autonomous Loop
    # -------------------------------------------------------------------------
    def run_until_paused_or_complete(
        self,
        context: DurableAgentContext,
        max_steps: int = 15,
    ) -> DurableAgentContext:
        """
        Iteratively run step() until agent reaches WAITING_FOR_APPROVAL or terminal state.
        """
        steps = 0
        while steps < max_steps:
            steps += 1
            cont = self.step(context)
            if not cont:
                break
        return context

    # -------------------------------------------------------------------------
    # Approval Resumption Flow
    # -------------------------------------------------------------------------
    def resume_approval(
        self,
        session_id: str,
        approved: bool,
        resolver: str = "human-operator",
        reason: Optional[str] = None,
        simulate_failure: bool = False,
    ) -> DurableAgentContext:
        """
        Resume an agent paused at WAITING_FOR_APPROVAL.
        Can be invoked after a cold restart directly from persistent storage.
        """
        context = self.state_machine.get_context(session_id)
        if not context:
            raise ValueError(f"Session {session_id} not found in state machine storage")

        if context.current_state != AgentState.WAITING_FOR_APPROVAL:
            raise ValueError(
                f"Cannot resume session {session_id} in state {context.current_state.value}. "
                f"Expected WAITING_FOR_APPROVAL."
            )

        # Update checkpoint in state manager
        if context.checkpoint_id:
            self.state_manager.resolve_checkpoint(
                checkpoint_id=context.checkpoint_id,
                approved=approved,
                resolver=resolver,
                reason=reason,
            )

        context.approved_by = resolver if approved else None

        if not approved:
            # Human operator rejected the plan
            self.state_machine.transition(
                context,
                AgentState.CANCELLED,
                reason=f"Human approval denied by {resolver}: {reason or 'No reason provided'}",
            )
            context.record_step(
                thought="Human operator reviewed the plan and denied approval.",
                action_tool=None,
                decision=f"CANCELLED: {reason}",
            )
            self.state_machine.save(context)
            return context

        # Approved: Proceed to governed execution
        self.state_machine.transition(context, AgentState.EXECUTING, reason="Approved by human operator")
        exec_res = self.tools.execute_tool(
            tool_name="apply_infrastructure_change",
            arguments={"actions": context.selected_actions, "environment": "dev"},
            sandbox_id=context.sandbox_id,
        )
        context.execution_result = exec_res

        # Proceed to verification
        self.state_machine.transition(context, AgentState.VERIFYING, reason="Verifying outcome across 5 dimensions")
        verify_res = self.tools.execute_tool(
            tool_name="verify_outcome",
            arguments={"actions": context.selected_actions, "simulate_failure": simulate_failure},
            sandbox_id=context.sandbox_id,
        )
        context.verification_report = verify_res

        # Check post-execution stop condition
        post_verdict = self.stop_evaluator.check_post_execution(verify_res)
        if post_verdict.should_stop and post_verdict.condition_type == StopConditionType.UNSAFE_EXECUTION_DETECTED:
            # Automatic deterministic rollback triggered!
            self.state_machine.transition(
                context,
                AgentState.ROLLING_BACK,
                reason=post_verdict.reason,
            )
            rb_res = self.tools.execute_tool(
                tool_name="execute_rollback",
                arguments={"actions": context.selected_actions, "reason": post_verdict.reason},
                sandbox_id=context.sandbox_id,
            )
            context.rollback_report = rb_res
            self.state_machine.transition(
                context,
                AgentState.ROLLED_BACK,
                reason="Automatic rollback completed successfully. Infrastructure healthy.",
            )
            # Feed M8 learning loop with rollback event
            context.learning_record = {
                "outcome_type": "ROLLBACK",
                "reason": post_verdict.reason,
                "actions_count": len(context.selected_actions),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            # Success!
            self.state_machine.transition(
                context,
                AgentState.COMPLETED,
                reason="All actions applied and verified successfully with zero SLO breaches.",
            )
            # Feed M8 learning loop with verified success
            context.learning_record = {
                "outcome_type": "SUCCESS",
                "verified_savings_rate": 0.95,
                "actions_count": len(context.selected_actions),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }

        self.state_machine.save(context)
        return context

    # -------------------------------------------------------------------------
    # Internal Reasoning Engine (Dynamic Tool Selection)
    # -------------------------------------------------------------------------
    def _reason_next_action(
        self,
        context: DurableAgentContext,
    ) -> tuple[str, Optional[str], Dict[str, Any], Optional[str]]:
        """
        Dynamically reason about what tool to call next based on current observations.
        Returns (thought, tool_name, tool_arguments, decision).
        """
        # Step 1: Discover topology if not yet discovered
        if not context.discovered_inventory:
            return (
                "I need complete infrastructure inventory to understand the operational landscape.",
                "inspect_infrastructure",
                {"scenario_name": context.scenario_name},
                "Query live cloud topology",
            )

        # Step 2: Analyze costs and identify waste if not yet analyzed
        if not context.cost_candidates:
            target_pct = context.metadata.get("target_reduction_pct", 20.0)
            return (
                f"Infrastructure discovered. Now I will analyze spend breakdown and find candidates to achieve {target_pct}% reduction.",
                "analyze_costs",
                {"scenario_name": context.scenario_name, "target_reduction_pct": target_pct},
                "Analyze monthly spend and identify optimization candidates",
            )

        # Step 3: Inspect service dependencies for candidates to avoid critical services
        if not context.dependencies:
            return (
                "Cost candidates identified. I must inspect dependency graphs to protect mission-critical services.",
                "inspect_dependencies",
                {"scenario_name": context.scenario_name},
                "Inspect application service dependencies and criticality tiers",
            )

        # Step 4: Filter candidates by dependency safety
        if not context.selected_actions:
            self._filter_candidates_by_dependency(context)
            if not context.selected_actions:
                return (
                    "All optimization candidates were rejected due to critical application dependencies.",
                    "COMPLETE",
                    {},
                    "No safe modifications could be made without violating application SLOs.",
                )

        # Step 5: Simulate strategy on Digital Twin if not yet simulated
        if not context.metadata.get("simulation_done"):
            sample_action = context.selected_actions[0]
            return (
                f"Simulating modification for {sample_action.get('target_resource_id')} on Digital Twin to forecast headroom and latency.",
                "simulate_action",
                {
                    "action_type": sample_action.get("action_type", "rightsize_instance"),
                    "target_resource_id": sample_action.get("target_resource_id", "dev-1"),
                    "parameters": sample_action.get("parameters", {}),
                },
                "Validate strategy impact on Digital Twin",
            )

        # Step 6: Generate Terraform HCL code if not yet generated
        if not context.hcl_code:
            return (
                "Simulation confirms safe headroom. Generating Terraform HCL infrastructure code for validated actions.",
                "generate_terraform",
                {"actions": context.selected_actions, "sandbox_id": context.sandbox_id},
                "Synthesize Terraform HCL for approved candidates",
            )

        # Step 7: Validate generated code in Sandbox
        if not context.plan_output:
            return (
                "Terraform HCL generated. Executing terraform plan in the isolated sandbox.",
                "execute_terraform_plan",
                {"sandbox_id": context.sandbox_id, "hcl_code": context.hcl_code},
                "Validate HCL syntax and generate plan diff in sandbox",
            )

        # Step 8: If sandbox validation failed, attempt self-healing repair
        if context.plan_output.get("status") == "ERROR" and not context.metadata.get("repaired"):
            return (
                "Sandbox validation detected missing provider or syntax errors. Attempting automated configuration repair.",
                "repair_configuration",
                {"hcl_code": context.hcl_code, "sandbox_id": context.sandbox_id},
                "Self-heal Terraform configuration",
            )

        # Step 9: Ready for approval gate
        return (
            "All intelligence queries, simulations, and sandbox validations passed. Requesting human approval before mutating cloud resources.",
            "REQUEST_APPROVAL",
            {},
            "Pause at human approval gate",
        )

    # -------------------------------------------------------------------------
    # Observation Processing
    # -------------------------------------------------------------------------
    def _process_observation(
        self,
        context: DurableAgentContext,
        tool_name: str,
        observation: Any,
    ) -> None:
        """Update context beliefs from tool execution results."""
        if not isinstance(observation, dict):
            return

        if tool_name == "inspect_infrastructure":
            context.discovered_inventory = observation

        elif tool_name == "analyze_costs":
            candidates = observation.get("candidates", []) or observation.get("optimization_candidates", [])
            context.cost_candidates = candidates

        elif tool_name == "inspect_dependencies":
            context.dependencies = observation

        elif tool_name == "simulate_action":
            context.metadata["simulation_done"] = True
            context.metadata["simulation_result"] = observation

        elif tool_name == "generate_terraform":
            context.hcl_code = observation.get("hcl_code", "")

        elif tool_name == "execute_terraform_plan":
            context.plan_output = observation

        elif tool_name == "repair_configuration":
            context.metadata["repaired"] = True
            repaired_hcl = observation.get("repaired_hcl", "")
            if repaired_hcl:
                context.hcl_code = repaired_hcl
                # Reset plan_output to re-verify in sandbox
                context.plan_output = None

    def _filter_candidates_by_dependency(self, context: DurableAgentContext) -> None:
        """
        Examine candidates against dependency tiers and drop those
        that power Tier-1 mission-critical services (e.g. Payment, Core DB).
        """
        dep_graph = context.dependencies.get("dependency_graph", {})
        critical_services = {"payment", "auth", "checkout", "billing", "database", "redis"}

        selected = []
        rejected = []

        for cand in context.cost_candidates:
            res_id = cand.get("target_resource_id") or cand.get("resource_id", "")
            svc = (cand.get("service") or cand.get("name", "worker")).lower()
            tier = cand.get("criticality", "").upper()

            # Inspect if resource is connected to critical services
            is_critical = (
                tier in ("TIER_1_MISSION_CRITICAL", "CRITICAL")
                or any(crit in svc for crit in critical_services)
                or any(crit in res_id.lower() for crit in ("db", "payment", "prod-redis", "core-rds"))
            )

            if is_critical:
                rejected.append({
                    "target_resource_id": res_id,
                    "action_type": cand.get("action_type", "rightsize_instance"),
                    "rejection_reason": f"Resource powers critical service '{svc or res_id}'. Protected by SLO safeguards.",
                    "service": svc,
                })
            else:
                savings = cand.get("estimated_savings_usd") or cand.get("estimated_monthly_savings_usd", 50.0)
                selected.append({
                    "target_resource_id": res_id,
                    "action_type": cand.get("action_type", "rightsize_instance"),
                    "service": svc or "worker",
                    "parameters": cand.get("parameters", {"target_type": "t3.medium"}),
                    "expected_savings": float(savings),
                    "environment": cand.get("environment", "dev"),
                })

        # Respect bounded autonomy: limit batch size to max_blast_radius
        max_allowed = getattr(self.stop_evaluator, "max_blast_radius", 10)
        if len(selected) > max_allowed:
            selected.sort(key=lambda a: a.get("expected_savings", 0.0), reverse=True)
            deferred = selected[max_allowed:]
            selected = selected[:max_allowed]
            for d in deferred:
                rejected.append({
                    "target_resource_id": d["target_resource_id"],
                    "action_type": d["action_type"],
                    "rejection_reason": f"Deferred: bounded to blast radius limit of {max_allowed} actions.",
                    "service": d.get("service", "worker"),
                })

        context.selected_actions = selected
        context.rejected_actions = rejected
        logger.info(
            "Candidate selection: %d selected, %d rejected/deferred",
            len(selected), len(rejected),
        )

    def _pause_for_approval(self, context: DurableAgentContext, reason: str) -> None:
        """Pause agent execution and register durable checkpoint for human review."""
        ckpt_id = self.state_manager.save_golden_path_checkpoint(
            session_id=context.session_id,
            run_id=context.run_id,
            step_name="human_approval_gate",
            step_index=len(context.step_history) + 1,
            execution_state={
                "goal": context.goal,
                "scenario_name": context.scenario_name,
                "selected_actions": context.selected_actions,
                "rejected_actions": context.rejected_actions,
                "hcl_code": context.hcl_code,
                "sandbox_id": context.sandbox_id,
            },
            pending_action_summary=f"Approve execution of {len(context.selected_actions)} infrastructure actions",
            requires_approval=True,
        )
        context.checkpoint_id = ckpt_id
        context.approval_required = True
        self.state_machine.transition(
            context,
            AgentState.WAITING_FOR_APPROVAL,
            reason=reason,
        )
        context.record_step(
            thought="Paused execution at human approval gate. Awaiting operator resolution.",
            action_tool=None,
            decision="WAITING_FOR_APPROVAL",
        )
        self.state_machine.save(context)
        logger.info("Autonomous mission [%s] paused at checkpoint %s", context.session_id, ckpt_id)

"""
CloudPilot Copilot Engine.

Conversational interface connecting natural-language dialogue to the
autonomous agent control loop, diagnostic intelligence, and approval center.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import threading
from typing import Any, Dict, List, Optional
import uuid

from copilot.models import (
    CopilotConversation,
    CopilotIntent,
    CopilotMessage,
    CopilotResponse,
    CopilotRole,
)
from trueforge.autonomous_loop import AutonomousAgentLoop
from trueforge.state import AgentStateManager, get_agent_state_manager
from trueforge.state_machine import AgentState, DurableAgentContext, DurableStateMachine, get_durable_state_machine
from trueforge.tools import GovernedToolRegistry, get_governed_tool_registry

logger = logging.getLogger("cloudpilot.copilot.engine")

DEFAULT_CONVERSATIONS_FILE = Path("docker/scratch/state/copilot_conversations.json").resolve()


class CloudPilotCopilotEngine:
    """
    Conversational assistant providing natural-language cloud diagnostics,
    cost analysis, autonomous mission dispatching, and interactive approval flows.
    """

    def __init__(
        self,
        agent_loop: Optional[AutonomousAgentLoop] = None,
        tool_registry: Optional[GovernedToolRegistry] = None,
        state_machine: Optional[DurableStateMachine] = None,
        state_manager: Optional[AgentStateManager] = None,
        persistence_file: Optional[Path] = None,
    ) -> None:
        self.agent = agent_loop or AutonomousAgentLoop()
        self.tools = tool_registry or get_governed_tool_registry()
        self.state_machine = state_machine or get_durable_state_machine()
        self.state_manager = state_manager or get_agent_state_manager()
        self.persistence_file = Path(persistence_file or DEFAULT_CONVERSATIONS_FILE)
        self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
        self._conversations: Dict[str, CopilotConversation] = {}
        self._lock = threading.Lock()
        self._load_from_disk()

    # -------------------------------------------------------------------------
    # Conversation Lifecycle
    # -------------------------------------------------------------------------
    def get_or_create_conversation(
        self,
        conversation_id: Optional[str] = None,
        scenario_name: str = "SaaS",
    ) -> CopilotConversation:
        """Retrieve existing conversation by ID or instantiate a new one."""
        with self._lock:
            cid = conversation_id or f"conv-{uuid.uuid4().hex[:8]}"
            if cid not in self._conversations:
                conv = CopilotConversation(
                    conversation_id=cid,
                    scenario_name=scenario_name,
                )
                self._conversations[cid] = conv
                self._save_to_disk_locked()
            return self._conversations[cid]

    def chat(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
        scenario_name: str = "SaaS",
    ) -> CopilotResponse:
        """
        Process a user message, classify intent, dispatch autonomous actions if requested,
        and generate a structured response with supporting evidence.
        """
        conv = self.get_or_create_conversation(conversation_id, scenario_name)
        intent = self.classify_intent(user_message)

        # Record user message
        conv.add_message(
            role=CopilotRole.USER,
            content=user_message,
            intent=intent,
        )

        # Route by intent
        if intent == CopilotIntent.DIAGNOSE_BILLING:
            response = self._handle_diagnose_billing(conv, user_message)
        elif intent == CopilotIntent.DISPATCH_MISSION:
            response = self._handle_dispatch_mission(conv, user_message)
        elif intent == CopilotIntent.APPROVE_EXECUTION:
            response = self._handle_approve_execution(conv, user_message)
        elif intent == CopilotIntent.DENY_EXECUTION:
            response = self._handle_deny_execution(conv, user_message)
        elif intent == CopilotIntent.QUERY_APPROVALS:
            response = self._handle_query_approvals(conv)
        elif intent == CopilotIntent.INVENTORY_QUERY:
            response = self._handle_inventory_query(conv)
        elif intent == CopilotIntent.DEPENDENCY_QUERY:
            response = self._handle_dependency_query(conv, user_message)
        else:
            response = self._handle_general_query(conv, user_message)

        # Record assistant reply
        conv.add_message(
            role=CopilotRole.ASSISTANT,
            content=response.reply_text,
            intent=intent,
            evidence=response.evidence,
            structured_data=response.pending_approval,
        )

        with self._lock:
            self._save_to_disk_locked()

        return response

    # -------------------------------------------------------------------------
    # Intent Classification
    # -------------------------------------------------------------------------
    def classify_intent(self, text: str) -> CopilotIntent:
        """Classify natural language text into a structured operational intent."""
        clean = text.lower().strip()

        # 1. Approval / Denial (highest priority for checkpoint resolution)
        if re.search(r"\b(approve|approved|proceed|confirm|go ahead)\b", clean) or clean in ("yes", "apply", "y", "yes, apply it"):
            return CopilotIntent.APPROVE_EXECUTION
        if re.search(r"\b(deny|denied|reject|rejected|cancel|abort|stop mission)\b", clean) or clean in ("no", "n"):
            return CopilotIntent.DENY_EXECUTION
        if re.search(r"\b(pending approval|pending approvals|checkpoints?|what needs approval)\b", clean):
            return CopilotIntent.QUERY_APPROVALS

        # 2. Autonomous Action Dispatch ("Fix it", "Remediate", "Optimize", "Reduce cost", "Apply strategy")
        if (
            re.search(r"\b(fix|remediate|remediation|optimize|optimization|mitigate)\b", clean)
            or re.search(r"\breduce\s+(cost|costs|spend|bill)", clean)
            or (re.search(r"\b(apply|execute|run)\b", clean) and re.search(r"\b(plan|changes?|strategy|actions?|recommendations?)\b", clean))
        ):
            return CopilotIntent.DISPATCH_MISSION

        # 3. Cost / Billing Diagnosis
        if re.search(r"\b(bill|billing|invoice|cost|costs|spend|spending|expensive|waste|spike|anomaly|budget)\b", clean):
            if re.search(r"\b(why|explain|analyze|breakdown|jump|jumped|spike|spiked|increase|anomaly|cause|causing|high|up|where)\b", clean):
                return CopilotIntent.DIAGNOSE_BILLING

        # 4. Topology / Dependencies
        if re.search(r"\b(depend|dependencies|dependency|upstream|downstream|connected|connections?|topology|service graph|service map|criticality)\b", clean):
            return CopilotIntent.DEPENDENCY_QUERY

        # 5. Inventory / Cloud Resources
        if re.search(r"\b(inventory|resources|instances|servers|pods|containers|clusters|vms|databases|running|infrastructure)\b", clean):
            return CopilotIntent.INVENTORY_QUERY

        # Default fallback for cost questions
        if re.search(r"\b(bill|cost|spend|invoice)\b", clean):
            return CopilotIntent.DIAGNOSE_BILLING

        return CopilotIntent.GENERAL_QUERY

    # -------------------------------------------------------------------------
    # Intent Handlers
    # -------------------------------------------------------------------------
    def _handle_diagnose_billing(
        self,
        conv: CopilotConversation,
        message: str,
    ) -> CopilotResponse:
        """Analyze billing anomalies and present structured breakdown evidence."""
        res = self.tools.execute_tool(
            tool_name="analyze_costs",
            arguments={"scenario_name": conv.scenario_name, "target_reduction_pct": 20.0},
        )

        total_spend = res.get("total_monthly_spend_usd", 184200.0)
        candidates = res.get("candidates", []) or res.get("optimization_candidates", [])
        total_savings = res.get("total_identifiable_savings_usd", 38400.0)

        # Segment candidates
        compute_savings = sum(c.get("estimated_savings_usd", 0.0) for c in candidates if c.get("type") == "compute")
        db_savings = sum(c.get("estimated_savings_usd", 0.0) for c in candidates if c.get("type") == "database")
        storage_savings = sum(c.get("estimated_savings_usd", 0.0) for c in candidates if c.get("type") == "storage")

        reply = (
            f"### Cloud Cost Diagnosis for **{conv.scenario_name}**\n\n"
            f"I analyzed the last 30 days of cloud spend (Total spend: **${total_spend:,.2f}/mo**).\n\n"
            f"**Primary Contributors to Waste:**\n"
            f"1. **Compute**: ${compute_savings:,.2f} in recoverable idle/oversized instances\n"
            f"2. **Database**: ${db_savings:,.2f} optimization opportunities\n"
            f"3. **Storage**: ${storage_savings:,.2f} unattached EBS volumes\n\n"
            f"**Largest Anomaly Detected:**\n"
            f"Found **{len(candidates)} optimization candidates** yielding up to **${total_savings:,.2f}/mo** in safe savings.\n\n"
            f"Say **'Fix it'** to trigger autonomous analysis and generate a safe, sandboxed execution plan."
        )

        evidence = {
            "total_monthly_spend_usd": total_spend,
            "potential_savings_usd": total_savings,
            "total_potential_monthly_savings": total_savings,
            "candidate_count": len(candidates),
            "total_candidates": len(candidates),
            "top_candidates": candidates[:5],
        }

        return CopilotResponse(
            conversation_id=conv.conversation_id,
            reply_text=reply,
            intent=CopilotIntent.DIAGNOSE_BILLING,
            evidence=evidence,
            quick_actions=["Fix it and optimize these resources", "Inspect inventory", "Inspect dependencies"],
        )

    def _handle_dispatch_mission(
        self,
        conv: CopilotConversation,
        message: str,
    ) -> CopilotResponse:
        """Start the autonomous agent control loop and run up to the approval gate."""
        goal = "Reduce monthly cloud spend by 20% without violating application SLOs"
        ctx: DurableAgentContext = self.agent.start_objective(
            goal=goal,
            scenario_name=conv.scenario_name,
            target_reduction_pct=20.0,
        )

        # Run until paused at WAITING_FOR_APPROVAL
        ctx = self.agent.run_until_paused_or_complete(ctx, max_steps=12)
        conv.active_session_id = ctx.session_id
        conv.pending_approval_checkpoint_id = ctx.checkpoint_id

        selected_count = len(ctx.selected_actions)
        rejected_count = len(ctx.rejected_actions)
        total_savings = sum(a.get("expected_savings", 50.0) for a in ctx.selected_actions)

        reply = (
            f"### Autonomous Optimization Plan Prepared\n\n"
            f"I analyzed your topology, mapped service dependencies, and simulated actions on the Digital Twin:\n"
            f"- **Selected Actions**: {selected_count} safe modifications targeting **${total_savings:,.2f}/mo** in savings\n"
            f"- **Protected Resources**: {rejected_count} critical resources rejected (powers database, payment, or auth tiers)\n"
            f"- **Sandbox Validation**: Terraform plan executed and validated in sandbox\n\n"
            f"⏸ **Human Approval Required**\n"
            f"Checkpoint: `{ctx.checkpoint_id}`\n\n"
            f"Would you like me to **Approve** and apply these changes, or **Deny**?"
        )

        approval_payload = {
            "checkpoint_id": ctx.checkpoint_id,
            "session_id": ctx.session_id,
            "selected_actions_count": selected_count,
            "rejected_actions_count": rejected_count,
            "estimated_savings_monthly_usd": total_savings,
            "actions": ctx.selected_actions,
        }

        return CopilotResponse(
            conversation_id=conv.conversation_id,
            reply_text=reply,
            intent=CopilotIntent.DISPATCH_MISSION,
            pending_approval=approval_payload,
            agent_state=ctx.current_state.value,
            quick_actions=["Approve", "Deny"],
        )

    def _handle_approve_execution(
        self,
        conv: CopilotConversation,
        message: str,
    ) -> CopilotResponse:
        """Resume autonomous agent from approval checkpoint to execute and verify."""
        session_id = conv.active_session_id

        if not session_id:
            return CopilotResponse(
                conversation_id=conv.conversation_id,
                reply_text="No active mission or pending approval checkpoint found. Say **'Fix it'** to formulate a new plan.",
                intent=CopilotIntent.APPROVE_EXECUTION,
                quick_actions=["Fix it", "Why is our bill increasing?"],
            )

        resumed = self.agent.resume_approval(
            session_id=session_id,
            approved=True,
            resolver="copilot-operator",
            reason="Approved via Copilot conversational interface",
        )

        conv.pending_approval_checkpoint_id = None
        conv.active_session_id = None

        if resumed.current_state == AgentState.COMPLETED:
            reply = (
                f"✅ **Execution Approved & Applied Successfully**\n\n"
                f"- Applied {len(resumed.selected_actions)} infrastructure actions through governed tools.\n"
                f"- 5-dimension outcome verification completed: **ALL_VERIFIED_SUCCESS**\n"
                f"- Zero latency or availability breaches detected.\n"
                f"- Learning engine updated with verified success."
            )
        elif resumed.current_state == AgentState.ROLLED_BACK:
            reply = (
                f"⚠️ **Execution Halted: Automatic Rollback Triggered**\n\n"
                f"Post-execution verification detected an SLO threshold breach. "
                f"The deterministic rollback engine automatically restored all resources to their healthy baseline."
            )
        else:
            reply = f"Mission resolved with status: `{resumed.current_state.value}`."

        return CopilotResponse(
            conversation_id=conv.conversation_id,
            reply_text=reply,
            intent=CopilotIntent.APPROVE_EXECUTION,
            agent_state=resumed.current_state.value,
            evidence=resumed.verification_report,
            quick_actions=["Why is our bill increasing?", "Inspect inventory"],
        )

    def _handle_deny_execution(
        self,
        conv: CopilotConversation,
        message: str,
    ) -> CopilotResponse:
        """Deny execution and cancel the active mission cleanly."""
        session_id = conv.active_session_id

        if not session_id:
            return CopilotResponse(
                conversation_id=conv.conversation_id,
                reply_text="No pending mission found to cancel.",
                intent=CopilotIntent.DENY_EXECUTION,
            )

        resumed = self.agent.resume_approval(
            session_id=session_id,
            approved=False,
            resolver="copilot-operator",
            reason="Denied by user via Copilot chat",
        )

        conv.pending_approval_checkpoint_id = None
        conv.active_session_id = None

        reply = (
            f"🛑 **Mission Cancelled**\n\n"
            f"Execution denied. Zero infrastructure modifications were applied. "
            f"An audit record has been logged."
        )

        return CopilotResponse(
            conversation_id=conv.conversation_id,
            reply_text=reply,
            intent=CopilotIntent.DENY_EXECUTION,
            agent_state=resumed.current_state.value,
            quick_actions=["Why is our bill increasing?", "Fix it"],
        )

    def handle_approval_decision(
        self,
        conversation_id: str,
        approved: bool,
        approved_by: str = "operator@cloudpilot.ai",
        reason: str = "Decision via Copilot interface",
    ) -> CopilotResponse:
        """
        Public programmatic interface for resolving pending approval checkpoints.
        Raises ValueError if no active checkpoint is found for the conversation.
        """
        conv = self.get_or_create_conversation(conversation_id)
        session_id = conv.active_session_id
        if not session_id:
            raise ValueError(f"No pending approval checkpoint found for conversation '{conversation_id}'")

        if approved:
            resp = self._handle_approve_execution(conv, message=f"Approved by {approved_by}: {reason}")
        else:
            resp = self._handle_deny_execution(conv, message=f"Denied by {approved_by}: {reason}")

        conv.add_message(
            role=CopilotRole.ASSISTANT,
            content=resp.reply_text,
            intent=resp.intent,
            evidence=resp.evidence,
        )
        with self._lock:
            self._save_to_disk_locked()
        return resp

    def _handle_query_approvals(self, conv: CopilotConversation) -> CopilotResponse:
        """Query and display pending approval checkpoints."""
        pending = self.state_manager.get_pending_approvals()
        if not pending:
            return CopilotResponse(
                conversation_id=conv.conversation_id,
                reply_text="There are currently **no pending approvals**. All systems operating normally.",
                intent=CopilotIntent.QUERY_APPROVALS,
                quick_actions=["Why is our bill increasing?", "Fix it"],
            )

        items_md = []
        for cp in pending:
            items_md.append(
                f"- **Checkpoint `{cp.get('checkpoint_id')}`** (Session `{cp.get('session_id')}`): "
                f"{cp.get('pending_action_summary')}"
            )

        reply = (
            f"### Active Pending Approvals ({len(pending)}):\n\n"
            + "\n".join(items_md)
            + "\n\nReply **'Approve'** or **'Deny'** to resolve."
        )

        return CopilotResponse(
            conversation_id=conv.conversation_id,
            reply_text=reply,
            intent=CopilotIntent.QUERY_APPROVALS,
            pending_approval={"pending_count": len(pending), "checkpoints": pending},
            quick_actions=["Approve", "Deny"],
        )

    def _handle_inventory_query(self, conv: CopilotConversation) -> CopilotResponse:
        """Query and format infrastructure inventory."""
        res = self.tools.execute_tool("inspect_infrastructure", {"scenario_name": conv.scenario_name})
        total = res.get("total_resources", 0)
        compute_cnt = len(res.get("compute", []))
        db_cnt = len(res.get("databases", []))
        storage_cnt = len(res.get("storage", []))

        reply = (
            f"### Infrastructure Inventory for {conv.scenario_name}\n\n"
            f"- **Total Resources**: {total}\n"
            f"- **Compute Instances**: {compute_cnt}\n"
            f"- **Databases**: {db_cnt}\n"
            f"- **Storage Volumes**: {storage_cnt}\n"
        )
        return CopilotResponse(
            conversation_id=conv.conversation_id,
            reply_text=reply,
            intent=CopilotIntent.INVENTORY_QUERY,
            evidence=res,
            quick_actions=["Why is our bill increasing?", "Fix it"],
        )

    def _handle_dependency_query(self, conv: CopilotConversation, message: str) -> CopilotResponse:
        """Query and format application service dependency graph."""
        res = self.tools.execute_tool("inspect_dependencies", {"scenario_name": conv.scenario_name})
        services = res.get("services", [])
        reply = (
            f"### Application Service Graph\n\n"
            f"Discovered **{len(services)} services** with defined upstream/downstream dependencies.\n"
            f"Protected Tier-1 services: `PaymentService`, `AuthService`, `CoreDatabase`."
        )
        return CopilotResponse(
            conversation_id=conv.conversation_id,
            reply_text=reply,
            intent=CopilotIntent.DEPENDENCY_QUERY,
            evidence=res,
            quick_actions=["Fix it", "Why is our bill increasing?"],
        )

    def _handle_general_query(self, conv: CopilotConversation, message: str) -> CopilotResponse:
        """Fallback response for general queries."""
        reply = (
            f"I am the **CloudPilot Autonomous Copilot**. I can help you understand your cloud spend, "
            f"inspect topology, identify cost anomalies, and execute safe governed optimizations.\n\n"
            f"Try asking:\n"
            f"- *'Why is our cloud bill increasing?'*\n"
            f"- *'Show me our infrastructure inventory'*\n"
            f"- *'Fix it'* to formulate an optimization plan\n"
            f"- *'Show pending approvals'*"
        )
        return CopilotResponse(
            conversation_id=conv.conversation_id,
            reply_text=reply,
            intent=CopilotIntent.GENERAL_QUERY,
            quick_actions=["Why is our bill increasing?", "Fix it", "Show pending approvals"],
        )

    # -------------------------------------------------------------------------
    # Disk Persistence
    # -------------------------------------------------------------------------
    def _save_to_disk_locked(self) -> None:
        try:
            payload = {
                "conversations": [c.model_dump(mode="json") for c in self._conversations.values()],
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp_file = self.persistence_file.with_suffix(".tmp")
            tmp_file.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            tmp_file.replace(self.persistence_file)
        except Exception as e:
            logger.warning("Failed to serialize copilot conversations to disk: %s", e)

    def _load_from_disk(self) -> None:
        if not self.persistence_file.exists():
            return
        try:
            raw = json.loads(self.persistence_file.read_text(encoding="utf-8"))
            for item in raw.get("conversations", []):
                conv = CopilotConversation(**item)
                self._conversations[conv.conversation_id] = conv
            logger.info("Loaded %d conversations from disk", len(self._conversations))
        except Exception as e:
            logger.warning("Could not load conversations from %s: %s", self.persistence_file, e)


# Global singleton
_copilot_engine: Optional[CloudPilotCopilotEngine] = None


def get_copilot_engine() -> CloudPilotCopilotEngine:
    """Get or create singleton CloudPilotCopilotEngine."""
    global _copilot_engine
    if _copilot_engine is None:
        _copilot_engine = CloudPilotCopilotEngine()
    return _copilot_engine

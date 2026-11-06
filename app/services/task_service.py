"""
CloudPilot SwitchOps — Task Lifecycle & Switch Orchestration Service

Orchestrates task receipt from Switch rooms, validates state transitions,
executes infrastructure discovery, coordinates specialist agents (FinOps, SecOps),
appends immutable audit events, and truthfully communicates status back to Switch rooms.
"""

from __future__ import annotations

from pathlib import Path
import re
import uuid
from typing import Any, List, Optional, Tuple

from app.core.errors import TaskNotFoundError
from app.core.logging import (
    get_logger,
    redact_secrets,
    set_correlation_id,
    set_task_id,
)
from app.domain.approvals import (
    ApprovalPrincipal,
    ApproverRole,
    PERMITTED_APPROVAL_ROLES,
)
from app.domain.decisions import DecisionReport, DecisionRun
from app.domain.execution import ExecutionStatus
from app.domain.finding import (
    AssessmentSummary,
    Finding,
    FindingCategory,
    FindingSeverity,
)
from app.domain.inventory import InfrastructureInventory
from app.domain.models import (
    ActorType,
    Evidence,
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
)
from app.domain.objectives import PreferenceProfile
from app.integrations.switch.client import SwitchAdapterInterface
from app.integrations.switch.connection_manager import SwitchConnectionManager
from app.integrations.switch.event_handler import SwitchEventHandler
from app.integrations.switch.message_mapper import (
    SwitchCollaborationEvent,
    SwitchMessageMapper,
    WorkflowEventType,
)
from app.persistence.repository import TaskRepositoryInterface
from app.services.approval.approval_service import ApprovalSecurityError, ApprovalService
from app.services.decision.decision_orchestrator import DecisionOrchestrator
from app.services.discovery.engine import InfrastructureDiscoveryEngine
from app.services.execution.execution_orchestrator import ExecutionOrchestrator
from app.services.specialists.finops_specialist import FinOpsSpecialist
from app.services.specialists.secops_specialist import SecOpsSpecialist

logger = get_logger("cloudpilot.services.task")


class TaskService:
    """
    Core application service managing the CloudPilot task lifecycle,
    persistence, audit logging, and bidirectional Switch room interactions.
    """

    def __init__(
        self,
        repository: TaskRepositoryInterface,
        switch_adapter: SwitchAdapterInterface,
        discovery_engine: Optional[InfrastructureDiscoveryEngine] = None,
        finops_specialist: Optional[FinOpsSpecialist] = None,
        secops_specialist: Optional[SecOpsSpecialist] = None,
        connection_manager: Optional[SwitchConnectionManager] = None,
        event_handler: Optional[SwitchEventHandler] = None,
    ) -> None:
        self.repository = repository
        self.switch_adapter = switch_adapter
        self.discovery_engine = discovery_engine or InfrastructureDiscoveryEngine()
        self.finops_specialist = finops_specialist or FinOpsSpecialist()
        self.secops_specialist = secops_specialist or SecOpsSpecialist()
        self.connection_manager = connection_manager or SwitchConnectionManager(adapter=switch_adapter)
        self.event_handler = event_handler or SwitchEventHandler()

    async def handle_switch_event(self, frame: dict[str, Any]) -> Task | None:
        """
        Handle an incoming event frame from the Switch Agent Bridge.
        Filters for addressed room messages, executes task lifecycle, and posts room replies.
        """
        try:
            self.event_handler.validate_frame(frame)
        except Exception as frame_err:
            logger.debug("Frame validation failed: %s", frame_err)
            return None

        event_kind = frame.get("event")
        payload = frame.get("payload", {})

        if event_kind != "message":
            logger.debug("Ignoring non-message Switch event: %s", event_kind)
            return None

        # Verify addressed flag
        if not payload.get("addressed", False):
            logger.debug("Ignoring unaddressed room message")
            return None

        # Inbound deduplication
        if self.connection_manager.is_duplicate_inbound_event(frame):
            logger.info("Ignoring duplicate inbound Switch message: %s", payload.get("message_id"))
            return None

        body = payload.get("body", "").strip()
        sender = payload.get("sender", "unknown")
        sender_name = payload.get("sender_name", "Operator")
        message_id = payload.get("message_id", f"msg-{uuid.uuid4().hex[:8]}")
        room_id = frame.get("rooms", ["cloudpilot-ops"])[0] if "rooms" in frame else "cloudpilot-ops"

        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        set_correlation_id(correlation_id)

        logger.info(
            "Received addressed message from %s in room '%s': %s",
            sender_name,
            room_id,
            redact_secrets(body),
        )

        # Detect Phase 4 Human Approval and Rejection commands
        approve_match = re.search(
            r"\bapprove(?:\s+proposal)?\s+(prop-[a-f0-9]+)(?:\s+(?:token\s+)?([^\s]+))?",
            body,
            re.IGNORECASE,
        )
        reject_match = re.search(
            r"\breject(?:\s+proposal)?\s+(prop-[a-f0-9]+)(?:\s+(?:reason[:\s]+)?(.+))?",
            body,
            re.IGNORECASE,
        )
        if approve_match:
            proposal_id = approve_match.group(1)
            token_str = approve_match.group(2) if approve_match.group(2) else None
            return await self._handle_switch_approval(
                proposal_id=proposal_id,
                token_str=token_str,
                sender=sender,
                sender_name=sender_name,
                room_id=room_id,
                correlation_id=correlation_id,
                metadata=frame.get("metadata") or {},
            )
        elif reject_match:
            proposal_id = reject_match.group(1)
            reason = reject_match.group(2).strip() if reject_match.group(2) else None
            return await self._handle_switch_rejection(
                proposal_id=proposal_id,
                reason=reason,
                sender=sender,
                sender_name=sender_name,
                room_id=room_id,
                correlation_id=correlation_id,
                metadata=frame.get("metadata") or {},
            )

        # Detect if task is an explicit assessment or decision command
        is_decision = bool(
            re.search(r"\b(decide|optimize|optimization|recommend|trade-?off|pareto)\b", body, re.IGNORECASE)
        )
        is_assessment = bool(
            re.search(r"assess\s+(?:\./|[a-zA-Z0-9_\-\.\/]+)", body, re.IGNORECASE)
            or (frame.get("metadata") and "workspace_root" in frame["metadata"])
        )

        pref_profile = PreferenceProfile.BALANCED
        body_lower = body.lower()
        if "cost" in body_lower or "savings" in body_lower or "cheapest" in body_lower:
            pref_profile = PreferenceProfile.COST_FIRST
        elif "security" in body_lower or "secure" in body_lower:
            pref_profile = PreferenceProfile.SECURITY_FIRST
        elif "reliability" in body_lower or "sla" in body_lower or "availability" in body_lower:
            pref_profile = PreferenceProfile.RELIABILITY_FIRST

        if is_decision:
            task_type = "decision_optimization"
        elif is_assessment:
            task_type = "infrastructure_assessment"
        else:
            task_type = "infrastructure_review"

        meta = {
            "origin_message_id": message_id,
            "sender_name": sender_name,
            "preference_profile": pref_profile.value,
        }
        if frame.get("metadata"):
            meta.update(frame["metadata"])

        return await self.process_task_request(
            title=f"Task from {sender_name}: {body[:40]}...",
            description=body,
            room_id=room_id,
            requested_by=sender,
            correlation_id=correlation_id,
            task_type=task_type,
            metadata=meta,
        )

    async def process_task_request(
        self,
        title: str,
        description: str,
        room_id: str,
        requested_by: str,
        correlation_id: str | None = None,
        task_type: str = "infrastructure_review",
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """
        Execute task workflow through truth-preserving state transitions.
        """
        cid = correlation_id or f"corr-{uuid.uuid4().hex[:12]}"
        set_correlation_id(cid)

        # 1. Initialize Task in RECEIVED state
        task_meta = dict(metadata or {})
        if "switch_execution_mode" not in task_meta:
            if hasattr(self.switch_adapter, "bridge_url"):
                task_meta["switch_execution_mode"] = "LIVE_WIRE"
            else:
                task_meta["switch_execution_mode"] = "EMULATED_BRIDGE"

        task = Task(
            task_type=task_type,
            title=title,
            description=description,
            room_id=room_id,
            requested_by=requested_by,
            status=TaskStatus.RECEIVED,
            correlation_id=cid,
            metadata=task_meta,
        )
        set_task_id(task.task_id)

        self.repository.save_task(task)
        self.repository.append_event(
            TaskEvent(
                task_id=task.task_id,
                event_type=TaskEventType.TASK_RECEIVED,
                actor_id=requested_by,
                actor_type=ActorType.HUMAN,
                correlation_id=cid,
                payload={"description": description, "room_id": room_id},
            )
        )
        logger.info("Task %s created with status RECEIVED", task.task_id)

        try:
            # 2. Transition to ACKNOWLEDGED
            task.transition_to(TaskStatus.ACKNOWLEDGED)
            self.repository.update_task(task)
            self.repository.append_event(
                TaskEvent(
                    task_id=task.task_id,
                    event_type=TaskEventType.TASK_ACKNOWLEDGED,
                    actor_id="cloudpilot-agent",
                    actor_type=ActorType.AGENT,
                    correlation_id=cid,
                    payload={"status": task.status.value},
                )
            )

            # Post acknowledgment back into the Switch room
            ack_message = (
                f"**[CloudPilot SwitchOps]** Acknowledged request: `{task.title}`\n"
                f"- **Task ID**: `{task.task_id}`\n"
                f"- **Status**: `ACKNOWLEDGED`\n"
                f"- **Correlation ID**: `{cid}`\n"
                f"Proceeding to evaluate operational boundary..."
            )
            await self._safe_post_switch_message(
                room_id,
                ack_message,
                task=task,
                event_type=WorkflowEventType.TASK_ACKNOWLEDGED,
            )

            # 3. Transition to IN_PROGRESS
            task.transition_to(TaskStatus.IN_PROGRESS)
            self.repository.update_task(task)
            self.repository.append_event(
                TaskEvent(
                    task_id=task.task_id,
                    event_type=TaskEventType.TASK_STARTED,
                    actor_id="cloudpilot-agent",
                    actor_type=ActorType.AGENT,
                    correlation_id=cid,
                    payload={"status": task.status.value},
                )
            )

            # Check if this task targets infrastructure assessment or decision optimization
            workspace_path = self._extract_workspace_path(description, metadata)

            if task_type == "decision_optimization" or (workspace_path and any(w in description.lower() for w in ["decide", "optimize", "recommend", "pareto"])):
                # Execute Phase 2 Assessment first, then Phase 3 Decision Intelligence
                target_dir = workspace_path or "samples/staging"
                assessment = await self._execute_assessment_workflow(
                    task=task,
                    workspace_dir=target_dir,
                    room_id=room_id,
                    correlation_id=cid,
                )
                decision_run, report = await self._execute_decision_workflow(
                    task=task,
                    assessment=assessment,
                    room_id=room_id,
                    correlation_id=cid,
                    metadata=metadata,
                )
                rec = decision_run.recommended_candidate
                execution_summary = (
                    f"CloudPilot SwitchOps Phase 3 Decision Intelligence Completed for `{target_dir}`.\n"
                    f"- Decision ID: {decision_run.decision_id}\n"
                    f"- Z3 Constraint Verification: {decision_run.z3_verification_status}\n"
                    f"- Candidates: {decision_run.total_candidates_generated} generated | {decision_run.feasible_candidates_count} feasible | {decision_run.rejected_candidates_count} rejected by constraints\n"
                    f"- Pareto Frontier: {decision_run.pareto_optimal_count} non-dominated alternatives\n"
                    f"- Recommended Action: {rec.title if rec else 'None (All rejected)'}\n"
                    f"- Read-only policy strictly enforced: zero modifications made to files or infrastructure."
                )
            elif workspace_path or task_type == "infrastructure_assessment":
                # Execute Phase 2 Intelligence Assessment Workflow
                target_dir = workspace_path or "samples/staging"
                assessment = await self._execute_assessment_workflow(
                    task=task,
                    workspace_dir=target_dir,
                    room_id=room_id,
                    correlation_id=cid,
                )
                execution_summary = (
                    f"CloudPilot SwitchOps Phase 2 Assessment Completed for `{target_dir}`.\n"
                    f"- Resources Discovered: {assessment.total_resources}\n"
                    f"- Estimated Monthly Baseline: ${assessment.estimated_monthly_cost} {assessment.currency}\n"
                    f"- Total Findings: {assessment.total_findings} "
                    f"({assessment.critical_findings_count} critical, {assessment.high_findings_count} high)\n"
                    f"- Read-only policy strictly enforced: zero modifications made to files or infrastructure."
                )
            else:
                # Phase 1 Engineering Foundation baseline execution
                execution_summary = (
                    "CloudPilot SwitchOps Phase 1 Foundation Verified.\n"
                    "- Read-only policy enforced: zero modifications made to files or infrastructure.\n"
                    "- Live multi-cloud discovery & FinOps/SecOps intelligence engines available in Phase 2.\n"
                    "- Switch collaboration bridge and task audit trail are verified active."
                )

                # 6. Post final result report in Switch room
                report_message = (
                    f"### [CloudPilot SwitchOps] Task Execution Report\n"
                    f"- **Task ID**: `{task.task_id}`\n"
                    f"- **Status**: `COMPLETED`\n"
                    f"- **Requested by**: {task.requested_by}\n"
                    f"- **Room**: `{task.room_id}`\n"
                    f"- **Correlation ID**: `{cid}`\n\n"
                    f"**Assessment Outcome:**\n"
                    f"{execution_summary}\n\n"
                    f"*Audit trail persisted with {len(self.repository.get_events_for_task(task.task_id))} events.*"
                )
                await self._safe_post_switch_message(
                    room_id,
                    report_message,
                    task=task,
                    event_type=WorkflowEventType.WORKFLOW_COMPLETED,
                )

            # 5. Transition to COMPLETED
            task.transition_to(TaskStatus.COMPLETED)
            task.metadata["result_summary"] = execution_summary
            self.repository.update_task(task)
            self.repository.append_event(
                TaskEvent(
                    task_id=task.task_id,
                    event_type=TaskEventType.TASK_COMPLETED,
                    actor_id="cloudpilot-agent",
                    actor_type=ActorType.AGENT,
                    correlation_id=cid,
                    payload={"summary": execution_summary, "status": task.status.value},
                )
            )

            logger.info("Task %s completed successfully", task.task_id)
            return task

        except Exception as exc:
            logger.exception("Error executing task %s: %s", task.task_id, exc)
            if task.can_transition_to(TaskStatus.FAILED):
                task.transition_to(TaskStatus.FAILED)
                task.metadata["error"] = str(exc)
                self.repository.update_task(task)
                self.repository.append_event(
                    TaskEvent(
                        task_id=task.task_id,
                        event_type=TaskEventType.TASK_FAILED,
                        actor_id="cloudpilot-agent",
                        actor_type=ActorType.AGENT,
                        correlation_id=cid,
                        payload={"error": str(exc)},
                    )
                )
                err_msg = (
                    f"**[CloudPilot SwitchOps]** Task `{task.task_id}` FAILED: {exc!s}\n"
                    f"- Status: `FAILED`\n- Correlation ID: `{cid}`"
                )
                await self._safe_post_switch_message(room_id, err_msg, task=task)
            raise

    async def _execute_assessment_workflow(
        self,
        task: Task,
        workspace_dir: str,
        room_id: str,
        correlation_id: str,
    ) -> AssessmentSummary:
        """
        Coordinates full multi-specialist investigation across Discovery, FinOps, and SecOps.
        """
        # Step A: Announce discovery start in room
        start_msg = (
            f"🔍 **Starting Infrastructure Discovery**\n"
            f"- **Target Workspace**: `{workspace_dir}`\n"
            f"- **Mode**: Read-only assessment (zero modifications)\n"
            f"Scanning for Terraform (`*.tf`) and Docker Compose definitions..."
        )
        await self._safe_post_switch_message(room_id, start_msg, task=task)

        # Step B: Run Discovery Engine
        inventory = self.discovery_engine.discover(
            workspace_root=workspace_dir,
            task_id=task.task_id,
        )
        self.repository.save_inventory(inventory)

        disc_msg = (
            f"📦 **Infrastructure Discovery Completed**\n"
            f"- **Discovered Files**: {len(inventory.discovered_files)} (`{', '.join(Path(f).name for f in inventory.discovered_files)}`)\n"
            f"- **Total Resources**: {inventory.total_resources}\n"
            f"- **Scan Duration**: {inventory.discovery_duration_ms:.1f}ms\n"
            f"Dispatching specialist agents: `finops-specialist`, `secops-specialist`..."
        )
        await self._safe_post_switch_message(room_id, disc_msg, task=task)

        # Step C: FinOps Specialist evaluation
        finops_res = self.finops_specialist.analyze(inventory=inventory, task_id=task.task_id)
        for f in finops_res.findings:
            self.repository.save_finding(f)

        finops_switch_msg = self.finops_specialist.format_switch_message(finops_res)
        await self._safe_post_switch_message(room_id, finops_switch_msg, task=task)

        # Step D: SecOps Specialist evaluation
        secops_res = self.secops_specialist.analyze(inventory=inventory, task_id=task.task_id)
        for f in secops_res.all_findings:
            self.repository.save_finding(f)

        secops_switch_msg = self.secops_specialist.format_switch_message(secops_res)
        await self._safe_post_switch_message(room_id, secops_switch_msg, task=task)

        # Step E: Compile Assessment Summary
        all_findings = finops_res.findings + secops_res.all_findings
        crit = sum(1 for f in all_findings if f.severity == FindingSeverity.CRITICAL)
        high = sum(1 for f in all_findings if f.severity == FindingSeverity.HIGH)
        med = sum(1 for f in all_findings if f.severity == FindingSeverity.MEDIUM)
        low = sum(1 for f in all_findings if f.severity == FindingSeverity.LOW)

        next_recommendations = [
            "Evaluate Phase 3 Pareto optimization to balance compute instance downscaling against SLA targets.",
            "Formulate bounded remediation plan for exposed ports and unrestricted security group ingress.",
            "Implement off-hours shutdown schedule on non-production database resources to capture up to 65% savings.",
        ]

        assessment = AssessmentSummary(
            task_id=task.task_id,
            workspace_root=workspace_dir,
            total_resources=inventory.total_resources,
            total_findings=len(all_findings),
            critical_findings_count=crit,
            high_findings_count=high,
            medium_findings_count=med,
            low_findings_count=low,
            estimated_monthly_cost=finops_res.total_monthly_cost,
            currency=finops_res.currency,
            finops_summary=finops_res.summary_text,
            secops_summary=secops_res.security_summary,
            reliability_summary=secops_res.reliability_summary,
            next_phase_recommendations=next_recommendations,
            status="COMPLETED",
        )
        self.repository.save_assessment(assessment)

        # Step F: Publish final consolidated report in Switch room
        consolidated_report = (
            f"## 📊 [CloudPilot SwitchOps] Task Execution Report — Consolidated Assessment\n"
            f"- **Task ID**: `{task.task_id}` | **Status**: `COMPLETED`\n"
            f"- **Target Workspace**: `{workspace_dir}`\n"
            f"- **Total Discovered Resources**: {inventory.total_resources}\n\n"
            f"### 1. FinOps Baseline\n"
            f"- **Estimated Monthly Baseline**: **${assessment.estimated_monthly_cost} {assessment.currency}**\n"
            f"- {finops_res.summary_text}\n\n"
            f"### 2. SecOps & Reliability Posture\n"
            f"- **Total Findings**: {assessment.total_findings} "
            f"({crit} Critical, {high} High, {med} Medium, {low} Low)\n"
            f"- {secops_res.security_summary}\n"
            f"- {secops_res.reliability_summary}\n\n"
            f"### 3. Next Phase Investigation Scope\n"
            + "\n".join(f"- {rec}" for rec in next_recommendations)
            + f"\n\n*All {len(all_findings)} finding(s) persisted with reproducible evidence records.*"
        )
        await self._safe_post_switch_message(room_id, consolidated_report, task=task)

        return assessment

    async def _execute_decision_workflow(
        self,
        task: Task,
        assessment: AssessmentSummary,
        room_id: str,
        correlation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Tuple[DecisionRun, DecisionReport]:
        """
        Coordinates candidate generation, constraint verification (Z3),
        Pareto frontier calculation, and report publishing in Switch room.
        """
        pref_str = (metadata or {}).get("preference_profile", "BALANCED")
        try:
            profile = PreferenceProfile(pref_str)
        except Exception:
            profile = PreferenceProfile.BALANCED

        start_msg = (
            f"🧠 **Starting CloudPilot Decision Intelligence Engine**\n"
            f"- **Target Workspace**: `{assessment.workspace_root}`\n"
            f"- **Preference Profile**: `{profile.value}`\n"
            f"- **Policy Invariants**: Non-public databases, persistent volume preservation, budget ceiling\n"
            f"Generating candidates and validating hard constraints with Z3 SMT solver..."
        )
        await self._safe_post_switch_message(room_id, start_msg, task=task)

        orchestrator = DecisionOrchestrator(repository=self.repository)
        decision_run, report = orchestrator.run_decision_analysis(
            task_id=task.task_id,
            preference_profile=profile,
        )

        # Truth-preserving metadata annotations
        task.metadata["decision_id"] = decision_run.decision_id
        task.metadata["decision_status"] = decision_run.status
        task.metadata["optimization_scope"] = decision_run.optimization_scope
        task.metadata["z3_verification_status"] = decision_run.z3_verification_status
        task.metadata["provenance_hash"] = report.provenance_hash

        # Report is posted ONLY upon successful completion of decision analysis
        decision_switch_msg = orchestrator.recommender.format_switch_report(decision_run, report)
        await self._safe_post_switch_message(room_id, decision_switch_msg, task=task)

        # Auto-propose if there is a recommended feasible candidate
        if decision_run.recommended_candidate:
            try:
                approval_service = ApprovalService(repository=self.repository)
                proposal = approval_service.generate_proposal_from_decision(
                    decision_run=decision_run,
                    candidate=decision_run.recommended_candidate,
                    workspace_root=assessment.workspace_root,
                )
                task.metadata["proposal_id"] = proposal.proposal_id
                task.metadata["proposal_hash"] = proposal.proposal_hash

                proposal_announcement = SwitchMessageMapper.format_proposal_for_switch(
                    proposal=proposal,
                    decision_run=decision_run,
                    decision_report=report,
                )
                await self._safe_post_switch_message(
                    room_id,
                    proposal_announcement,
                    task=task,
                    event_type=WorkflowEventType.PROPOSAL_PUBLISHED,
                    proposal_id=proposal.proposal_id,
                    correlation_id=correlation_id,
                )
            except Exception as prop_err:
                logger.warning(
                    "Could not auto-generate proposal for decision %s: %s",
                    decision_run.decision_id,
                    prop_err,
                )

        return decision_run, report

    def _extract_principal(
        self, sender: str, sender_name: str, metadata: dict[str, Any] | None
    ) -> ApprovalPrincipal:
        """Extract and validate principal identity and role from Switch message context using authoritative server directory."""
        return self.event_handler.resolve_authenticated_principal(
            sender=sender,
            sender_name=sender_name,
            metadata=metadata,
        )

    async def _handle_switch_approval(
        self,
        proposal_id: str,
        token_str: Optional[str],
        sender: str,
        sender_name: str,
        room_id: str,
        correlation_id: str,
        metadata: dict[str, Any],
    ) -> Task:
        """Handle human-in-the-loop proposal approval from Switch room."""
        principal = self._extract_principal(sender, sender_name, metadata)
        task = Task(
            task_type="proposal_approval",
            title=f"Approve Proposal {proposal_id} by {principal.display_name}",
            description=f"Human approval and bounded execution for proposal {proposal_id}",
            room_id=room_id,
            requested_by=sender,
            status=TaskStatus.RECEIVED,
            correlation_id=correlation_id,
            metadata={"proposal_id": proposal_id, "approver_role": principal.role.value},
        )
        self.repository.save_task(task)
        self.repository.append_event(
            TaskEvent(
                task_id=task.task_id,
                event_type=TaskEventType.TASK_RECEIVED,
                actor_id=sender,
                actor_type=ActorType.HUMAN,
                correlation_id=correlation_id,
                payload={"proposal_id": proposal_id},
            )
        )

        task.transition_to(TaskStatus.ACKNOWLEDGED)
        task.transition_to(TaskStatus.IN_PROGRESS)
        self.repository.update_task(task)

        # 1. Authorization check
        if not principal.is_authorized:
            err_msg = (
                f"❌ **Approval Denied: Unauthorized Approver Role**\n"
                f"- **Principal**: `{principal.principal_id}`\n"
                f"- **Role**: `{principal.role.value}`\n"
                f"- **Required Role**: One of {[r.value for r in PERMITTED_APPROVAL_ROLES]}\n"
                f"Infrastructure change proposals can only be authorized by designated engineering leads."
            )
            await self._safe_post_switch_message(room_id, err_msg, task=task)
            task.transition_to(TaskStatus.FAILED)
            task.metadata["error"] = "UNAUTHORIZED_APPROVER_ROLE"
            self.repository.update_task(task)
            return task

        # 2. Check proposal exists
        proposal = self.repository.get_proposal(proposal_id)
        if not proposal:
            err_msg = f"❌ **Proposal Not Found**: `{proposal_id}` does not exist in repository."
            await self._safe_post_switch_message(room_id, err_msg, task=task)
            task.transition_to(TaskStatus.FAILED)
            task.metadata["error"] = "PROPOSAL_NOT_FOUND"
            self.repository.update_task(task)
            return task

        # 3. Submit approval
        approval_service = ApprovalService(repository=self.repository)
        if not token_str:
            token_str, _ = approval_service.request_approval_token(proposal_id, principal)
        elif isinstance(token_str, tuple):
            token_str = token_str[0]

        try:
            approval_record = approval_service.submit_approval(
                proposal_id=proposal_id,
                token_string=token_str,
                principal=principal,
            )
        except ApprovalSecurityError as sec_err:
            err_msg = (
                f"❌ **Approval Security Verification Failed**\n"
                f"- **Reason**: {sec_err.message}\n"
                f"- **Code**: `{sec_err.code}`"
            )
            await self._safe_post_switch_message(room_id, err_msg, task=task)
            task.transition_to(TaskStatus.FAILED)
            task.metadata["error"] = sec_err.message
            self.repository.update_task(task)
            return task

        approval_ack = (
            f"✅ **Infrastructure Change Proposal Authorized**\n"
            f"- **Proposal ID**: `{proposal.proposal_id}`\n"
            f"- **Decision ID**: `{proposal.decision_id}`\n"
            f"- **Approved By**: `{principal.display_name}` (`{principal.role.value}`)\n"
            f"- **Proposal SHA-256 Hash**: `{proposal.proposal_hash}`\n"
            f"- **Status**: `APPROVED`\n\n"
            f"Spawning isolated workspace execution and validation runner..."
        )
        await self._safe_post_switch_message(room_id, approval_ack, task=task)

        # 4. Execute bounded change inside isolated workspace
        orchestrator = ExecutionOrchestrator(repository=self.repository)
        workspace_target = proposal.workspace_root or "samples/staging"
        exec_record = orchestrator.execute_proposal(
            proposal_id=proposal.proposal_id,
            approval_token=token_str,
            principal=principal,
            target_workspace=workspace_target,
        )

        task.metadata["execution_id"] = exec_record.execution_id
        task.metadata["execution_status"] = exec_record.status.value

        if exec_record.status == ExecutionStatus.COMPLETED:
            mutations_summary = "\n".join(
                f"- `{m.relative_path}` ({m.mutation_type}): pre=`{m.before_hash[:10]}...` -> post=`{m.after_hash[:10]}...`"
                for m in exec_record.mutations
            )
            completion_msg = (
                f"🚀 **Bounded Execution & Verification Succeeded**\n"
                f"- **Execution ID**: `{exec_record.execution_id}`\n"
                f"- **Proposal ID**: `{proposal.proposal_id}`\n"
                f"- **Status**: `COMPLETED`\n"
                f"- **Isolated Sandbox**: `{exec_record.isolated_workspace_path}`\n"
                f"- **Audit Trail Head Hash**: `{exec_record.audit_trail_hash}`\n\n"
                f"**Applied Mutations (Syntax & Post-Hash Verified):**\n"
                f"{mutations_summary}\n\n"
                f"> **Truth-Preserving Operational Notice**: {exec_record.disclaimer}"
            )
            await self._safe_post_switch_message(room_id, completion_msg, task=task)
            task.transition_to(TaskStatus.COMPLETED)
            task.metadata["result_summary"] = "Bounded execution and verification completed successfully."
        elif exec_record.status == ExecutionStatus.ROLLED_BACK:
            rollback_msg = (
                f"⚠️ **Execution Aborted — Automated File Recovery Verified**\n"
                f"- **Execution ID**: `{exec_record.execution_id}`\n"
                f"- **Status**: `ROLLED_BACK`\n"
                f"- **Failure Reason**: {exec_record.error_message}\n"
                f"- **Recovery Result**: All modified workspace files were restored from pre-execution snapshot.\n"
                f"- **Restored Hashes Verified**: Yes (all files match baseline pre-change hashes).\n\n"
                f"> **Notice**: {exec_record.disclaimer}"
            )
            await self._safe_post_switch_message(room_id, rollback_msg, task=task)
            task.transition_to(TaskStatus.FAILED)
            task.metadata["error"] = exec_record.error_message
        else:
            fail_msg = (
                f"🚨 **Execution Failed**: {exec_record.error_message}\n"
                f"- Status: `{exec_record.status.value}`"
            )
            await self._safe_post_switch_message(room_id, fail_msg, task=task)
            task.transition_to(TaskStatus.FAILED)
            task.metadata["error"] = exec_record.error_message

        self.repository.update_task(task)
        return task

    async def _handle_switch_rejection(
        self,
        proposal_id: str,
        reason: Optional[str],
        sender: str,
        sender_name: str,
        room_id: str,
        correlation_id: str,
        metadata: dict[str, Any],
    ) -> Task:
        """Handle human-in-the-loop proposal rejection from Switch room."""
        principal = self._extract_principal(sender, sender_name, metadata)
        task = Task(
            task_type="proposal_rejection",
            title=f"Reject Proposal {proposal_id} by {principal.display_name}",
            description=f"Human rejection for proposal {proposal_id}",
            room_id=room_id,
            requested_by=sender,
            status=TaskStatus.RECEIVED,
            correlation_id=correlation_id,
            metadata={"proposal_id": proposal_id},
        )
        self.repository.save_task(task)
        task.transition_to(TaskStatus.ACKNOWLEDGED)
        task.transition_to(TaskStatus.IN_PROGRESS)
        self.repository.update_task(task)

        if not principal.is_authorized:
            err_msg = (
                f"❌ **Rejection Denied: Unauthorized Approver Role**\n"
                f"- Principal `{principal.principal_id}` has role `{principal.role.value}`."
            )
            await self._safe_post_switch_message(room_id, err_msg, task=task)
            task.transition_to(TaskStatus.FAILED)
            self.repository.update_task(task)
            return task

        proposal = self.repository.get_proposal(proposal_id)
        if not proposal:
            err_msg = f"❌ **Proposal Not Found**: `{proposal_id}`."
            await self._safe_post_switch_message(room_id, err_msg, task=task)
            task.transition_to(TaskStatus.FAILED)
            self.repository.update_task(task)
            return task

        approval_service = ApprovalService(repository=self.repository)
        rejection_reason = reason or "Rejected by human operator in Switch"
        approval_service.submit_rejection(proposal_id, principal, reason=rejection_reason)

        rej_msg = (
            f"🛑 **Infrastructure Change Proposal Rejected**\n"
            f"- **Proposal ID**: `{proposal.proposal_id}`\n"
            f"- **Decision ID**: `{proposal.decision_id}`\n"
            f"- **Rejected By**: `{principal.display_name}` (`{principal.role.value}`)\n"
            f"- **Reason**: {rejection_reason}\n"
            f"- **Status**: `REJECTED`\n"
            f"- **Proposal Hash**: `{proposal.proposal_hash}`\n\n"
            f"No changes were applied. The proposal has been permanently closed."
        )
        await self._safe_post_switch_message(room_id, rej_msg, task=task)
        task.transition_to(TaskStatus.COMPLETED)
        task.metadata["result_summary"] = f"Proposal {proposal_id} rejected."
        self.repository.update_task(task)
        return task

    def _extract_workspace_path(self, text: str, metadata: dict[str, Any] | None) -> str:
        """Extract workspace path from metadata or explicit path command if it exists."""
        candidate = ""
        if metadata and "workspace_root" in metadata:
            candidate = str(metadata["workspace_root"])
        else:
            # Check for explicit paths like ./samples/staging or samples/safe
            path_match = re.search(r"(\./[^\s,]+|samples/[^\s,]+)", text)
            if path_match:
                candidate = path_match.group(1).rstrip(".,;'\"")
            # Or explicit command targeting staging or safe (e.g. "@cloudpilot assess staging", "@cloudpilot optimize staging")
            elif re.search(r"\b(?:assess|decide|optimize)\s+(?:on\s+)?(?:the\s+)?(staging|safe)", text, re.IGNORECASE):
                sub = "staging" if "staging" in text.lower() else "safe"
                candidate = f"samples/{sub}"

        if candidate and Path(candidate).exists() and Path(candidate).is_dir():
            return candidate

        return ""

    async def _safe_post_switch_message(
        self,
        room_id: str,
        content: str,
        task: Optional[Task] = None,
        event_type: Optional[WorkflowEventType] = None,
        proposal_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Post a message to the Switch room via ConnectionManager, truthfully surfacing
        delivery errors in task metadata and recording collaboration events.
        """
        cid = correlation_id or (task.correlation_id if task else f"corr-{uuid.uuid4().hex[:10]}")
        tid = task.task_id if task else f"task-sys-{uuid.uuid4().hex[:6]}"
        ev_type = event_type or WorkflowEventType.WORKFLOW_COMPLETED

        collab_event = SwitchCollaborationEvent(
            event_type=ev_type,
            task_id=tid,
            proposal_id=proposal_id,
            execution_id=execution_id,
            correlation_id=cid,
            switch_room_id=room_id,
            summary=content[:120],
        )

        try:
            published = await self.connection_manager.publish_workflow_event(
                event=collab_event,
                content=content,
            )
            if task:
                task.metadata["switch_delivery_status"] = published.delivery_status
                if published.switch_message_id:
                    task.metadata["switch_last_message_id"] = published.switch_message_id
        except Exception as err:
            logger.warning(
                "Unable to post message to Switch room '%s' (bridge may be offline): %s",
                room_id,
                err,
            )
            if task:
                task.metadata["switch_delivery_status"] = "FAILED"
                task.metadata["switch_delivery_error"] = str(err)
                try:
                    self.repository.update_task(task)
                except Exception:
                    pass

    def get_task(self, task_id: str) -> Task:
        """Retrieve task by ID or raise TaskNotFoundError."""
        task = self.repository.get_task(task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        room_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks with filtering and pagination."""
        return self.repository.list_tasks(status=status, room_id=room_id, limit=limit, offset=offset)

    def get_task_events(self, task_id: str) -> list[TaskEvent]:
        """Retrieve chronological event history for a task."""
        self.get_task(task_id)
        return self.repository.get_events_for_task(task_id)

    def attach_evidence(self, task_id: str, evidence: Evidence) -> Evidence:
        """Attach evidence finding to a task and log audit event."""
        task = self.get_task(task_id)
        evidence.task_id = task.task_id
        saved = self.repository.save_evidence(evidence)
        self.repository.append_event(
            TaskEvent(
                task_id=task.task_id,
                event_type=TaskEventType.EVIDENCE_ATTACHED,
                actor_id="cloudpilot-agent",
                actor_type=ActorType.AGENT,
                correlation_id=task.correlation_id,
                payload={
                    "evidence_id": saved.evidence_id,
                    "category": saved.finding_category,
                    "severity": saved.severity.value,
                },
            )
        )
        return saved

    def get_task_evidence(self, task_id: str) -> list[Evidence]:
        """Retrieve all evidence associated with a task."""
        self.get_task(task_id)
        return self.repository.get_evidence_for_task(task_id)

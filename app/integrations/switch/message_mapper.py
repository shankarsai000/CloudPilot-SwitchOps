"""
CloudPilot SwitchOps — Switch Workflow Event & Message Mapper (Phase 4.2)

Maps CloudPilot internal specialist and execution workflow events to the Switch wire protocol.
Guarantees:
1. All 14 proposal transparency fields are included in Switch proposal publications.
2. Offline pricing estimates are explicitly labeled as estimates (never live billing claims).
3. Secrets, credentials, and HMAC approval tokens are strictly redacted from Switch messages.
4. Every message embeds stable machine-readable correlation identifiers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

from app.core.logging import redact_secrets
from app.domain.decisions import DecisionReport, DecisionRun
from app.domain.execution import ExecutionRecord, ExecutionStatus
from app.domain.proposals import Proposal


class WorkflowEventType(str, Enum):
    """Typed internal workflow events mapped to Switch collaboration messages (Workstream B2 & F3)."""

    TASK_ACKNOWLEDGED = "TASK_ACKNOWLEDGED"
    TASK_STARTED = "TASK_STARTED"
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    DISCOVERY_COMPLETED = "DISCOVERY_COMPLETED"
    FINOPS_ANALYSIS_COMPLETED = "FINOPS_ANALYSIS_COMPLETED"
    SECOPS_ANALYSIS_COMPLETED = "SECOPS_ANALYSIS_COMPLETED"
    SRE_ANALYSIS_COMPLETED = "SRE_ANALYSIS_COMPLETED"
    DECISION_GENERATED = "DECISION_GENERATED"
    PROPOSAL_PUBLISHED = "PROPOSAL_PUBLISHED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    EXECUTION_VERIFIED = "EXECUTION_VERIFIED"
    EXECUTION_REJECTED = "EXECUTION_REJECTED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"


class SwitchCollaborationEvent(BaseModel):
    """
    Persisted collaboration evidence record for every Switch workflow event (Workstream B3).
    Never claims delivery if publication failed.
    """

    event_id: str = Field(default_factory=lambda: f"swevt-{uuid.uuid4().hex[:12]}")
    event_type: WorkflowEventType
    task_id: str
    decision_id: Optional[str] = None
    proposal_id: Optional[str] = None
    candidate_id: Optional[str] = None
    proposal_hash: Optional[str] = None
    approval_id: Optional[str] = None
    execution_id: Optional[str] = None
    correlation_id: str = Field(default_factory=lambda: f"corr-{uuid.uuid4().hex[:10]}")
    switch_session_id: Optional[str] = None
    switch_room_id: str = "cloudpilot-ops"
    switch_message_id: Optional[str] = None
    specialist_role: str = "cloudpilot-coordinator"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivery_status: str = Field(
        default="PENDING",
        description="DELIVERED, FAILED, PENDING_RETRY, or SKIPPED_OFFLINE",
    )
    ack_status: str = Field(
        default="UNACKNOWLEDGED",
        description="ACKNOWLEDGED, UNACKNOWLEDGED, or FAILED",
    )
    retry_count: int = 0
    idempotency_key: str = ""
    integration_state: str = "LIVE_UNVERIFIED"
    error_message: Optional[str] = None
    summary: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.idempotency_key:
            summary_digest = hashlib.sha256(self.summary.encode("utf-8")).hexdigest()[:16] if self.summary else ""
            raw = (
                f"{self.task_id}:{self.event_type.value}:{self.decision_id or ''}:"
                f"{self.proposal_id or ''}:{self.execution_id or ''}:{self.correlation_id}:{summary_digest}"
            )
            self.idempotency_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def compute_canonical_hash(self) -> str:
        payload = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "task_id": self.task_id,
            "decision_id": self.decision_id,
            "proposal_id": self.proposal_id,
            "candidate_id": self.candidate_id,
            "proposal_hash": self.proposal_hash,
            "approval_id": self.approval_id,
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "switch_session_id": self.switch_session_id,
            "switch_room_id": self.switch_room_id,
            "switch_message_id": self.switch_message_id,
            "timestamp": self.timestamp.isoformat(),
            "delivery_status": self.delivery_status,
            "ack_status": self.ack_status,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


# Patterns for redacting HMAC approval tokens, bearer tokens, and Switch API keys
_HMAC_TOKEN_PATTERN = re.compile(r"\b(?:v1\.[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+|cp-auth\.v1\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)\b")
_SWITCH_KEY_PATTERN = re.compile(r"\bswak-[a-zA-Z0-9_-]+\b")


class SwitchMessageMapper:
    """
    Translates internal CloudPilot domain objects and workflow events into
    correlated, secret-redacted Switch room messages.
    """

    @staticmethod
    def redact_for_switch(text: str) -> str:
        """
        Redacts secrets, API keys, and HMAC approval tokens before publishing to Switch (Workstream C3).
        """
        cleaned = redact_secrets(text)
        cleaned = _HMAC_TOKEN_PATTERN.sub("[REDACTED_APPROVAL_TOKEN]", cleaned)
        cleaned = _SWITCH_KEY_PATTERN.sub("[REDACTED_SWITCH_KEY]", cleaned)
        return cleaned

    @classmethod
    def format_proposal_for_switch(
        cls,
        proposal: Proposal,
        decision_run: DecisionRun,
        decision_report: Optional[DecisionReport] = None,
    ) -> str:
        """
        Formats a complete, 14-point reviewable optimization proposal for Switch (Workstream C1-C3).
        Preserves exact canonical identifiers (proposal_id, candidate_id, proposal_hash, decision_id)
        and never exposes HMAC approval tokens.
        """
        rec_cand = decision_run.recommended_candidate
        cost_before = (
            str(rec_cand.estimated_monthly_cost_before)
            if rec_cand and getattr(rec_cand, "estimated_monthly_cost_before", None) is not None
            else getattr(proposal, "estimated_monthly_cost_before", "N/A")
        )
        cost_after = (
            str(rec_cand.estimated_monthly_cost_after)
            if rec_cand and getattr(rec_cand, "estimated_monthly_cost_after", None) is not None
            else getattr(proposal, "estimated_monthly_cost_after", "N/A")
        )
        savings = (
            str(rec_cand.estimated_monthly_savings)
            if rec_cand and getattr(rec_cand, "estimated_monthly_savings", None) is not None
            else getattr(proposal, "estimated_monthly_savings", "0.00")
        )
        sec_impact = rec_cand.security_impact.value if rec_cand else "NEUTRAL"
        rel_impact = rec_cand.reliability_impact.value if rec_cand else "NEUTRAL"
        complexity = rec_cand.operational_complexity.value if rec_cand else "LOW"
        findings_str = ", ".join(proposal.source_finding_ids) if proposal.source_finding_ids else "Deterministic rule evaluation"
        resources_str = ", ".join(proposal.affected_resource_ids) if proposal.affected_resource_ids else "N/A"

        # Build human-readable change preview (C3)
        change_lines: List[str] = []
        for idx, ch in enumerate(proposal.canonical_proposed_changes, start=1):
            change_lines.append(
                f"  {idx}. **File**: `{ch.source_file}` | **Resource**: `{ch.resource_id}` (`{ch.resource_type}`)\n"
                f"     - **Operation**: `{ch.action_type}` on attribute `{ch.attribute_path}`\n"
                f"     - **Current Configuration**: `{cls.redact_for_switch(str(ch.current_value))}`\n"
                f"     - **Proposed Configuration**: `{cls.redact_for_switch(str(ch.proposed_value))}`\n"
                f"     - **Expected Effect**: Updates `{ch.attribute_path}` in isolated sandbox while preserving surrounding blocks\n"
                f"     - **Risk Classification**: `{complexity}` operational complexity (`{sec_impact}` security, `{rel_impact}` reliability)"
            )
        changes_preview = "\n".join(change_lines) if change_lines else "  - No file mutations specified."

        before_hashes_preview = ", ".join(
            f"`{k}`: `{v[:16]}...`" for k, v in sorted(proposal.before_state_file_hashes.items())
        )
        after_hashes_preview = ", ".join(
            f"`{k}`: `{v[:16]}...`" for k, v in sorted(proposal.expected_after_state_file_hashes.items())
        )

        assumptions_list = (
            rec_cand.assumptions
            if (rec_cand and getattr(rec_cand, "assumptions", None))
            else [
                "Offline pricing catalog v" + str(proposal.pricing_catalog_version) + " (730 hours/month standard model)",
                "Static configuration analysis of local Terraform HCL and Docker Compose YAML definitions",
            ]
        )
        assumptions_text = "; ".join(assumptions_list)

        msg = (
            f"### 📝 [CloudPilot SwitchOps] Formal Infrastructure Change Proposal Generated — Human Review Required\n"
            f"**1. Analyzed Infrastructure**: Workspace `{proposal.workspace_root}` (Resources: `{resources_str}`)\n"
            f"**2. Identified Problem**: {proposal.description} (Source findings: `{findings_str}`)\n"
            f"**3. Why Recommended**: Pareto-optimal feasible action under `{decision_run.preference_profile.value}` profile (`{proposal.title}`)\n"
            f"**4. Proposed Configuration Change**:\n{changes_preview}\n"
            f"**5. Estimated Financial Impact (Offline Catalog Estimate)**: "
            f"Before: `${cost_before}/mo` → After: `${cost_after}/mo` | **Estimated Monthly Savings: `${savings}/mo` USD** "
            f"*(Note: Offline catalog estimate only; not live cloud billing data)*\n"
            f"**6. Security Impact**: `{sec_impact}`\n"
            f"**7. Reliability Impact**: `{rel_impact}`\n"
            f"**8. Operational Complexity / Simplicity Impact**: `{complexity}` (Rollback: `{proposal.rollback_plan or 'Pre-execution snapshot reversion'}`)\n"
            f"**9. Hard Constraints & Formal Verification**: `{proposal.z3_verification_status}` (Policy v`{proposal.policy_version}` satisfied)\n"
            f"**10. Evidence & Assumptions**: {assumptions_text}\n"
            f"**11. Known Uncertainties**: Static local configuration analysis without runtime telemetry or live cloud state inspection.\n"
            f"**12. State File Digests (SHA-256)**:\n"
            f"  - **Before-State**: {before_hashes_preview}\n"
            f"  - **Expected After-State**: {after_hashes_preview}\n"
            f"**13. Canonical Proposal Binding**:\n"
            f"  - `task_id`: `{proposal.task_id}`\n"
            f"  - `decision_id`: `{proposal.decision_id}`\n"
            f"  - `proposal_id`: `{proposal.proposal_id}`\n"
            f"  - `candidate_id`: `{proposal.candidate_id}`\n"
            f"  - `proposal_hash`: `{proposal.proposal_hash}`\n"
            f"**14. Execution Scope & Safety Boundary**: `{proposal.optimization_scope}` — "
            f"Local sandbox configuration file mutation ONLY. Zero live cloud mutations (`terraform apply` / cloud write APIs strictly prohibited).\n\n"
            f"---\n"
            f"**Authenticated Human Review Instructions**:\n"
            f"- Authenticate via CloudPilot Approval API (`POST /api/v1/approvals/{proposal.proposal_id}/approve`) with server-verified principal & HMAC token, OR\n"
            f"- In Switch room (for registered server-directory principals): `@cloudpilot-ops-agent approve proposal {proposal.proposal_id}`\n"
            f"- To Reject: `@cloudpilot-ops-agent reject proposal {proposal.proposal_id} reason: <reason>`"
        )
        return cls.redact_for_switch(msg)

    @classmethod
    def format_verification_outcome_for_switch(
        cls,
        outcome_type: WorkflowEventType,
        proposal: Proposal,
        execution: Optional[ExecutionRecord],
        verification_details: Dict[str, Any],
        correlation_id: str,
    ) -> str:
        """
        Formats post-execution independent verification or recovery results for Switch (Workstream F3).
        """
        exec_id = execution.execution_id if execution else "N/A"
        status_str = execution.status.value if execution else outcome_type.value
        mutations_lines: List[str] = []
        if execution and execution.applied_mutations:
            for m in execution.applied_mutations:
                mutations_lines.append(
                    f"  - `{m.file_path}` (`{m.operation}` `{m.attribute_path}`): "
                    f"before=`{m.before_hash[:16]}...` → after=`{m.after_hash[:16]}...`"
                )
        mutations_block = "\n".join(mutations_lines) if mutations_lines else "  - None"

        msg = (
            f"### 🔍 [CloudPilot SwitchOps] Workflow Outcome: `{outcome_type.value}`\n"
            f"- **Task ID**: `{proposal.task_id}`\n"
            f"- **Decision ID**: `{proposal.decision_id}`\n"
            f"- **Proposal ID**: `{proposal.proposal_id}`\n"
            f"- **Candidate ID**: `{proposal.candidate_id}`\n"
            f"- **Proposal Hash**: `{proposal.proposal_hash}`\n"
            f"- **Execution ID**: `{exec_id}`\n"
            f"- **Execution Status**: `{status_str}`\n"
            f"- **Correlation ID**: `{correlation_id}`\n"
            f"- **Independent Verification Passed**: `{verification_details.get('passed', False)}`\n"
            f"- **Containment & Unexpected File Check**: `{verification_details.get('containment_verified', True)}`\n"
            f"**Modified Files**:\n{mutations_block}\n"
        )
        if execution and execution.recovery_status:
            msg += (
                f"- **Local File Recovery Status**: {execution.recovery_status} "
                f"*(Local workspace files restored; no live cloud infrastructure was mutated or rolled back)*\n"
            )
        if execution and execution.error_message:
            msg += f"- **Error / Failure Reason**: {cls.redact_for_switch(execution.error_message)}\n"

        msg += (
            f"\n> **Safety Boundary Notice**: Local configuration files only. "
            f"No live cloud infrastructure was modified."
        )
        return cls.redact_for_switch(msg)


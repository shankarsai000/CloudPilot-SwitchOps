"""
CloudPilot SwitchOps — Human-in-the-Loop Approval Service (Phase 4)

Coordinates exact proposal generation, cryptographic token issuance,
authenticated human approval/rejection lifecycle, and audit persistence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.core.errors import CloudPilotError, NotFoundError
from app.domain.approvals import (
    ApprovalPrincipal,
    ApprovalRecord,
    ApprovalStatus,
    ApprovalTokenPayload,
    ApproverRole,
)
from app.domain.candidates import Candidate
from app.domain.decisions import DecisionReport, DecisionRun
from app.domain.models import ActorType, TaskEvent, TaskEventType
from app.domain.proposals import Proposal, ProposalStatus
from app.persistence.repository import TaskRepositoryInterface
from app.services.approval.approval_token import ApprovalTokenManager
from app.services.approval.approval_validator import ApprovalValidator

logger = logging.getLogger("cloudpilot.approval.service")


class ApprovalSecurityError(CloudPilotError):
    """Raised when an approval security constraint or authorization check fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="APPROVAL_SECURITY_VIOLATION",
            status_code=403,
            details=details,
        )


class ApprovalService:
    """
    Core application service governing change proposal generation,
    cryptographic token workflows, and authorized human approvals.
    """

    def __init__(
        self,
        repository: TaskRepositoryInterface,
        token_manager: Optional[ApprovalTokenManager] = None,
        validator: Optional[ApprovalValidator] = None,
    ) -> None:
        self.repository = repository
        self.token_manager = token_manager or ApprovalTokenManager()
        self.validator = validator or ApprovalValidator()

    def generate_proposal_from_decision(
        self,
        decision_run: DecisionRun,
        candidate: Candidate,
        workspace_root: str,
        ttl_seconds: int = 3600,
        decision_report: Optional[DecisionReport] = None,
    ) -> Proposal:
        """
        Synthesizes an exact, immutable Proposal from a verified DecisionRun candidate.
        Calculates before-state and expected after-state hashes for all affected files.
        """
        norm_workspace = os.path.abspath(workspace_root)
        source_file_paths: List[str] = []
        before_hashes: Dict[str, str] = {}
        expected_after_hashes: Dict[str, str] = {}
        simulated_files: Dict[str, bytes] = {}

        # 1. Inspect affected files and enforce path security
        for ch in candidate.proposed_changes:
            src_file = ch.source_file or "main.tf"
            # Normalize path
            if os.path.isabs(src_file):
                abs_file = os.path.abspath(src_file)
            else:
                abs_file = os.path.abspath(os.path.join(norm_workspace, src_file))

            # Reject path traversal outside workspace root
            if not abs_file.startswith(norm_workspace):
                raise ApprovalSecurityError(
                    f"Security violation: proposed change targets file '{src_file}' outside workspace '{workspace_root}'"
                )

            rel_path = os.path.relpath(abs_file, norm_workspace).replace("\\", "/")
            if rel_path not in source_file_paths:
                source_file_paths.append(rel_path)

            # Calculate before-state hash from actual filesystem if available
            if os.path.isfile(abs_file):
                try:
                    if rel_path not in before_hashes:
                        with open(abs_file, "rb") as f:
                            content = f.read()
                        before_hashes[rel_path] = hashlib.sha256(content).hexdigest()
                        simulated_files[rel_path] = content

                    # Simulate expected after-state hash sequentially
                    simulated_files[rel_path] = self._simulate_file_mutation(simulated_files[rel_path], ch, rel_path)
                    expected_after_hashes[rel_path] = hashlib.sha256(simulated_files[rel_path]).hexdigest()
                except Exception as exc:
                    logger.warning("Could not read file '%s' for hash calculation: %s", abs_file, exc)
                    if rel_path not in before_hashes:
                        b_hash = hashlib.sha256(f"initial-state-{rel_path}".encode("utf-8")).hexdigest()
                        before_hashes[rel_path] = b_hash
                    expected_after_hashes[rel_path] = hashlib.sha256(f"expected-after-{rel_path}-{ch.proposed_value}".encode("utf-8")).hexdigest()
            else:
                if rel_path not in before_hashes:
                    b_hash = hashlib.sha256(f"initial-state-{rel_path}".encode("utf-8")).hexdigest()
                    before_hashes[rel_path] = b_hash
                expected_after_hashes[rel_path] = hashlib.sha256(f"expected-after-{rel_path}-{ch.proposed_value}".encode("utf-8")).hexdigest()

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        rejected_alt_summaries: List[Dict[str, Any]] = []
        if decision_report and decision_report.rejected_candidates:
            for ev in decision_report.rejected_candidates:
                rejected_alt_summaries.append({
                    "candidate_id": ev.candidate.candidate_id,
                    "title": ev.candidate.title,
                    "rejection_reasons": ev.rejection_reasons,
                })

        proposal_id = f"prop-{uuid.uuid4().hex[:10]}"
        proposal = Proposal(
            proposal_id=proposal_id,
            decision_id=decision_run.decision_id,
            task_id=decision_run.task_id,
            candidate_id=candidate.candidate_id,
            title=candidate.title,
            description=candidate.description,
            candidate_type=candidate.candidate_type,
            workspace_root=norm_workspace,
            source_finding_ids=list(candidate.source_finding_ids),
            affected_resource_ids=list(candidate.affected_resource_ids),
            source_file_paths=source_file_paths,
            canonical_proposed_changes=list(candidate.proposed_changes),
            before_state_file_hashes=before_hashes,
            expected_after_state_file_hashes=expected_after_hashes,
            proposal_hash=candidate.proposal_hash or candidate.compute_proposal_hash(),
            policy_version=candidate.policy_version,
            pricing_catalog_version=candidate.pricing_catalog_version,
            objective_model_version=decision_run.objective_model_version,
            z3_verification_status=decision_run.z3_verification_status,
            optimization_scope=decision_run.optimization_scope,
            rejected_alternatives=rejected_alt_summaries,
            estimated_monthly_savings=str(candidate.estimated_monthly_savings),
            estimated_monthly_cost_before=str(candidate.estimated_monthly_cost_before),
            estimated_monthly_cost_after=str(candidate.estimated_monthly_cost_after),
            security_impact=candidate.security_impact.value if hasattr(candidate.security_impact, "value") else str(candidate.security_impact),
            reliability_impact=candidate.reliability_impact.value if hasattr(candidate.reliability_impact, "value") else str(candidate.reliability_impact),
            operational_complexity=candidate.operational_complexity.value if hasattr(candidate.operational_complexity, "value") else str(candidate.operational_complexity),
            status=ProposalStatus.PENDING_APPROVAL,
            created_at=now,
            expires_at=expires_at,
            schema_version="1.0",
        )

        saved = self.repository.save_proposal(proposal)

        # Append audit event
        self.repository.append_event(
            TaskEvent(
                task_id=decision_run.task_id,
                correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
                event_type=TaskEventType.TASK_UPDATED,
                actor_id="cloudpilot-decision-engine",
                actor_type=ActorType.AGENT,
                payload={
                    "event": "PROPOSAL_GENERATED",
                    "proposal_id": proposal.proposal_id,
                    "proposal_hash": proposal.proposal_hash,
                    "affected_resources": proposal.affected_resource_ids,
                    "expires_at": proposal.expires_at.isoformat(),
                },
            )
        )
        logger.info(
            "Generated proposal '%s' (hash=%s) for task '%s'",
            proposal.proposal_id,
            proposal.proposal_hash[:16],
            decision_run.task_id,
        )
        return saved

    def request_approval_token(
        self,
        proposal_id: str,
        principal: ApprovalPrincipal,
        ttl_seconds: int = 3600,
    ) -> Tuple[str, ApprovalTokenPayload]:
        """
        Validates principal authorization and generates a signed HMAC-SHA256 approval token.
        """
        is_auth, auth_err = self.validator.validate_principal(principal)
        if not is_auth:
            raise ApprovalSecurityError(f"Principal authorization failed: {auth_err}")

        proposal = self.repository.get_proposal(proposal_id)
        if not proposal:
            raise NotFoundError(f"Proposal '{proposal_id}' not found", resource_type="proposal", resource_id=proposal_id)

        is_valid_prop, prop_err = self.validator.validate_proposal_for_approval(proposal)
        if not is_valid_prop:
            raise ApprovalSecurityError(f"Proposal is not eligible for approval: {prop_err}")

        token_str, token_payload = self.token_manager.issue_token(
            proposal_id=proposal.proposal_id,
            proposal_hash=proposal.proposal_hash,
            approver_id=principal.principal_id,
            approver_role=principal.role.value,
            decision_id=proposal.decision_id,
            task_id=proposal.task_id,
            ttl_seconds=ttl_seconds,
        )
        logger.info(
            "Issued approval token '%s' for proposal '%s' to approver '%s'",
            token_payload.token_id,
            proposal_id,
            principal.principal_id,
        )
        return token_str, token_payload

    def submit_approval(
        self,
        proposal_id: str,
        token_string: str,
        principal: ApprovalPrincipal,
    ) -> ApprovalRecord:
        """
        Validates the approval token, binds the approval, and transitions proposal to APPROVED.
        """
        # 1. Authorize principal
        is_auth, auth_err = self.validator.validate_principal(principal)
        if not is_auth:
            raise ApprovalSecurityError(f"Principal authorization failed: {auth_err}")

        # 2. Verify token signature and expiration
        is_valid_tok, token_payload, tok_err = self.token_manager.verify_token(token_string)
        if not is_valid_tok or not token_payload:
            raise ApprovalSecurityError(f"Approval token verification failed: {tok_err}")

        # 3. Retrieve proposal
        proposal = self.repository.get_proposal(proposal_id)
        if not proposal:
            raise NotFoundError(f"Proposal '{proposal_id}' not found", resource_type="proposal", resource_id=proposal_id)

        # 4. Validate proposal status
        is_valid_prop, prop_err = self.validator.validate_proposal_for_approval(proposal)
        if not is_valid_prop:
            raise ApprovalSecurityError(f"Proposal cannot be approved: {prop_err}")

        # 5. Strictly validate token binds to this proposal and exact proposal_hash
        is_bound, bind_err = self.validator.validate_token_against_proposal(token_payload, proposal)
        if not is_bound:
            raise ApprovalSecurityError(f"Approval token binding check failed: {bind_err}")

        # 6. Check existing approval record to prevent replay/duplicate approval
        existing_approval = self.repository.get_approval_for_proposal(proposal_id)
        if existing_approval and existing_approval.status in (ApprovalStatus.APPROVED, ApprovalStatus.CONSUMED):
            raise ApprovalSecurityError(
                f"Proposal '{proposal_id}' has already been approved (approval_id={existing_approval.approval_id})"
            )

        now = datetime.now(timezone.utc)
        approval_record = ApprovalRecord(
            approval_id=f"appr-{uuid.uuid4().hex[:10]}",
            proposal_id=proposal.proposal_id,
            proposal_hash=proposal.proposal_hash,
            approver_id=principal.principal_id,
            approver_role=principal.role,
            status=ApprovalStatus.APPROVED,
            approval_token_id=token_payload.token_id,
            decision_id=proposal.decision_id,
            task_id=proposal.task_id,
            created_at=now,
            expires_at=proposal.expires_at,
            schema_version="1.0",
        )

        # Update proposal state
        proposal.status = ProposalStatus.APPROVED
        self.repository.update_proposal(proposal)
        saved_approval = self.repository.save_approval(approval_record)

        # Audit trail
        self.repository.append_event(
            TaskEvent(
                task_id=proposal.task_id,
                correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
                event_type=TaskEventType.TASK_UPDATED,
                actor_id=principal.principal_id,
                actor_type=ActorType.HUMAN,
                payload={
                    "event": "PROPOSAL_APPROVED",
                    "approval_id": approval_record.approval_id,
                    "proposal_id": proposal.proposal_id,
                    "proposal_hash": proposal.proposal_hash,
                    "approver_id": principal.principal_id,
                    "approver_role": principal.role.value,
                    "token_id": token_payload.token_id,
                },
            )
        )
        logger.info(
            "Proposal '%s' successfully APPROVED by '%s' (%s)",
            proposal.proposal_id,
            principal.principal_id,
            principal.role.value,
        )
        return saved_approval

    def submit_rejection(
        self,
        proposal_id: str,
        principal: ApprovalPrincipal,
        reason: str,
    ) -> ApprovalRecord:
        """
        Records human rejection of a proposal and transitions proposal to REJECTED.
        """
        is_auth, auth_err = self.validator.validate_principal(principal)
        if not is_auth:
            raise ApprovalSecurityError(f"Principal authorization failed: {auth_err}")

        proposal = self.repository.get_proposal(proposal_id)
        if not proposal:
            raise NotFoundError(f"Proposal '{proposal_id}' not found", resource_type="proposal", resource_id=proposal_id)

        if proposal.status != ProposalStatus.PENDING_APPROVAL:
            raise ApprovalSecurityError(f"Cannot reject proposal in status '{proposal.status.value}'")

        now = datetime.now(timezone.utc)
        approval_record = ApprovalRecord(
            approval_id=f"appr-{uuid.uuid4().hex[:10]}",
            proposal_id=proposal.proposal_id,
            proposal_hash=proposal.proposal_hash,
            approver_id=principal.principal_id,
            approver_role=principal.role,
            status=ApprovalStatus.REJECTED,
            approval_token_id=f"tok-rejected-{uuid.uuid4().hex[:8]}",
            decision_id=proposal.decision_id,
            task_id=proposal.task_id,
            rejection_reason=reason,
            created_at=now,
            expires_at=proposal.expires_at,
            schema_version="1.0",
        )

        proposal.status = ProposalStatus.REJECTED
        self.repository.update_proposal(proposal)
        saved_approval = self.repository.save_approval(approval_record)

        self.repository.append_event(
            TaskEvent(
                task_id=proposal.task_id,
                correlation_id=f"corr-{uuid.uuid4().hex[:8]}",
                event_type=TaskEventType.TASK_UPDATED,
                actor_id=principal.principal_id,
                actor_type=ActorType.HUMAN,
                payload={
                    "event": "PROPOSAL_REJECTED",
                    "approval_id": approval_record.approval_id,
                    "proposal_id": proposal.proposal_id,
                    "approver_id": principal.principal_id,
                    "reason": reason,
                },
            )
        )
        logger.info("Proposal '%s' REJECTED by '%s': %s", proposal.proposal_id, principal.principal_id, reason)
        return saved_approval

    def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        return self.repository.get_proposal(proposal_id)

    def get_approval(self, proposal_id: str) -> Optional[ApprovalRecord]:
        return self.repository.get_approval_for_proposal(proposal_id)

    def list_proposals(
        self,
        decision_id: Optional[str] = None,
        status: Optional[ProposalStatus] = None,
    ) -> List[Proposal]:
        return self.repository.list_proposals(decision_id=decision_id, status=status)

    @staticmethod
    def _simulate_file_mutation(content: bytes, change: Any, file_name: str = "") -> bytes:
        """
        Simulates structured file mutation to calculate expected after-state hash.
        Uses ChangeApplier to guarantee exact hash parity with execution.
        """
        from app.services.execution.change_applier import ChangeApplier
        applier = ChangeApplier()
        text = content.decode("utf-8", errors="replace")
        updated_text = applier.apply_mutation_to_text(text, change, file_name)
        return updated_text.encode("utf-8")

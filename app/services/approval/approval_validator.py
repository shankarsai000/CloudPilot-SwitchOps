"""
CloudPilot SwitchOps — Approval Validator (Phase 4)

Enforces strict authorization, token consistency, proposal-hash binding,
replay prevention, and lifecycle state checks.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from app.domain.approvals import (
    ApprovalPrincipal,
    ApprovalRecord,
    ApprovalStatus,
    ApprovalTokenPayload,
    PERMITTED_APPROVAL_ROLES,
)
from app.domain.proposals import Proposal, ProposalStatus

logger = logging.getLogger("cloudpilot.approval.validator")


class ApprovalValidator:
    """
    Validates human authorization credentials, proposal invariants,
    and approval token bindings before allowing approvals or execution.
    """

    @staticmethod
    def validate_principal(principal: ApprovalPrincipal) -> Tuple[bool, Optional[str]]:
        """
        Verifies that the principal is authenticated and authorized to approve changes.
        Fails closed on unauthenticated sessions or non-privileged roles.
        """
        if not principal:
            return False, "Missing approval principal (identity cannot be anonymous)"

        if not principal.authenticated:
            return False, f"Principal '{principal.principal_id}' is unauthenticated ({principal.auth_mechanism})"

        if principal.role not in PERMITTED_APPROVAL_ROLES:
            return False, (
                f"Principal '{principal.principal_id}' has role '{principal.role.value}', "
                f"which is not authorized to grant infrastructure approvals. "
                f"Permitted roles: {[r.value for r in PERMITTED_APPROVAL_ROLES]}"
            )

        return True, None

    @staticmethod
    def validate_proposal_for_approval(
        proposal: Proposal,
        expected_hash: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates that a proposal is in a valid state to be approved or rejected.
        """
        if not proposal:
            return False, "Proposal does not exist"

        if proposal.is_expired():
            return False, f"Proposal '{proposal.proposal_id}' has expired (expired at {proposal.expires_at.isoformat()})"

        if proposal.status != ProposalStatus.PENDING_APPROVAL:
            return False, (
                f"Proposal '{proposal.proposal_id}' is in status '{proposal.status.value}', "
                f"only PENDING_APPROVAL proposals may be approved or rejected."
            )

        # Integrity verification: proposal_hash must match canonical proposed changes
        current_hash = proposal.compute_proposal_hash()
        if proposal.proposal_hash != current_hash:
            return False, (
                f"Proposal '{proposal.proposal_id}' tampering detected: "
                f"recorded hash ({proposal.proposal_hash[:16]}...) does not match computed hash ({current_hash[:16]}...)"
            )

        if expected_hash and proposal.proposal_hash != expected_hash:
            return False, (
                f"Proposal hash mismatch: expected {expected_hash[:16]}..., "
                f"got {proposal.proposal_hash[:16]}..."
            )

        return True, None

    @staticmethod
    def validate_token_against_proposal(
        payload: ApprovalTokenPayload,
        proposal: Proposal,
    ) -> Tuple[bool, Optional[str]]:
        """
        Guarantees that an approval token is strictly bound to the exact proposal and proposal_hash.
        """
        if payload.proposal_id != proposal.proposal_id:
            return False, (
                f"Token proposal_id mismatch: token for '{payload.proposal_id}', "
                f"target proposal is '{proposal.proposal_id}'"
            )

        if payload.proposal_hash != proposal.proposal_hash:
            return False, (
                f"CRITICAL: Token proposal_hash ({payload.proposal_hash[:16]}...) does not match "
                f"current proposal_hash ({proposal.proposal_hash[:16]}...). "
                f"A changed proposal strictly requires a new approval."
            )

        if payload.decision_id != proposal.decision_id:
            return False, f"Token decision correlation mismatch: {payload.decision_id} != {proposal.decision_id}"

        if payload.task_id != proposal.task_id:
            return False, f"Token task correlation mismatch: {payload.task_id} != {proposal.task_id}"

        return True, None

    @staticmethod
    def validate_approval_record_for_execution(
        approval: ApprovalRecord,
        proposal: Proposal,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifies that an approval record satisfies all preconditions before initiating execution.
        """
        if not approval:
            return False, "No approval record found for proposal"

        if approval.status == ApprovalStatus.CONSUMED:
            return False, f"Replay rejected: Approval '{approval.approval_id}' has already been consumed."

        if approval.status == ApprovalStatus.REJECTED:
            return False, f"Execution blocked: Proposal was rejected by approver (reason: {approval.rejection_reason})."

        if approval.status != ApprovalStatus.APPROVED:
            return False, f"Execution blocked: Proposal approval status is '{approval.status.value}', expected APPROVED."

        if approval.is_expired():
            return False, f"Execution blocked: Approval '{approval.approval_id}' has expired."

        if approval.proposal_id != proposal.proposal_id:
            return False, f"Approval record proposal mismatch: {approval.proposal_id} != {proposal.proposal_id}"

        if approval.proposal_hash != proposal.proposal_hash:
            return False, (
                f"Approval record proposal_hash ({approval.proposal_hash[:16]}...) does not match "
                f"current proposal_hash ({proposal.proposal_hash[:16]}...)"
            )

        return True, None

"""
CloudPilot SwitchOps — Pre-Execution Policy Engine (Phase 4)

Executes all pre-flight safety checks immediately before configuration mutation:
- Token authenticity and unconsumed status
- Proposal-hash cryptographic matching
- Approver role authorization
- Source file drift detection (before-state hash verification)
- Re-evaluation of mandatory policy invariants
- Proposal lifecycle freshness
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from app.domain.approvals import (
    ApprovalRecord,
    ApprovalStatus,
    PERMITTED_APPROVAL_ROLES,
)
from app.domain.candidates import Candidate, CandidateType, ImpactLevel, OperationalComplexity
from app.domain.policies import PolicyConfiguration
from app.domain.proposals import Proposal, ProposalStatus
from app.services.approval.approval_token import ApprovalTokenManager
from app.services.approval.approval_validator import ApprovalValidator
from app.services.decision.constraint_engine import ConstraintEngine

logger = logging.getLogger("cloudpilot.execution.policy")


class PreExecutionCheckError(Exception):
    """Raised when one or more pre-execution safety checks fail."""


class ExecutionPolicyEngine:
    """
    Enforces non-negotiable pre-flight safety gates before modifying any workspace files.
    """

    def __init__(
        self,
        token_manager: Optional[ApprovalTokenManager] = None,
        validator: Optional[ApprovalValidator] = None,
        constraint_engine: Optional[ConstraintEngine] = None,
    ) -> None:
        self.token_manager = token_manager or ApprovalTokenManager()
        self.validator = validator or ApprovalValidator()
        self.constraint_engine = constraint_engine or ConstraintEngine()

    def verify_pre_execution_safety(
        self,
        proposal: Proposal,
        approval: ApprovalRecord,
        token_string: str,
        workspace_root: str,
        policy: Optional[PolicyConfiguration] = None,
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Executes complete pre-execution safety checklist.
        Returns: (is_safe, check_results, failure_reasons)
        """
        checks: Dict[str, bool] = {}
        failure_reasons: List[str] = []

        # 1. Verify approval token authenticity and expiration
        is_valid_tok, token_payload, tok_err = self.token_manager.verify_token(token_string)
        if not is_valid_tok or not token_payload:
            checks["token_authenticity"] = False
            failure_reasons.append(f"Approval token verification failed: {tok_err}")
        else:
            checks["token_authenticity"] = True

        # 2. Verify token has not been consumed
        if approval.status == ApprovalStatus.CONSUMED or approval.consumed_at is not None:
            checks["token_unconsumed"] = False
            failure_reasons.append(f"Replay detected: Approval '{approval.approval_id}' has already been consumed.")
        else:
            checks["token_unconsumed"] = True

        # 3. Verify proposal status is APPROVED
        if proposal.status != ProposalStatus.APPROVED:
            checks["proposal_approved"] = False
            failure_reasons.append(
                f"Proposal '{proposal.proposal_id}' status is '{proposal.status.value}', expected APPROVED."
            )
        else:
            checks["proposal_approved"] = True

        # 4. Verify proposal hash matching across proposal, approval, and token
        current_proposal_hash = proposal.compute_proposal_hash()
        hashes_match = (
            proposal.proposal_hash == current_proposal_hash
            and approval.proposal_hash == proposal.proposal_hash
            and (token_payload is None or token_payload.proposal_hash == proposal.proposal_hash)
        )
        if not hashes_match:
            checks["proposal_hash_match"] = False
            failure_reasons.append(
                f"Proposal hash mismatch detected! Proposal={proposal.proposal_hash[:16]}, "
                f"Computed={current_proposal_hash[:16]}, Approval={approval.proposal_hash[:16]}"
            )
        else:
            checks["proposal_hash_match"] = True

        # 5. Verify approver role authorization
        if approval.approver_role not in PERMITTED_APPROVAL_ROLES:
            checks["approver_authorized"] = False
            failure_reasons.append(
                f"Approver '{approval.approver_id}' has unauthorized role '{approval.approver_role.value}'"
            )
        else:
            checks["approver_authorized"] = True

        # 6. Verify source file before-state drift (detect out-of-band edits)
        drift_detected = False
        norm_ws = os.path.realpath(os.path.abspath(workspace_root))
        for rel_path, expected_before_hash in proposal.before_state_file_hashes.items():
            abs_path = os.path.join(norm_ws, rel_path)
            if os.path.isfile(abs_path):
                with open(abs_path, "rb") as f:
                    actual_hash = hashlib.sha256(f.read()).hexdigest()
                if actual_hash != expected_before_hash:
                    drift_detected = True
                    failure_reasons.append(
                        f"Out-of-band file drift detected in '{rel_path}': "
                        f"expected before-hash {expected_before_hash[:16]}, current hash is {actual_hash[:16]}. "
                        f"A stale proposal requires a fresh decision and approval."
                    )
        checks["source_file_drift_free"] = not drift_detected

        # 7. Verify proposal is not expired
        if proposal.is_expired():
            checks["proposal_unexpired"] = False
            failure_reasons.append(f"Proposal '{proposal.proposal_id}' has expired.")
        else:
            checks["proposal_unexpired"] = True

        # 8. Re-evaluate hard constraints against active policy
        active_policy = policy or PolicyConfiguration()
        self.constraint_engine.policy = active_policy
        temp_candidate = Candidate(
            candidate_id=proposal.candidate_id,
            title=proposal.title,
            description=proposal.description,
            candidate_type=proposal.candidate_type,
            affected_resource_ids=proposal.affected_resource_ids,
            target_resource_ids=proposal.affected_resource_ids,
            proposed_changes=proposal.canonical_proposed_changes,
            estimated_monthly_cost_before=proposal.estimated_monthly_cost_before,
            estimated_monthly_cost_after=proposal.estimated_monthly_cost_after,
            estimated_monthly_savings=proposal.estimated_monthly_savings,
            security_impact=ImpactLevel(proposal.security_impact) if hasattr(ImpactLevel, proposal.security_impact) else ImpactLevel.NEUTRAL,
            reliability_impact=ImpactLevel(proposal.reliability_impact) if hasattr(ImpactLevel, proposal.reliability_impact) else ImpactLevel.NEUTRAL,
            operational_complexity=OperationalComplexity(proposal.operational_complexity) if hasattr(OperationalComplexity, proposal.operational_complexity) else OperationalComplexity.LOW,
            proposal_hash=proposal.proposal_hash,
        )
        is_feasible, c_results, c_reasons = self.constraint_engine.evaluate(temp_candidate)
        if not is_feasible:
            checks["hard_constraints_passed"] = False
            failure_reasons.append(f"Pre-execution constraint re-evaluation failed: {c_reasons}")
        else:
            checks["hard_constraints_passed"] = True

        is_safe = len(failure_reasons) == 0
        return is_safe, checks, failure_reasons

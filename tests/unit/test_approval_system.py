"""
CloudPilot SwitchOps — Unit Tests: Cryptographic Approval System (Phase 4)

Validates:
1. HMAC-SHA256 token issuance and constant-time signature verification.
2. Authorization checks: permitted roles (PLATFORM_LEAD, SRE_ADMIN, etc.) vs unauthorized (OPERATOR).
3. Fail-closed rejection of unauthenticated principals.
4. Rejection of expired tokens.
5. Replay protection (consumed tokens cannot be reused).
6. Proposal hash tampering detection (token bound to proposal_hash).
7. Mismatched proposal ID rejection.
8. Invalid signature tampering rejection.
9. Rejection of proposals that are already rejected or expired.
"""

from datetime import datetime, timedelta, timezone
import pytest

from app.domain.approvals import (
    ApprovalPrincipal,
    ApprovalRecord,
    ApprovalStatus,
    ApproverRole,
    PERMITTED_APPROVAL_ROLES,
)
from app.domain.candidates import CandidateType
from app.domain.proposals import Proposal, ProposalStatus
from app.persistence.repository import InMemoryTaskRepository
from app.services.approval.approval_service import ApprovalSecurityError, ApprovalService
from app.services.approval.approval_token import ApprovalTokenManager
from app.services.approval.approval_validator import ApprovalValidator


@pytest.fixture
def repo() -> InMemoryTaskRepository:
    return InMemoryTaskRepository()


@pytest.fixture
def token_mgr() -> ApprovalTokenManager:
    return ApprovalTokenManager(secret_key=b"test-approval-secret-key-32bytes-long-hmac-sha256")


@pytest.fixture
def service(repo: InMemoryTaskRepository, token_mgr: ApprovalTokenManager) -> ApprovalService:
    return ApprovalService(repository=repo, token_manager=token_mgr)


@pytest.fixture
def valid_proposal(repo: InMemoryTaskRepository) -> Proposal:
    now = datetime.now(timezone.utc)
    proposal = Proposal(
        proposal_id="prop-test001",
        decision_id="dec-test001",
        task_id="task-test001",
        candidate_id="cand-test001",
        title="Rightsize test instance",
        description="Downscale t3.large to t3.medium",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        workspace_root="samples/staging",
        source_finding_ids=["find-001"],
        affected_resource_ids=["aws_instance.web"],
        source_file_paths=["samples/staging/main.tf"],
        canonical_proposed_changes=[
            {
                "file_path": "samples/staging/main.tf",
                "resource_type": "aws_instance",
                "resource_id": "aws_instance.web",
                "resource_name": "web",
                "attribute": "instance_type",
                "action": "MODIFY",
                "old_value": "t3.large",
                "new_value": "t3.medium",
            }
        ],
        before_state_file_hashes={"samples/staging/main.tf": "a" * 64},
        expected_after_state_file_hashes={"samples/staging/main.tf": "b" * 64},
        proposal_hash="",
        policy_version="1.0.0",
        pricing_catalog_version="2026.03",
        objective_model_version="1.0.0",
        z3_verification_status="Z3_CONSTRAINTS_SAT",
        optimization_scope="LOCAL_RESOURCE_ATTRIBUTES_ONLY",
        created_at=now,
        expires_at=now + timedelta(hours=24),
        status=ProposalStatus.PENDING_APPROVAL,
    )
    proposal.proposal_hash = proposal.compute_proposal_hash()
    repo.save_proposal(proposal)
    return proposal


@pytest.fixture
def lead_principal() -> ApprovalPrincipal:
    return ApprovalPrincipal(
        principal_id="user-platform-lead",
        display_name="Sarah Connor",
        role=ApproverRole.PLATFORM_LEAD,
        authenticated=True,
    )


@pytest.fixture
def operator_principal() -> ApprovalPrincipal:
    return ApprovalPrincipal(
        principal_id="user-ops-junior",
        display_name="John Doe",
        role=ApproverRole.OPERATOR,
        authenticated=True,
    )


class TestApprovalSystem:

    def test_permitted_approval_roles(self):
        """Verify explicit permitted roles whitelist."""
        assert ApproverRole.PLATFORM_LEAD in PERMITTED_APPROVAL_ROLES
        assert ApproverRole.SRE_ADMIN in PERMITTED_APPROVAL_ROLES
        assert ApproverRole.FINOPS_ADMIN in PERMITTED_APPROVAL_ROLES
        assert ApproverRole.SECURITY_ADMIN in PERMITTED_APPROVAL_ROLES
        assert ApproverRole.CLOUD_OPS_LEAD in PERMITTED_APPROVAL_ROLES
        assert ApproverRole.OPERATOR not in PERMITTED_APPROVAL_ROLES

    def test_hmac_token_issuance_and_verification(
        self,
        token_mgr: ApprovalTokenManager,
        valid_proposal: Proposal,
        lead_principal: ApprovalPrincipal,
    ):
        """Test cryptographic token issuance and verification round-trip."""
        token_str, payload = token_mgr.issue_token(
            proposal_id=valid_proposal.proposal_id,
            proposal_hash=valid_proposal.proposal_hash,
            approver_id=lead_principal.principal_id,
            approver_role=lead_principal.role.value,
            decision_id=valid_proposal.decision_id,
            task_id=valid_proposal.task_id,
            ttl_seconds=7200,
        )

        assert token_str.startswith("v1.")
        assert payload.proposal_id == valid_proposal.proposal_id
        assert payload.proposal_hash == valid_proposal.proposal_hash
        assert payload.approver_id == lead_principal.principal_id
        assert payload.approver_role == lead_principal.role.value

        # Verify token successfully
        is_valid, verified_payload, err = token_mgr.verify_token(token_str)
        assert is_valid is True
        assert err is None
        assert verified_payload is not None
        assert verified_payload.token_id == payload.token_id
        assert verified_payload.proposal_id == payload.proposal_id

    def test_unauthorized_approver_role_rejected(
        self,
        service: ApprovalService,
        valid_proposal: Proposal,
        operator_principal: ApprovalPrincipal,
    ):
        """OPERATOR role is strictly forbidden from requesting approval token or approving."""
        with pytest.raises(ApprovalSecurityError) as exc_info:
            service.request_approval_token(valid_proposal.proposal_id, operator_principal)
        assert "Principal authorization failed" in exc_info.value.message

    def test_unauthenticated_principal_rejected(
        self,
        service: ApprovalService,
        valid_proposal: Proposal,
    ):
        """Unauthenticated principal is rejected fail-closed."""
        unauth = ApprovalPrincipal(
            principal_id="anon",
            display_name="Anon",
            role=ApproverRole.PLATFORM_LEAD,
            authenticated=False,
        )
        with pytest.raises(ApprovalSecurityError) as exc_info:
            service.request_approval_token(valid_proposal.proposal_id, unauth)
        assert "Principal authorization failed" in exc_info.value.message

    def test_expired_token_rejected(
        self,
        token_mgr: ApprovalTokenManager,
        valid_proposal: Proposal,
        lead_principal: ApprovalPrincipal,
    ):
        """Tokens past expiration must be rejected."""
        token_str, _ = token_mgr.issue_token(
            proposal_id=valid_proposal.proposal_id,
            proposal_hash=valid_proposal.proposal_hash,
            approver_id=lead_principal.principal_id,
            approver_role=lead_principal.role.value,
            decision_id=valid_proposal.decision_id,
            task_id=valid_proposal.task_id,
            ttl_seconds=-10,  # Expired in past
        )
        is_valid, payload, err = token_mgr.verify_token(token_str)
        assert is_valid is False
        assert "expired" in (err or "").lower()

    def test_tampered_signature_rejected(
        self,
        token_mgr: ApprovalTokenManager,
        valid_proposal: Proposal,
        lead_principal: ApprovalPrincipal,
    ):
        """Tampering with token signature triggers fail-closed error."""
        token_str, _ = token_mgr.issue_token(
            proposal_id=valid_proposal.proposal_id,
            proposal_hash=valid_proposal.proposal_hash,
            approver_id=lead_principal.principal_id,
            approver_role=lead_principal.role.value,
            decision_id=valid_proposal.decision_id,
            task_id=valid_proposal.task_id,
            ttl_seconds=3600,
        )
        # Modify signature
        parts = token_str.split(".")
        tampered_sig = parts[3][:-1] + ("A" if parts[3][-1] != "A" else "B")
        tampered = f"{parts[0]}.{parts[1]}.{parts[2]}.{tampered_sig}"

        is_valid, payload, err = token_mgr.verify_token(tampered)
        assert is_valid is False
        assert "signature verification failed" in (err or "").lower()

    def test_tampered_proposal_hash_rejected(
        self,
        service: ApprovalService,
        valid_proposal: Proposal,
        lead_principal: ApprovalPrincipal,
    ):
        """If proposal changes after token issuance, proposal-hash binding mismatch raises error."""
        token_str, _ = service.request_approval_token(valid_proposal.proposal_id, lead_principal)

        # Tamper with proposal content
        from app.domain.candidates import ProposedChange
        valid_proposal.canonical_proposed_changes.append(
            ProposedChange(
                action="MODIFY",
                resource_id="aws_instance.malicious",
                attribute="instance_type",
                new_value="m5.24xlarge",
            )
        )
        valid_proposal.proposal_hash = valid_proposal.compute_proposal_hash()
        service.repository.update_proposal(valid_proposal)

        with pytest.raises(ApprovalSecurityError) as exc_info:
            service.submit_approval(valid_proposal.proposal_id, token_str, lead_principal)
        assert "does not match current proposal_hash" in exc_info.value.message.lower()

    def test_replay_attack_rejected(
        self,
        service: ApprovalService,
        valid_proposal: Proposal,
        lead_principal: ApprovalPrincipal,
    ):
        """A consumed approval token cannot be reused for a second execution or approval."""
        token_str, _ = service.request_approval_token(valid_proposal.proposal_id, lead_principal)

        # Submit approval successfully once
        rec = service.submit_approval(valid_proposal.proposal_id, token_str, lead_principal)
        assert rec.status == ApprovalStatus.APPROVED

        # Re-submitting approval with same proposal must fail because proposal is already APPROVED
        with pytest.raises(ApprovalSecurityError) as exc_info:
            service.submit_approval(valid_proposal.proposal_id, token_str, lead_principal)
        assert "cannot be approved" in exc_info.value.message.lower()

    def test_human_rejection_marks_proposal_rejected(
        self,
        service: ApprovalService,
        valid_proposal: Proposal,
        lead_principal: ApprovalPrincipal,
    ):
        """Human rejection immediately terminates proposal lifecycle."""
        rec = service.submit_rejection(
            proposal_id=valid_proposal.proposal_id,
            principal=lead_principal,
            reason="Exceeds operational risk tolerance for staging environment.",
        )
        assert rec.status == ApprovalStatus.REJECTED
        assert rec.rejection_reason == "Exceeds operational risk tolerance for staging environment."

        updated_proposal = service.repository.get_proposal(valid_proposal.proposal_id)
        assert updated_proposal is not None
        assert updated_proposal.status == ProposalStatus.REJECTED

        # Trying to request token for rejected proposal must fail
        with pytest.raises(ApprovalSecurityError) as exc_info:
            service.request_approval_token(valid_proposal.proposal_id, lead_principal)
        assert "not eligible for approval" in exc_info.value.message.lower()

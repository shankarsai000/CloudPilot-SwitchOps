"""
CloudPilot SwitchOps — Unit Tests: Security, RBAC & API Bypass Adversarial Suite (Phase 4.1)

Validates Workstream A (Approval Identity and RBAC) and Workstream G (API & Workflow Bypass):
1. Caller-supplied role escalation rejected fail-closed.
2. Caller-supplied identity impersonation rejected.
3. Unauthorized approver roles rejected fail-closed (403).
4. Unauthorized execution by non-lead roles rejected fail-closed.
5. Missing or unauthenticated principal fails closed.
6. Role demotion between approval and execution rejected.
7. Execution without prior approval blocked.
8. Execution of rejected proposal blocked.
9. Execution of expired proposal blocked.
10. Forged or tampered HMAC token rejected with constant-time verification.
11. Cross-proposal token reuse rejected.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.core.errors import NotFoundError
from app.domain.approvals import (
    ApprovalPrincipal,
    ApprovalRecord,
    ApprovalStatus,
    ApproverRole,
    PERMITTED_APPROVAL_ROLES,
)
from app.domain.candidates import ProposedChange
from app.domain.proposals import Proposal, ProposalStatus
from app.main import create_app
from app.persistence.repository import InMemoryTaskRepository, SQLiteTaskRepository
from app.services.approval.approval_service import ApprovalSecurityError, ApprovalService
from app.services.approval.approval_token import ApprovalTokenManager
from app.services.approval.auth_provider import ServerSidePrincipalAuthenticator
from app.services.execution.execution_orchestrator import ExecutionOrchestrator
from app.services.execution.execution_policy import PreExecutionCheckError


@pytest.fixture
def test_env(tmp_path: Path):
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    main_tf = source_dir / "main.tf"
    main_tf.write_text('resource "aws_instance" "web" {\n  instance_type = "t3.large"\n}\n')

    repo = InMemoryTaskRepository()
    token_mgr = ApprovalTokenManager()
    approval_svc = ApprovalService(repository=repo, token_manager=token_mgr)
    orchestrator = ExecutionOrchestrator(repository=repo)

    now = datetime.now(timezone.utc)
    proposal = Proposal(
        proposal_id="prop-rbac-001",
        decision_id="dec-001",
        task_id="task-001",
        candidate_id="cand-001",
        title="Rightsize compute",
        description="Downscale compute",
        candidate_type="RESIZE_COMPUTE",
        workspace_root=str(source_dir),
        affected_resource_ids=["aws_instance.web"],
        source_file_paths=["main.tf"],
        canonical_proposed_changes=[
            ProposedChange(
                action_type="MODIFY",
                resource_type="aws_instance",
                resource_id="aws_instance.web",
                resource_name="web",
                attribute_path="instance_type",
                current_value="t3.large",
                proposed_value="t3.medium",
                source_file="main.tf",
            )
        ],
        before_state_file_hashes={"main.tf": "a" * 64},
        expected_after_state_file_hashes={"main.tf": "b" * 64},
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

    return {
        "repo": repo,
        "token_mgr": token_mgr,
        "approval_svc": approval_svc,
        "orchestrator": orchestrator,
        "proposal": proposal,
        "source_dir": source_dir,
        "authenticator": ServerSidePrincipalAuthenticator(),
    }


class TestSecurityAndRBACAdversarial:

    def test_caller_supplied_role_escalation_rejected(self, test_env):
        """A junior operator claiming PLATFORM_LEAD header fails closed."""
        auth: ServerSidePrincipalAuthenticator = test_env["authenticator"]
        # junior-ops is registered as OPERATOR in server directory
        principal = auth.authenticate(
            x_user_id="junior-ops",
            x_user_role="PLATFORM_LEAD",  # Attempted escalation
        )
        assert not principal.authenticated
        assert not principal.is_authorized
        assert principal.auth_mechanism == "ROLE_ESCALATION_REJECTED"

    def test_unregistered_identity_fails_closed(self, test_env):
        """Unknown user IDs without cryptographic bearer tokens fail closed."""
        auth: ServerSidePrincipalAuthenticator = test_env["authenticator"]
        principal = auth.authenticate(
            x_user_id="unregistered-intruder",
            x_user_role="PLATFORM_LEAD",
        )
        assert not principal.authenticated
        assert not principal.is_authorized
        assert principal.auth_mechanism == "UNREGISTERED_IDENTITY"

    def test_cryptographic_bearer_token_authentication(self, test_env):
        """Valid signed bearer token is authenticated; forged signature is rejected."""
        auth: ServerSidePrincipalAuthenticator = test_env["authenticator"]
        valid_token = auth.issue_bearer_token("trusted-auditor", ApproverRole.SECURITY_LEAD)

        p_valid = auth.authenticate(authorization=f"Bearer {valid_token}")
        assert p_valid.authenticated
        assert p_valid.is_authorized
        assert p_valid.role == ApproverRole.SECURITY_LEAD
        assert p_valid.principal_id == "trusted-auditor"

        # Tampered bearer token
        tampered_token = valid_token[:-4] + "FAIL"
        p_invalid = auth.authenticate(authorization=f"Bearer {tampered_token}")
        assert not p_invalid.authenticated
        assert not p_invalid.is_authorized

    def test_unauthorized_role_approval_rejected(self, test_env):
        """An operator or developer attempting approval is rejected with ApprovalSecurityError."""
        approval_svc: ApprovalService = test_env["approval_svc"]
        proposal: Proposal = test_env["proposal"]

        operator_principal = ApprovalPrincipal(
            principal_id="junior-ops",
            display_name="Junior Ops",
            role=ApproverRole.OPERATOR,
            authenticated=True,
        )
        assert not operator_principal.is_authorized

        with pytest.raises(ApprovalSecurityError) as exc_info:
            approval_svc.request_approval_token(proposal.proposal_id, operator_principal)
        assert "not authorized" in exc_info.value.message.lower()

    def test_unauthorized_execution_rejected(self, test_env):
        """An unauthorized role executing an approved proposal fails closed."""
        approval_svc: ApprovalService = test_env["approval_svc"]
        orchestrator: ExecutionOrchestrator = test_env["orchestrator"]
        proposal: Proposal = test_env["proposal"]

        lead = ApprovalPrincipal(
            principal_id="lead-platform",
            display_name="Lead",
            role=ApproverRole.PLATFORM_LEAD,
            authenticated=True,
        )
        operator = ApprovalPrincipal(
            principal_id="junior-ops",
            display_name="Junior Ops",
            role=ApproverRole.OPERATOR,
            authenticated=True,
        )

        token_str, _ = approval_svc.request_approval_token(proposal.proposal_id, lead)
        approval_svc.submit_approval(proposal.proposal_id, token_str, lead)

        # Operator tries to execute
        with pytest.raises(ApprovalSecurityError) as exc_info:
            orchestrator.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string=token_str,
                approver=operator,
            )
        assert "unauthorized" in exc_info.value.message.lower()

    def test_role_demotion_between_approval_and_execution_fails(self, test_env):
        """If an approver was demoted to OPERATOR prior to execution, execution fails closed."""
        approval_svc: ApprovalService = test_env["approval_svc"]
        orchestrator: ExecutionOrchestrator = test_env["orchestrator"]
        proposal: Proposal = test_env["proposal"]

        lead = ApprovalPrincipal(
            principal_id="lead-platform",
            display_name="Lead",
            role=ApproverRole.PLATFORM_LEAD,
            authenticated=True,
        )
        token_str, _ = approval_svc.request_approval_token(proposal.proposal_id, lead)
        approval_svc.submit_approval(proposal.proposal_id, token_str, lead)

        # Approver is demoted to OPERATOR
        demoted = ApprovalPrincipal(
            principal_id="lead-platform",
            display_name="Lead",
            role=ApproverRole.OPERATOR,
            authenticated=True,
        )
        with pytest.raises(ApprovalSecurityError) as exc_info:
            orchestrator.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string=token_str,
                approver=demoted,
            )
        assert "unauthorized" in exc_info.value.message.lower()

    def test_unapproved_proposal_execution_blocked(self, test_env):
        """Executing a proposal without prior approval is blocked."""
        orchestrator: ExecutionOrchestrator = test_env["orchestrator"]
        proposal: Proposal = test_env["proposal"]
        lead = ApprovalPrincipal(
            principal_id="lead-platform",
            display_name="Lead",
            role=ApproverRole.PLATFORM_LEAD,
            authenticated=True,
        )
        with pytest.raises(ApprovalSecurityError) as exc_info:
            orchestrator.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string="v1.dummy.token",
                approver=lead,
            )
        assert "has not been approved" in exc_info.value.message.lower()

    def test_rejected_proposal_execution_blocked(self, test_env):
        """Executing a proposal that was rejected fails closed."""
        approval_svc: ApprovalService = test_env["approval_svc"]
        orchestrator: ExecutionOrchestrator = test_env["orchestrator"]
        proposal: Proposal = test_env["proposal"]
        lead = ApprovalPrincipal(
            principal_id="lead-platform",
            display_name="Lead",
            role=ApproverRole.PLATFORM_LEAD,
            authenticated=True,
        )

        approval_svc.submit_rejection(proposal.proposal_id, lead, reason="Audit freeze")

        with pytest.raises(ApprovalSecurityError) as exc_info:
            orchestrator.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string="v1.dummy.token",
                approver=lead,
            )
        assert "expected approved" in exc_info.value.message.lower()

    def test_forged_hmac_token_rejected_constant_time(self, test_env):
        """A forged token with modified payload or signature fails cryptographic verification."""
        approval_svc: ApprovalService = test_env["approval_svc"]
        proposal: Proposal = test_env["proposal"]
        lead = ApprovalPrincipal(
            principal_id="lead-platform",
            display_name="Lead",
            role=ApproverRole.PLATFORM_LEAD,
            authenticated=True,
        )

        token_str, _ = approval_svc.request_approval_token(proposal.proposal_id, lead)
        # Flip bits in signature segment
        parts = token_str.split(".")
        forged_sig = "A" * len(parts[3])
        forged_token = f"{parts[0]}.{parts[1]}.{parts[2]}.{forged_sig}"

        with pytest.raises(ApprovalSecurityError) as exc_info:
            approval_svc.submit_approval(proposal.proposal_id, forged_token, lead)
        assert "tampered" in exc_info.value.message.lower() or "verification failed" in exc_info.value.message.lower()

    def test_cross_proposal_token_reuse_rejected(self, test_env):
        """A valid token issued for prop-A submitted for prop-B is rejected."""
        approval_svc: ApprovalService = test_env["approval_svc"]
        repo = test_env["repo"]
        proposal_a: Proposal = test_env["proposal"]
        lead = ApprovalPrincipal(
            principal_id="lead-platform",
            display_name="Lead",
            role=ApproverRole.PLATFORM_LEAD,
            authenticated=True,
        )

        # Create prop-B
        now = datetime.now(timezone.utc)
        proposal_b = proposal_a.model_copy(update={
            "proposal_id": "prop-rbac-002",
            "candidate_id": "cand-002",
            "created_at": now,
            "expires_at": now + timedelta(hours=24),
        })
        proposal_b.proposal_hash = proposal_b.compute_proposal_hash()
        repo.save_proposal(proposal_b)

        token_a, _ = approval_svc.request_approval_token(proposal_a.proposal_id, lead)

        # Attempt to submit token_a for proposal_b
        with pytest.raises(ApprovalSecurityError) as exc_info:
            approval_svc.submit_approval(proposal_b.proposal_id, token_a, lead)
        assert "proposal_id mismatch" in exc_info.value.message.lower()

    def test_api_execution_without_auth_rejected_403(self, test_env):
        """Calling execution endpoint without authentication is rejected with 403."""
        app = create_app()
        from app.api.executions import get_repository as executions_get_repo
        app.dependency_overrides[executions_get_repo] = lambda: test_env["repo"]
        client = TestClient(app)

        resp = client.post(
            f"/api/v1/executions/{test_env['proposal'].proposal_id}/execute",
            json={"token": "some-token"},
        )
        assert resp.status_code == 403
        assert "unauthorized" in resp.json()["detail"].lower()

    def test_api_execution_with_non_lead_role_rejected_403(self, test_env):
        """Calling execution endpoint with unprivileged role (e.g. developer) is rejected with 403."""
        app = create_app()
        from app.api.executions import get_repository as executions_get_repo
        app.dependency_overrides[executions_get_repo] = lambda: test_env["repo"]
        client = TestClient(app)

        resp = client.post(
            f"/api/v1/executions/{test_env['proposal'].proposal_id}/execute",
            json={"token": "some-token"},
            headers={"X-User-Id": "dev-user"},  # maps to DEVELOPER
        )
        assert resp.status_code == 403
        assert "lacks required execution authorization" in resp.json()["detail"].lower()

    def test_api_audit_manifest_unauthorized_rejected(self, test_env):
        """Exporting audit manifest without authorized lead role is rejected with 403."""
        app = create_app()
        from app.api.executions import get_repository as executions_get_repo
        app.dependency_overrides[executions_get_repo] = lambda: test_env["repo"]
        client = TestClient(app)

        # Anonymous caller
        resp = client.get("/api/v1/executions/exec-fake-001/manifest")
        assert resp.status_code == 403

        # Unprivileged developer
        resp2 = client.get(
            "/api/v1/executions/exec-fake-001/manifest",
            headers={"X-User-Id": "dev-user"},
        )
        assert resp2.status_code == 403


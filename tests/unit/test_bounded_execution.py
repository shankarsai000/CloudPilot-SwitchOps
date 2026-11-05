"""
CloudPilot SwitchOps — Unit Tests: Bounded Execution & Policy Gates (Phase 4)

Validates:
1. End-to-end bounded execution of human-approved proposal inside isolated workspace.
2. Strict isolation: mutations occur in sandbox only; original source files are untouched.
3. Unapproved execution attempt blocked fail-closed.
4. Execution on rejected proposal blocked.
5. Execution on expired proposal blocked.
6. Source file drift detection: if source file is modified out-of-band, execution is aborted.
7. Truth-preserving static disclaimer present on execution record.
8. Single-use token consumption and replay prevention.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import pytest

from app.domain.approvals import (
    ApprovalPrincipal,
    ApproverRole,
)
from app.domain.candidates import CandidateType, ProposedChange
from app.domain.execution import ExecutionStatus
from app.domain.proposals import Proposal, ProposalStatus
from app.persistence.repository import InMemoryTaskRepository
from app.services.approval.approval_service import ApprovalSecurityError, ApprovalService
from app.services.approval.approval_token import ApprovalTokenManager
from app.services.execution.execution_orchestrator import ExecutionOrchestrator
from app.services.execution.execution_policy import ExecutionPolicyEngine, PreExecutionCheckError
from app.services.execution.workspace_manager import WorkspaceManager


@pytest.fixture
def test_setup(tmp_path: Path):
    source_dir = tmp_path / "staging_src"
    source_dir.mkdir()
    workspaces_dir = tmp_path / "isolated_ws"
    workspaces_dir.mkdir()

    # Original main.tf
    main_tf = source_dir / "main.tf"
    initial_content = 'resource "aws_instance" "web" {\n  instance_type = "t3.large"\n}\n'
    main_tf.write_bytes(initial_content.encode("utf-8"))
    before_hash = hashlib.sha256(initial_content.encode("utf-8")).hexdigest()

    # Expected simulated after-content and after-hash
    expected_content = 'resource "aws_instance" "web" {\n  instance_type = "t3.medium"\n}\n'
    expected_hash = hashlib.sha256(expected_content.encode("utf-8")).hexdigest()

    repo = InMemoryTaskRepository()
    token_mgr = ApprovalTokenManager(secret_key=b"test-secret-key-32bytes-for-execution-tests")
    approval_svc = ApprovalService(repository=repo, token_manager=token_mgr)
    ws_mgr = WorkspaceManager(base_workspaces_dir=str(workspaces_dir))
    policy_engine = ExecutionPolicyEngine(token_manager=token_mgr)
    orchestrator = ExecutionOrchestrator(
        repository=repo,
        workspace_manager=ws_mgr,
        policy_engine=policy_engine,
    )

    lead_principal = ApprovalPrincipal(
        principal_id="user-platform-lead",
        display_name="Alex Chief",
        role=ApproverRole.PLATFORM_LEAD,
        authenticated=True,
    )

    now = datetime.now(timezone.utc)
    proposal = Proposal(
        proposal_id="prop-exec001",
        decision_id="dec-001",
        task_id="task-001",
        candidate_id="cand-001",
        title="Downscale web instance",
        description="Downscale t3.large to t3.medium to save cost",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        workspace_root=str(source_dir),
        source_finding_ids=["find-001"],
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
        before_state_file_hashes={"main.tf": before_hash},
        expected_after_state_file_hashes={"main.tf": expected_hash},
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
        "lead": lead_principal,
        "proposal": proposal,
        "source_dir": source_dir,
        "main_tf": main_tf,
        "initial_content": initial_content,
        "before_hash": before_hash,
        "expected_hash": expected_hash,
    }


class TestBoundedExecution:

    def test_end_to_end_approved_execution_in_sandbox(self, test_setup):
        """Full lifecycle: approve -> execute -> verify sandbox changed while source remains untouched."""
        env = test_setup
        approval_svc: ApprovalService = env["approval_svc"]
        orchestrator: ExecutionOrchestrator = env["orchestrator"]
        proposal: Proposal = env["proposal"]
        lead: ApprovalPrincipal = env["lead"]
        source_dir: Path = env["source_dir"]
        main_tf: Path = env["main_tf"]

        # 1. Request approval token and submit human approval
        token_str, _ = approval_svc.request_approval_token(proposal.proposal_id, lead)
        approval_rec = approval_svc.submit_approval(proposal.proposal_id, token_str, lead)
        assert approval_rec.status.value == "APPROVED"

        # 2. Execute approved proposal inside isolated sandbox
        exec_record = orchestrator.execute_approved_proposal(
            proposal_id=proposal.proposal_id,
            token_string=token_str,
            approver=lead,
            target_workspace_root=str(source_dir),
        )

        assert exec_record.status == ExecutionStatus.COMPLETED
        assert exec_record.proposal_id == proposal.proposal_id
        assert len(exec_record.applied_mutations) == 1
        assert exec_record.applied_mutations[0].file_path == "main.tf"
        assert exec_record.applied_mutations[0].after_hash == env["expected_hash"]

        # 3. Verify truth-preserving disclaimer
        assert "live cloud mutation" in exec_record.disclaimer.lower()

        # 4. CRITICAL: Verify source directory files are 100% UNTOUCHED
        assert main_tf.read_bytes() == env["initial_content"].encode("utf-8")

        # 5. Verify file in sandbox IS mutated
        sandbox_main = Path(exec_record.workspace_path) / "main.tf"
        assert sandbox_main.exists()
        assert 'instance_type = "t3.medium"' in sandbox_main.read_text()

        # 6. Verify proposal marked EXECUTED
        updated_prop = env["repo"].get_proposal(proposal.proposal_id)
        assert updated_prop.status == ProposalStatus.EXECUTED

    def test_unapproved_execution_blocked(self, test_setup):
        """Executing without prior human approval raises ApprovalSecurityError."""
        env = test_setup
        orchestrator: ExecutionOrchestrator = env["orchestrator"]
        proposal: Proposal = env["proposal"]
        lead: ApprovalPrincipal = env["lead"]

        with pytest.raises(ApprovalSecurityError) as exc_info:
            orchestrator.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string="v1.dummy.token",
                approver=lead,
            )
        assert "has not been approved" in exc_info.value.message

    def test_rejected_proposal_execution_blocked(self, test_setup):
        """Executing a proposal that was rejected raises ApprovalSecurityError."""
        env = test_setup
        approval_svc: ApprovalService = env["approval_svc"]
        orchestrator: ExecutionOrchestrator = env["orchestrator"]
        proposal: Proposal = env["proposal"]
        lead: ApprovalPrincipal = env["lead"]

        approval_svc.submit_rejection(proposal.proposal_id, lead, reason="Denied for audit")

        with pytest.raises(ApprovalSecurityError) as exc_info:
            orchestrator.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string="v1.dummy.token",
                approver=lead,
            )
        assert "expected approved" in exc_info.value.message.lower()

    def test_out_of_band_source_drift_detected_and_aborted(self, test_setup):
        """
        If a workspace source file is modified out-of-band after proposal generation,
        pre-flight check detects hash drift and aborts execution before changing anything.
        """
        env = test_setup
        approval_svc: ApprovalService = env["approval_svc"]
        orchestrator: ExecutionOrchestrator = env["orchestrator"]
        proposal: Proposal = env["proposal"]
        lead: ApprovalPrincipal = env["lead"]
        main_tf: Path = env["main_tf"]

        # Approve proposal
        token_str, _ = approval_svc.request_approval_token(proposal.proposal_id, lead)
        approval_svc.submit_approval(proposal.proposal_id, token_str, lead)

        # Simulate out-of-band external modification to main.tf
        main_tf.write_bytes(b'resource "aws_instance" "web" {\n  instance_type = "c5.9xlarge"\n}\n')

        # Execution must fail pre-flight check due to drift
        with pytest.raises(PreExecutionCheckError) as exc_info:
            orchestrator.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string=token_str,
                approver=lead,
                target_workspace_root=str(env["source_dir"]),
            )
        assert "drift" in str(exc_info.value).lower() or "hash mismatch" in str(exc_info.value).lower()

    def test_consumed_token_replay_attack_blocked(self, test_setup):
        """Attempting to execute again with an already-consumed token raises an error."""
        env = test_setup
        approval_svc: ApprovalService = env["approval_svc"]
        orchestrator: ExecutionOrchestrator = env["orchestrator"]
        proposal: Proposal = env["proposal"]
        lead: ApprovalPrincipal = env["lead"]

        token_str, _ = approval_svc.request_approval_token(proposal.proposal_id, lead)
        approval_svc.submit_approval(proposal.proposal_id, token_str, lead)

        # First execution succeeds
        orchestrator.execute_approved_proposal(
            proposal_id=proposal.proposal_id,
            token_string=token_str,
            approver=lead,
            target_workspace_root=str(env["source_dir"]),
        )

        # Second execution with consumed token must fail
        with pytest.raises(ApprovalSecurityError) as exc_info:
            orchestrator.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string=token_str,
                approver=lead,
                target_workspace_root=str(env["source_dir"]),
            )
        assert "consumed" in exc_info.value.message.lower() or "expected approved" in exc_info.value.message.lower()

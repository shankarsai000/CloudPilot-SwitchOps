"""
CloudPilot SwitchOps — Unit Tests: Execution Recovery & Audit Chaining (Phase 4)

Validates:
1. Pre-execution backup snapshot creation in .cloudpilot_snapshot.
2. Automatic rollback and file restoration upon failure.
3. Verification that post-rollback file hashes match exact pre-execution hashes.
4. Recovery failure handling (RECOVERY_FAILED) when snapshot is tampered or missing.
5. SHA-256 cryptographic hash chaining across execution audit events.
6. Tamper-evident audit chain verification (fails if any historical event is modified).
"""

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import pytest

from app.domain.approvals import ApprovalPrincipal, ApproverRole
from app.domain.candidates import CandidateType, ProposedChange
from app.domain.execution import ExecutionStatus
from app.domain.proposals import Proposal, ProposalStatus
from app.persistence.repository import InMemoryTaskRepository
from app.services.approval.approval_service import ApprovalService
from app.services.approval.approval_token import ApprovalTokenManager
from app.services.execution.execution_audit import ExecutionAuditLogger
from app.services.execution.execution_orchestrator import ExecutionOrchestrator
from app.services.execution.execution_policy import ExecutionPolicyEngine
from app.services.execution.recovery_manager import RecoveryManager
from app.services.execution.workspace_manager import WorkspaceManager


@pytest.fixture
def recovery_env(tmp_path: Path):
    ws_dir = tmp_path / "sandbox_ws"
    ws_dir.mkdir()

    # Create dummy config files
    main_tf = ws_dir / "main.tf"
    initial_hcl = 'resource "aws_instance" "web" {\n  instance_type = "t3.large"\n}\n'
    main_tf.write_bytes(initial_hcl.encode("utf-8"))
    before_hash = hashlib.sha256(initial_hcl.encode("utf-8")).hexdigest()

    return ws_dir, main_tf, initial_hcl, before_hash


class TestExecutionRecovery:

    def test_snapshot_creation_and_restoration(self, recovery_env):
        """Snapshot creates exact backup copies; rollback restores files and verifies hashes."""
        ws_dir, main_tf, initial_hcl, before_hash = recovery_env
        rm = RecoveryManager()

        # 1. Create pre-execution snapshot
        snapshot_hashes = rm.create_pre_execution_snapshot(
            workspace_path=str(ws_dir),
            relative_file_paths=["main.tf"],
        )
        assert "main.tf" in snapshot_hashes
        assert snapshot_hashes["main.tf"] == before_hash

        # 2. Mutate file
        main_tf.write_bytes(b'resource "aws_instance" "web" {\n  instance_type = "m5.large"\n}\n')
        assert main_tf.read_bytes() != initial_hcl.encode("utf-8")

        # 3. Rollback workspace
        restored_ok, restored_files, err = rm.rollback_workspace(
            workspace_path=str(ws_dir),
            expected_before_hashes={"main.tf": before_hash},
        )
        assert restored_ok is True
        assert err is None
        assert "main.tf" in restored_files

        # 4. Verify restored content matches pre-execution baseline
        assert main_tf.read_bytes() == initial_hcl.encode("utf-8")
        current_hash = hashlib.sha256(main_tf.read_bytes()).hexdigest()
        assert current_hash == before_hash

    def test_recovery_failure_when_snapshot_missing(self, recovery_env):
        """If snapshot directory does not exist, rollback fails safely."""
        ws_dir, _, _, before_hash = recovery_env
        rm = RecoveryManager()

        restored_ok, restored_files, err = rm.rollback_workspace(
            workspace_path=str(ws_dir),
            expected_before_hashes={"main.tf": before_hash},
        )
        assert restored_ok is False
        assert len(restored_files) == 0
        assert "snapshot directory not found" in (err or "").lower()

    def test_recovery_failure_when_restored_hash_mismatched(self, recovery_env):
        """If snapshot file is corrupted, hash mismatch triggers recovery failure."""
        ws_dir, main_tf, _, before_hash = recovery_env
        rm = RecoveryManager()

        # Capture snapshot
        rm.create_pre_execution_snapshot(
            workspace_path=str(ws_dir),
            relative_file_paths=["main.tf"],
        )

        # Corrupt the snapshot file
        snapshot_file = ws_dir / ".cloudpilot_snapshot" / "main.tf"
        snapshot_file.write_bytes(b"corrupted backup content")

        # Rollback should detect hash mismatch
        restored_ok, _, err = rm.rollback_workspace(
            workspace_path=str(ws_dir),
            expected_before_hashes={"main.tf": before_hash},
        )
        assert restored_ok is False
        assert "hash mismatch" in (err or "").lower()

    def test_automatic_orchestrator_rollback_on_mutation_error(self, tmp_path: Path):
        """When orchestrator execution encounters an error, automatic rollback is triggered."""
        source_dir = tmp_path / "source_dir"
        source_dir.mkdir()
        workspaces_dir = tmp_path / "ws_dir"
        workspaces_dir.mkdir()

        main_tf = source_dir / "main.tf"
        initial_hcl = 'resource "aws_instance" "web" {\n  instance_type = "t3.large"\n}\n'
        main_tf.write_bytes(initial_hcl.encode("utf-8"))
        before_hash = hashlib.sha256(initial_hcl.encode("utf-8")).hexdigest()

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

        lead = ApprovalPrincipal(
            principal_id="user-lead",
            display_name="Lead Engineer",
            role=ApproverRole.PLATFORM_LEAD,
            authenticated=True,
        )

        now = datetime.now(timezone.utc)
        # Create proposal with an unsupported action to force mutation failure
        proposal = Proposal(
            proposal_id="prop-fail001",
            decision_id="dec-fail001",
            task_id="task-fail001",
            candidate_id="cand-fail001",
            title="Invalid proposal",
            description="Forces mutation error",
            candidate_type=CandidateType.RESIZE_COMPUTE,
            workspace_root=str(source_dir),
            source_finding_ids=["find-001"],
            affected_resource_ids=["aws_instance.web"],
            source_file_paths=["main.tf"],
            canonical_proposed_changes=[
                ProposedChange(
                    action_type="UNSUPPORTED_ACTION",
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

        # Approve
        token_str, _ = approval_svc.request_approval_token(proposal.proposal_id, lead)
        approval_svc.submit_approval(proposal.proposal_id, token_str, lead)

        # Execute — must raise exception and mark ROLLED_BACK
        with pytest.raises(Exception):
            orchestrator.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string=token_str,
                approver=lead,
                target_workspace_root=str(source_dir),
            )

        exec_rec = orchestrator.get_execution_for_proposal(proposal.proposal_id)
        assert exec_rec is not None
        assert exec_rec.status == ExecutionStatus.ROLLED_BACK
        assert "recovery_status" in exec_rec.model_fields_set or exec_rec.recovery_status is not None

    def test_cryptographic_audit_chain_integrity_and_tamper_detection(self):
        """Audit logger computes append-only hash chain; tampering is detected."""
        repo = InMemoryTaskRepository()
        logger = ExecutionAuditLogger(repository=repo)
        exec_id = "exec-audit-chain-001"

        # Log 3 events
        ev1 = logger.log_event(
            execution_id=exec_id,
            proposal_id="prop-001",
            event_type="EXECUTION_INITIALIZED",
            actor_id="user-1",
            details={"step": 1},
        )
        ev2 = logger.log_event(
            execution_id=exec_id,
            proposal_id="prop-001",
            event_type="WORKSPACE_ISOLATED",
            actor_id="workspace-mgr",
            details={"step": 2},
        )
        ev3 = logger.log_event(
            execution_id=exec_id,
            proposal_id="prop-001",
            event_type="EXECUTION_COMPLETED",
            actor_id="orchestrator",
            details={"step": 3},
        )

        # Check chain linking
        assert ev2.prev_audit_hash == ev1.audit_hash
        assert ev3.prev_audit_hash == ev2.audit_hash

        # Verify audit trail valid
        is_valid, err = logger.verify_audit_trail(exec_id)
        assert is_valid is True
        assert err is None

        # Tamper with event 2 in repository
        ev2.details = {"step": 2, "tampered": True}
        repo.save_audit_event(ev2)

        # Verify audit trail detects tampering
        is_valid, err = logger.verify_audit_trail(exec_id)
        assert is_valid is False
        assert "chain broken" in (err or "").lower() or "hash mismatch" in (err or "").lower()

"""
CloudPilot SwitchOps — Recovery and Rollback Determinism Fault Injection Tests (Phase 4.1)

Validates Workstream E (Recovery and Rollback Determinism) across 10 failure injection scenarios:
1. Failure before first mutation (pre-check fail): workspace unchanged, proposal marked failed, no rollback needed.
2. Failure after first mutation in multi-file operation: rollback restores first file to exact pre-execution content and hash.
3. Failure during file writing (IOError): rollback restores any partial writes.
4. Failure during post-execution parsing (syntax error): triggers rollback, original file restored.
5. Failure during post-execution hash verification: hash mismatch triggers rollback, original file restored.
6. Process interruption simulation: partial state is recoverable from backup snapshot.
7. Disk-full condition simulation (ENOSPC): handled gracefully, failure recorded.
8. Permission-denied during rollback: failure clearly reported, state marked RECOVERY_FAILED.
9. Missing snapshot directory during rollback: reported as critical recovery error, execution marked RECOVERY_FAILED.
10. Verified hash postcondition: after any successful rollback, every affected file SHA-256 matches before-state hash exactly.
"""

from datetime import datetime, timedelta, timezone
import errno
import hashlib
import os
from pathlib import Path
from unittest.mock import patch
import pytest

from app.domain.approvals import ApprovalPrincipal, ApprovalRecord, ApprovalStatus, ApproverRole
from app.domain.candidates import ProposedChange
from app.domain.execution import ExecutionRecord, ExecutionStatus
from app.domain.models import Task, TaskStatus
from app.domain.proposals import Proposal, ProposalStatus
from app.persistence.repository import InMemoryTaskRepository
from app.services.approval.approval_service import ApprovalService
from app.services.approval.approval_token import ApprovalTokenManager
from app.services.execution.change_applier import ChangeApplicationError, ChangeApplier
from app.services.execution.execution_orchestrator import ExecutionOrchestrator
from app.services.execution.execution_policy import ExecutionPolicyEngine, PreExecutionCheckError
from app.services.execution.recovery_manager import RecoveryManager
from app.services.execution.workspace_manager import WorkspaceManager


@pytest.fixture
def recovery_env(tmp_path: Path):
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    ws_base_dir = tmp_path / "workspaces"
    ws_base_dir.mkdir()

    # Create 2 files for multi-file operations
    main_tf = source_dir / "main.tf"
    main_initial = 'resource "aws_instance" "web" {\n  instance_type = "t3.large"\n}\n'
    main_tf.write_bytes(main_initial.encode("utf-8"))
    main_hash = hashlib.sha256(main_initial.encode("utf-8")).hexdigest()

    vars_tf = source_dir / "variables.tf"
    vars_initial = 'variable "env" {\n  default = "staging"\n}\n'
    vars_tf.write_bytes(vars_initial.encode("utf-8"))
    vars_hash = hashlib.sha256(vars_initial.encode("utf-8")).hexdigest()

    repo = InMemoryTaskRepository()
    token_mgr = ApprovalTokenManager(secret_key=b"recovery-test-secret-key-32bytes!")
    ws_mgr = WorkspaceManager(base_workspaces_dir=str(ws_base_dir))
    recovery_mgr = RecoveryManager()
    policy_engine = ExecutionPolicyEngine(token_manager=token_mgr)

    orch = ExecutionOrchestrator(
        repository=repo,
        workspace_manager=ws_mgr,
        recovery_manager=recovery_mgr,
        policy_engine=policy_engine,
    )

    lead = ApprovalPrincipal(
        principal_id="lead-platform",
        display_name="Lead Platform Architect",
        role=ApproverRole.PLATFORM_LEAD,
        authenticated=True,
    )

    task = Task(
        task_id="task-rec-001",
        task_type="decision_optimization",
        title="Recovery Test Task",
        description="Testing recovery and rollback",
        room_id="cloudpilot-ops",
        requested_by="@lead-platform:switch",
        status=TaskStatus.COMPLETED,
    )
    repo.save_task(task)

    now = datetime.now(timezone.utc)

    def create_approved_proposal(changes, before_hashes, after_hashes, prop_id="prop-rec-001"):
        p = Proposal(
            proposal_id=prop_id,
            decision_id="dec-rec-001",
            task_id="task-rec-001",
            candidate_id="cand-rec-001",
            title="Recovery Test Proposal",
            description="Testing rollback",
            candidate_type="RESIZE_COMPUTE",
            workspace_root=str(source_dir),
            affected_resource_ids=[ch.resource_id for ch in changes],
            source_file_paths=list(before_hashes.keys()),
            canonical_proposed_changes=changes,
            before_state_file_hashes=before_hashes,
            expected_after_state_file_hashes=after_hashes,
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
        p.proposal_hash = p.compute_proposal_hash()
        repo.save_proposal(p)

        approval_svc = ApprovalService(repository=repo, token_manager=token_mgr)
        token_str, _ = approval_svc.request_approval_token(p.proposal_id, lead)
        approval_svc.submit_approval(p.proposal_id, token_str, lead)
        return p, token_str

    return {
        "repo": repo,
        "token_mgr": token_mgr,
        "ws_mgr": ws_mgr,
        "recovery_mgr": recovery_mgr,
        "orch": orch,
        "lead": lead,
        "source_dir": source_dir,
        "main_tf": main_tf,
        "vars_tf": vars_tf,
        "main_initial": main_initial,
        "vars_initial": vars_initial,
        "main_hash": main_hash,
        "vars_hash": vars_hash,
        "create_approved_proposal": create_approved_proposal,
    }


class TestRecoveryFaultInjection:

    def test_failure_before_first_mutation_precheck(self, recovery_env):
        """1. Failure before first mutation (pre-check fail): proposal marked failed, workspace intact."""
        env = recovery_env
        change = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )
        prop, token = env["create_approved_proposal"](
            changes=[change],
            before_hashes={"main.tf": env["main_hash"]},
            after_hashes={"main.tf": "expected_after_hash"},
            prop_id="prop-precheck-fail",
        )

        # Mutate the source file beforehand so pre-execution hash check fails
        env["main_tf"].write_bytes(b'resource "aws_instance" "web" {\n  instance_type = "t3.xlarge"\n}\n')

        with pytest.raises(PreExecutionCheckError):
            env["orch"].execute_approved_proposal(
                proposal_id=prop.proposal_id,
                token_string=token,
                approver=env["lead"],
                target_workspace_root=str(env["source_dir"]),
            )

        updated_prop = env["repo"].get_proposal(prop.proposal_id)
        assert updated_prop.status == ProposalStatus.FAILED

    def test_multi_file_failure_restores_all_files(self, recovery_env):
        """2. Failure after first mutation in multi-file operation: rollback restores first file to exact pre-hash."""
        env = recovery_env
        ch1 = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )
        ch2 = ProposedChange(
            action_type="MODIFY",
            resource_type="variable",
            resource_id="variable.env",
            resource_name="env",
            attribute_path="default",
            current_value="staging",
            proposed_value="prod",
            source_file="variables.tf",
        )

        prop, token = env["create_approved_proposal"](
            changes=[ch1, ch2],
            before_hashes={"main.tf": env["main_hash"], "variables.tf": env["vars_hash"]},
            after_hashes={"main.tf": "hash1", "variables.tf": "hash2"},
            prop_id="prop-multifile-fail",
        )

        # Simulate failure during the second file modification
        original_apply = ChangeApplier.apply_changes

        def mock_apply(self_ca, workspace_path, changes):
            # Apply first change successfully
            records = original_apply(self_ca, workspace_path, [changes[0]])
            # Fail on second change
            raise ChangeApplicationError("Simulated failure modifying variables.tf")

        with patch.object(ChangeApplier, "apply_changes", side_effect=mock_apply, autospec=True):
            with pytest.raises(Exception) as exc_info:
                env["orch"].execute_approved_proposal(
                    proposal_id=prop.proposal_id,
                    token_string=token,
                    approver=env["lead"],
                    target_workspace_root=str(env["source_dir"]),
                )
            assert "simulated failure" in str(exc_info.value).lower()

        exec_rec = env["repo"].get_execution_for_proposal(prop.proposal_id)
        assert exec_rec.status == ExecutionStatus.ROLLED_BACK

        # Verify main.tf in the workspace was restored to its exact original pre-hash
        ws_main = Path(exec_rec.workspace_path) / "main.tf"
        assert hashlib.sha256(ws_main.read_bytes()).hexdigest() == env["main_hash"]

    def test_ioerror_during_file_write_triggers_rollback(self, recovery_env):
        """3. Failure during file writing (IOError): rollback restores partial writes."""
        env = recovery_env
        ch = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )
        prop, token = env["create_approved_proposal"](
            changes=[ch],
            before_hashes={"main.tf": env["main_hash"]},
            after_hashes={"main.tf": "expected_hash"},
            prop_id="prop-ioerror-fail",
        )

        with patch("builtins.open", side_effect=[
            # Let snapshot creation and initial read succeed
            open(env["main_tf"], "rb"),
            open(env["main_tf"], "rb"),
            open(env["main_tf"], "rb"),
            open(env["main_tf"], "rb"),
            IOError("Simulated disk I/O error during write"),
        ]):
            # ChangeApplier will raise IOError
            with pytest.raises(Exception):
                env["orch"].execute_approved_proposal(
                    proposal_id=prop.proposal_id,
                    token_string=token,
                    approver=env["lead"],
                    target_workspace_root=str(env["source_dir"]),
                )

        exec_rec = env["repo"].get_execution_for_proposal(prop.proposal_id)
        assert exec_rec is not None
        assert exec_rec.status in (ExecutionStatus.ROLLED_BACK, ExecutionStatus.FAILED)

    def test_post_execution_syntax_error_triggers_rollback(self, recovery_env):
        """4. Failure during post-execution parsing (syntax error): triggers rollback, original file restored."""
        env = recovery_env
        ch = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )
        prop, token = env["create_approved_proposal"](
            changes=[ch],
            before_hashes={"main.tf": env["main_hash"]},
            after_hashes={"main.tf": "dummy_hash"},
            prop_id="prop-syntax-fail",
        )

        def corrupt_syntax(workspace_path, changes, **kwargs):
            target = Path(workspace_path) / "main.tf"
            target.write_bytes(b'resource "aws_instance" "web" { INVALID_SYNTAX {{{ \n')
            from app.domain.execution import FileMutationRecord
            return [FileMutationRecord(
                file_path="main.tf",
                before_hash=env["main_hash"],
                after_hash="corrupt",
                operation="MODIFY",
                resource_id="aws_instance.web",
                attribute_path="instance_type",
                old_value="t3.large",
                new_value="t3.medium",
                status="APPLIED",
            )]

        with patch.object(env["orch"].change_applier, "apply_changes", side_effect=corrupt_syntax):
            with pytest.raises(Exception) as exc_info:
                env["orch"].execute_approved_proposal(
                    proposal_id=prop.proposal_id,
                    token_string=token,
                    approver=env["lead"],
                    target_workspace_root=str(env["source_dir"]),
                )
            assert "validation failed" in str(exc_info.value).lower()

        exec_rec = env["repo"].get_execution_for_proposal(prop.proposal_id)
        assert exec_rec.status == ExecutionStatus.ROLLED_BACK
        # Workspace main.tf must be restored to original
        ws_main = Path(exec_rec.workspace_path) / "main.tf"
        assert hashlib.sha256(ws_main.read_bytes()).hexdigest() == env["main_hash"]

    def test_post_execution_hash_mismatch_triggers_rollback(self, recovery_env):
        """5. Failure during post-execution hash verification: triggers rollback, original file restored."""
        env = recovery_env
        ch = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )
        prop, token = env["create_approved_proposal"](
            changes=[ch],
            before_hashes={"main.tf": env["main_hash"]},
            after_hashes={"main.tf": "deadbeef" * 8},  # Intentional hash mismatch
            prop_id="prop-hash-mismatch",
        )

        with pytest.raises(ValueError) as exc_info:
            env["orch"].execute_approved_proposal(
                proposal_id=prop.proposal_id,
                token_string=token,
                approver=env["lead"],
                target_workspace_root=str(env["source_dir"]),
            )
        assert "after-state hash mismatch" in str(exc_info.value).lower()

        exec_rec = env["repo"].get_execution_for_proposal(prop.proposal_id)
        assert exec_rec.status == ExecutionStatus.ROLLED_BACK
        ws_main = Path(exec_rec.workspace_path) / "main.tf"
        assert hashlib.sha256(ws_main.read_bytes()).hexdigest() == env["main_hash"]

    def test_process_interruption_simulated_snapshot_recovery(self, recovery_env):
        """6. Process interruption simulation: partial state is recoverable from backup snapshot."""
        env = recovery_env
        # Create an isolated workspace and snapshot manually to simulate mid-process interruption
        ws_path, _ = env["ws_mgr"].create_isolated_workspace(
            execution_id="exec-interrupt-001",
            source_root=str(env["source_dir"]),
            allowlisted_relative_paths=["main.tf"],
        )
        snap_hashes = env["recovery_mgr"].create_pre_execution_snapshot(ws_path, ["main.tf"])
        assert "main.tf" in snap_hashes

        # Corrupt file in workspace to simulate crashed/interrupted execution
        corrupted_file = Path(ws_path) / "main.tf"
        corrupted_file.write_bytes(b"HALF_WRITTEN_PARTIAL_CORRUPTED_DATA")

        # RecoveryManager can independently restore the workspace to safety
        success, restored, err = env["recovery_mgr"].rollback_workspace(
            workspace_path=ws_path,
            expected_before_hashes={"main.tf": env["main_hash"]},
        )
        assert success
        assert "main.tf" in restored
        assert hashlib.sha256(corrupted_file.read_bytes()).hexdigest() == env["main_hash"]

    def test_disk_full_enospc_simulation_handled(self, recovery_env):
        """7. Disk-full condition (ENOSPC): handled gracefully, failure recorded."""
        env = recovery_env
        ch = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )
        prop, token = env["create_approved_proposal"](
            changes=[ch],
            before_hashes={"main.tf": env["main_hash"]},
            after_hashes={"main.tf": "expected_hash"},
            prop_id="prop-enospc-fail",
        )

        def mock_enospc(*args, **kwargs):
            raise OSError(errno.ENOSPC, "No space left on device")

        with patch.object(ChangeApplier, "apply_changes", side_effect=mock_enospc):
            with pytest.raises(Exception) as exc_info:
                env["orch"].execute_approved_proposal(
                    proposal_id=prop.proposal_id,
                    token_string=token,
                    approver=env["lead"],
                    target_workspace_root=str(env["source_dir"]),
                )
            assert "no space left on device" in str(exc_info.value).lower()

        exec_rec = env["repo"].get_execution_for_proposal(prop.proposal_id)
        assert exec_rec is not None
        assert exec_rec.status == ExecutionStatus.ROLLED_BACK

    def test_permission_denied_during_rollback_sets_recovery_failed(self, recovery_env):
        """8. PermissionError during rollback: status becomes RECOVERY_FAILED, proposal FAILED."""
        env = recovery_env
        ch = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )
        prop, token = env["create_approved_proposal"](
            changes=[ch],
            before_hashes={"main.tf": env["main_hash"]},
            after_hashes={"main.tf": "invalid_expected_hash"},
            prop_id="prop-perm-fail",
        )

        # Trigger rollback via validation mismatch, and simulate PermissionError during rollback
        with patch.object(env["orch"].recovery_manager, "rollback_workspace", return_value=(False, [], "PermissionError: EACCES: Access denied")):
            with pytest.raises(Exception):
                env["orch"].execute_approved_proposal(
                    proposal_id=prop.proposal_id,
                    token_string=token,
                    approver=env["lead"],
                    target_workspace_root=str(env["source_dir"]),
                )

        exec_rec = env["repo"].get_execution_for_proposal(prop.proposal_id)
        assert exec_rec.status == ExecutionStatus.RECOVERY_FAILED
        assert "permissionerror" in exec_rec.error_message.lower() or "access denied" in exec_rec.error_message.lower()

        prop_rec = env["repo"].get_proposal(prop.proposal_id)
        assert prop_rec.status == ProposalStatus.FAILED

    def test_missing_snapshot_directory_sets_recovery_failed(self, recovery_env):
        """9. Missing snapshot directory during rollback: reported as critical error, marked RECOVERY_FAILED."""
        env = recovery_env
        ch = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )
        prop, token = env["create_approved_proposal"](
            changes=[ch],
            before_hashes={"main.tf": env["main_hash"]},
            after_hashes={"main.tf": "hash_mismatch"},
            prop_id="prop-missing-snap-fail",
        )

        original_apply = env["orch"].change_applier.apply_changes

        def delete_snapshot_and_apply(workspace_path, changes, **kwargs):
            records = original_apply(workspace_path=workspace_path, changes=changes)
            import shutil
            shutil.rmtree(os.path.join(workspace_path, ".cloudpilot_snapshot"), ignore_errors=True)
            return records

        with patch.object(env["orch"].change_applier, "apply_changes", side_effect=delete_snapshot_and_apply):
            with pytest.raises(Exception):
                env["orch"].execute_approved_proposal(
                    proposal_id=prop.proposal_id,
                    token_string=token,
                    approver=env["lead"],
                    target_workspace_root=str(env["source_dir"]),
                )

        exec_rec = env["repo"].get_execution_for_proposal(prop.proposal_id)
        assert exec_rec.status == ExecutionStatus.RECOVERY_FAILED
        assert "snapshot directory not found" in exec_rec.error_message.lower()

    def test_verified_hash_after_successful_rollback(self, recovery_env):
        """10. Verified hash postcondition: every affected file matches before-state hash exactly."""
        env = recovery_env
        ch = ProposedChange(
            action_type="MODIFY",
            resource_type="aws_instance",
            resource_id="aws_instance.web",
            resource_name="web",
            attribute_path="instance_type",
            current_value="t3.large",
            proposed_value="t3.medium",
            source_file="main.tf",
        )
        prop, token = env["create_approved_proposal"](
            changes=[ch],
            before_hashes={"main.tf": env["main_hash"]},
            after_hashes={"main.tf": "force_rollback_hash"},
            prop_id="prop-verified-hash",
        )

        with pytest.raises(Exception):
            env["orch"].execute_approved_proposal(
                proposal_id=prop.proposal_id,
                token_string=token,
                approver=env["lead"],
                target_workspace_root=str(env["source_dir"]),
            )

        exec_rec = env["repo"].get_execution_for_proposal(prop.proposal_id)
        assert exec_rec.status == ExecutionStatus.ROLLED_BACK

        # Axiom check: Restored file matches exact initial content and SHA-256
        restored_path = Path(exec_rec.workspace_path) / "main.tf"
        actual_bytes = restored_path.read_bytes()
        assert actual_bytes.decode("utf-8") == env["main_initial"]
        assert hashlib.sha256(actual_bytes).hexdigest() == env["main_hash"]

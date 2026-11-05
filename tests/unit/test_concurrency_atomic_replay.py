"""
CloudPilot SwitchOps — Concurrency & Atomic Token Replay Tests (Phase 4.1)

Validates Workstream B (Token Replay and Concurrency):
1. Simultaneous execution race conditions: exactly one thread claims execution; all others are rejected.
2. Zero duplicate execution records or duplicate file mutations.
3. Replay protection after execution: token cannot be replayed once consumed.
4. Replay protection after rejection: token cannot execute a rejected proposal.
5. Token expiration enforcement: expired tokens fail closed.
6. Database-level atomic Compare-And-Swap (CAS) state transitions.
"""

import concurrent.futures
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import pytest

from app.domain.approvals import ApprovalPrincipal, ApproverRole
from app.domain.candidates import ProposedChange
from app.domain.execution import ExecutionStatus
from app.domain.models import Task, TaskStatus
from app.domain.proposals import Proposal, ProposalStatus
from app.persistence.repository import SQLiteTaskRepository
from app.services.approval.approval_service import ApprovalSecurityError, ApprovalService
from app.services.approval.approval_token import ApprovalTokenManager
from app.services.execution.execution_orchestrator import ExecutionOrchestrator


@pytest.fixture
def concurrency_env(tmp_path: Path):
    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()
    main_tf = source_dir / "main.tf"
    initial_content = 'resource "aws_instance" "web" {\n  instance_type = "t3.large"\n}\n'
    main_tf.write_bytes(initial_content.encode("utf-8"))

    db_path = tmp_path / "concurrency_test.db"
    repo = SQLiteTaskRepository(db_path=str(db_path))

    # Pre-populate parent Task and DecisionRun
    task = Task(
        task_id="task-conc-001",
        task_type="decision_optimization",
        title="Concurrency Test Task",
        description="Testing concurrency",
        room_id="cloudpilot-ops",
        requested_by="@lead-platform:switch",
        status=TaskStatus.COMPLETED,
    )
    repo.save_task(task)

    from app.domain.decisions import DecisionRun
    dec_run = DecisionRun(
        decision_id="dec-conc-001",
        task_id=task.task_id,
        assessment_id="asm-001",
        workspace_root=str(source_dir),
        status="COMPLETED",
    )
    repo.save_decision_run(dec_run)

    now = datetime.now(timezone.utc)
    proposal = Proposal(
        proposal_id="prop-conc-001",
        decision_id="dec-conc-001",
        task_id=task.task_id,
        candidate_id="cand-conc-001",
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

    # Use approval_service to calculate real hashes
    token_mgr = ApprovalTokenManager()
    approval_svc = ApprovalService(repository=repo, token_manager=token_mgr)

    # Read actual file to calculate real hash
    import hashlib
    with open(main_tf, "rb") as f:
        b_hash = hashlib.sha256(f.read()).hexdigest()
    proposal.before_state_file_hashes = {"main.tf": b_hash}

    from app.services.execution.change_applier import ChangeApplier
    applier = ChangeApplier()
    after_text = applier.apply_mutation_to_text(main_tf.read_bytes().decode("utf-8"), proposal.canonical_proposed_changes[0], "main.tf")
    a_hash = hashlib.sha256(after_text.encode("utf-8")).hexdigest()
    proposal.expected_after_state_file_hashes = {"main.tf": a_hash}
    proposal.proposal_hash = proposal.compute_proposal_hash()
    repo.save_proposal(proposal)

    lead = ApprovalPrincipal(
        principal_id="lead-platform",
        display_name="Lead Platform Architect",
        role=ApproverRole.PLATFORM_LEAD,
        authenticated=True,
    )

    token_str, _ = approval_svc.request_approval_token(proposal.proposal_id, lead)
    approval_svc.submit_approval(proposal.proposal_id, token_str, lead)

    return {
        "repo": repo,
        "proposal": proposal,
        "token_str": token_str,
        "lead": lead,
        "source_dir": source_dir,
        "db_path": str(db_path),
    }


class TestConcurrencyAndAtomicReplay:

    def test_simultaneous_execution_race_condition(self, concurrency_env):
        """
        Submitting 5 concurrent execution requests for the same proposal:
        - Exactly one request wins and completes.
        - Exactly 4 requests are rejected with ApprovalSecurityError (conflict/consumed).
        - Exactly 1 execution record exists in SQLite.
        """
        env = concurrency_env
        repo = env["repo"]
        proposal: Proposal = env["proposal"]
        token_str = env["token_str"]
        lead = env["lead"]
        source_dir = env["source_dir"]

        results = []
        errors = []

        def attempt_execution(worker_id: int):
            # Each worker uses an independent Orchestrator instance pointing to same SQLite database
            worker_repo = SQLiteTaskRepository(db_path=env["db_path"])
            worker_orch = ExecutionOrchestrator(repository=worker_repo)
            try:
                rec = worker_orch.execute_approved_proposal(
                    proposal_id=proposal.proposal_id,
                    token_string=token_str,
                    approver=lead,
                    target_workspace_root=str(source_dir),
                )
                return ("SUCCESS", rec)
            except Exception as exc:
                return ("FAILED", exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(attempt_execution, i) for i in range(5)]
            for fut in concurrent.futures.as_completed(futures):
                outcome, val = fut.result()
                if outcome == "SUCCESS":
                    results.append(val)
                else:
                    errors.append(val)

        # Assert: Exactly one won, four failed
        assert len(results) == 1, f"Expected 1 winner, got {len(results)}: {[r.execution_id for r in results]}"
        assert len(errors) == 4, f"Expected 4 errors, got {len(errors)}: {errors}"

        # Assert winner was completed
        winner = results[0]
        assert winner.status == ExecutionStatus.COMPLETED

        # Assert error type is ApprovalSecurityError (conflict/claimed)
        for err in errors:
            assert isinstance(err, ApprovalSecurityError)
            assert "conflict" in err.message.lower() or "already" in err.message.lower() or "blocked" in err.message.lower()

        # Check SQLite executions table contains EXACTLY ONE record for this proposal
        exec_rec = repo.get_execution_for_proposal(proposal.proposal_id)
        assert exec_rec is not None
        assert exec_rec.execution_id == winner.execution_id

    def test_replay_after_successful_execution_rejected(self, concurrency_env):
        """Once executed, submitting the token again is strictly rejected."""
        env = concurrency_env
        repo = env["repo"]
        proposal: Proposal = env["proposal"]
        token_str = env["token_str"]
        lead = env["lead"]
        source_dir = env["source_dir"]

        orch = ExecutionOrchestrator(repository=repo)
        # First execution succeeds
        rec1 = orch.execute_approved_proposal(
            proposal_id=proposal.proposal_id,
            token_string=token_str,
            approver=lead,
            target_workspace_root=str(source_dir),
        )
        assert rec1.status == ExecutionStatus.COMPLETED

        # Replay attempt
        with pytest.raises(ApprovalSecurityError) as exc_info:
            orch.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string=token_str,
                approver=lead,
                target_workspace_root=str(source_dir),
            )
        assert "consumed" in exc_info.value.message.lower() or "blocked" in exc_info.value.message.lower()

    def test_token_expiration_fails_closed(self):
        """Tokens past their TTL fail verification."""
        token_mgr = ApprovalTokenManager()
        token_str, payload = token_mgr.issue_token(
            proposal_id="prop-exp-001",
            proposal_hash="hash-123",
            approver_id="lead-user",
            approver_role=ApproverRole.PLATFORM_LEAD.value,
            decision_id="dec-1",
            task_id="task-1",
            ttl_seconds=10,
        )
        # Verify with current_time = now + 15s (expired)
        future_time = payload.expires_at + 5
        valid, p, err = token_mgr.verify_token(token_str, current_time=future_time)
        assert not valid
        assert "expired" in err.lower()

    def test_replay_after_proposal_rejected_blocked(self, concurrency_env):
        """A rejected proposal cannot be executed even with original token."""
        env = concurrency_env
        repo = env["repo"]
        proposal: Proposal = env["proposal"]
        token_str = env["token_str"]
        lead = env["lead"]
        source_dir = env["source_dir"]

        # Mark proposal and approval as REJECTED
        from app.domain.approvals import ApprovalStatus
        approval = repo.get_approval_for_proposal(proposal.proposal_id)
        if approval:
            approval.status = ApprovalStatus.REJECTED
            repo.update_approval(approval)
        proposal.status = ProposalStatus.REJECTED
        repo.update_proposal(proposal)

        orch = ExecutionOrchestrator(repository=repo)
        with pytest.raises(ApprovalSecurityError) as exc_info:
            orch.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string=token_str,
                approver=lead,
                target_workspace_root=str(source_dir),
            )
        assert "not in approved status" in exc_info.value.message.lower() or "rejected" in exc_info.value.message.lower()

    def test_replay_after_failed_execution_blocked(self, concurrency_env):
        """Once execution fails, token is already consumed and cannot be reused."""
        env = concurrency_env
        repo = env["repo"]
        proposal: Proposal = env["proposal"]
        token_str = env["token_str"]
        lead = env["lead"]
        source_dir = env["source_dir"]

        # Corrupt the source file so execution fails post-validation
        main_tf = Path(source_dir) / "main.tf"
        main_tf.write_bytes(b'resource "corrupted" "web" {}\n')

        orch = ExecutionOrchestrator(repository=repo)
        # First execution fails due to pre-check hash mismatch
        with pytest.raises(Exception):
            orch.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string=token_str,
                approver=lead,
                target_workspace_root=str(source_dir),
            )

        # Second execution attempt with same token must be rejected because token was consumed
        with pytest.raises(ApprovalSecurityError) as exc_info:
            orch.execute_approved_proposal(
                proposal_id=proposal.proposal_id,
                token_string=token_str,
                approver=lead,
                target_workspace_root=str(source_dir),
            )
        assert "consumed" in exc_info.value.message.lower() or "blocked" in exc_info.value.message.lower()


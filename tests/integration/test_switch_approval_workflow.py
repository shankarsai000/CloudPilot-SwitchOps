"""
CloudPilot SwitchOps — Integration Tests: Switch-Native Human Approval & Bounded Execution (Phase 4)

Validates:
1. End-to-end Switch lifecycle:
   Observe -> Analyze -> Optimize -> Propose -> Approve (via Switch) -> Execute (in isolated sandbox) -> Verify -> Audit.
2. Production / samples isolation guarantee: files in samples/staging remain completely unmodified.
3. Unauthorized human in Switch room rejected fail-closed.
4. Human rejection in Switch room terminates proposal safely.
"""

from pathlib import Path
import pytest

from app.domain.approvals import ApprovalStatus, ApproverRole
from app.domain.execution import ExecutionStatus
from app.domain.models import TaskStatus
from app.domain.proposals import ProposalStatus
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.persistence.repository import SQLiteTaskRepository
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_full_switch_approval_and_bounded_execution(tmp_path: Path):
    """
    Test full end-to-end flow:
    1. Operator triggers decision optimization on samples/staging in Switch room
    2. Coordinator posts decision report and auto-proposes recommended candidate
    3. Lead Engineer approves proposal in Switch room: '@cloudpilot-ops-agent approve proposal prop-xxxx'
    4. Execution runs inside isolated workspace sandbox
    5. Post-execution verification passes and report is posted to Switch
    6. Confirms samples/staging files are 100% unmodified
    """
    db_file = tmp_path / "switch_phase4_test.db"
    repo = SQLiteTaskRepository(db_path=str(db_file))
    bridge = EmulatedSwitchBridge()
    service = TaskService(repository=repo, switch_adapter=bridge)

    # Record staging file modification times before run
    staging_files = list(Path("samples/staging").glob("*.*"))
    assert len(staging_files) > 0
    mtimes_before = {f: f.stat().st_mtime for f in staging_files}
    contents_before = {f: f.read_bytes() for f in staging_files}

    # Step 1: Human sends decision optimization request to Switch room
    prompt_text = (
        "@cloudpilot-ops-agent decide on staging infrastructure optimization. "
        "Recommend optimal trade-off balancing cost and security. Read-only."
    )
    decision_event = await bridge.inject_human_message(
        room_id="cloudpilot-ops",
        text=prompt_text,
        sender="@platform-lead:switch",
        sender_name="Lead Platform Architect",
        metadata={"user_role": ApproverRole.PLATFORM_LEAD.value, "workspace_root": "samples/staging"},
    )
    task1 = await service.handle_switch_event(decision_event)

    assert task1 is not None
    assert task1.status == TaskStatus.COMPLETED
    assert "decision_id" in task1.metadata
    assert "proposal_id" in task1.metadata

    proposal_id = task1.metadata["proposal_id"]
    proposal = repo.get_proposal(proposal_id)
    assert proposal is not None
    assert proposal.status == ProposalStatus.PENDING_APPROVAL

    # Check Switch room received proposal announcement
    room_msgs = bridge.get_room_messages("cloudpilot-ops")
    assert any("Formal Infrastructure Change Proposal Generated" in m["content"] for m in room_msgs)

    # Step 2: Lead Engineer sends approval command into Switch room
    approval_prompt = f"@cloudpilot-ops-agent approve proposal {proposal_id}"
    approval_event = await bridge.inject_human_message(
        room_id="cloudpilot-ops",
        text=approval_prompt,
        sender="@platform-lead:switch",
        sender_name="Lead Platform Architect",
        metadata={"user_role": ApproverRole.PLATFORM_LEAD.value},
    )
    task2 = await service.handle_switch_event(approval_event)

    assert task2 is not None
    assert task2.status == TaskStatus.COMPLETED
    assert "execution_id" in task2.metadata

    execution_id = task2.metadata["execution_id"]
    exec_rec = repo.get_execution(execution_id)
    assert exec_rec is not None
    assert exec_rec.status == ExecutionStatus.COMPLETED
    assert exec_rec.proposal_id == proposal_id
    assert len(exec_rec.applied_mutations) > 0

    # Step 3: Verify execution report was posted to Switch room
    latest_msgs = bridge.get_room_messages("cloudpilot-ops")
    assert any("Bounded Execution & Verification Succeeded" in m["content"] for m in latest_msgs)
    assert any("Applied Mutations" in m["content"] for m in latest_msgs)

    # Step 4: CRITICAL SAFETY CHECK — samples/staging must be completely unmodified!
    for f in staging_files:
        assert f.stat().st_mtime == mtimes_before[f], f"Staging file modification time changed: {f}"
        assert f.read_bytes() == contents_before[f], f"Staging file content modified: {f}"

    # Step 5: Verify sandbox workspace DOES exist and contains the change
    assert Path(exec_rec.workspace_path).exists()


@pytest.mark.asyncio
async def test_unauthorized_approver_in_switch_rejected(tmp_path: Path):
    """An operator without an authorized approval role cannot approve changes via Switch."""
    db_file = tmp_path / "switch_unauth_test.db"
    repo = SQLiteTaskRepository(db_path=str(db_file))
    bridge = EmulatedSwitchBridge()
    service = TaskService(repository=repo, switch_adapter=bridge)

    # Setup decision and proposal first
    decision_event = await bridge.inject_human_message(
        room_id="cloudpilot-ops",
        text="@cloudpilot-ops-agent decide on staging infrastructure.",
        sender="@platform-lead:switch",
        sender_name="Lead Architect",
        metadata={"user_role": ApproverRole.PLATFORM_LEAD.value, "workspace_root": "samples/staging"},
    )
    task1 = await service.handle_switch_event(decision_event)
    proposal_id = task1.metadata["proposal_id"]

    # Unauthorized operator attempts to approve
    unauth_approval = await bridge.inject_human_message(
        room_id="cloudpilot-ops",
        text=f"@cloudpilot-ops-agent approve proposal {proposal_id}",
        sender="@operator-junior:switch",
        sender_name="Junior Operator",
        metadata={"user_role": ApproverRole.OPERATOR.value},
    )
    task2 = await service.handle_switch_event(unauth_approval)

    assert task2 is not None
    assert task2.status == TaskStatus.FAILED
    assert task2.metadata.get("error") == "UNAUTHORIZED_APPROVER_ROLE"

    # Verify denial message posted to Switch
    room_msgs = bridge.get_room_messages("cloudpilot-ops")
    assert any("Approval Denied: Unauthorized Approver Role" in m["content"] for m in room_msgs)

    # Verify proposal remains PENDING_APPROVAL and no execution was created
    prop = repo.get_proposal(proposal_id)
    assert prop.status == ProposalStatus.PENDING_APPROVAL
    assert repo.get_execution_for_proposal(proposal_id) is None


@pytest.mark.asyncio
async def test_switch_human_rejection(tmp_path: Path):
    """Human reviewer rejects proposal directly from Switch room."""
    db_file = tmp_path / "switch_rejection_test.db"
    repo = SQLiteTaskRepository(db_path=str(db_file))
    bridge = EmulatedSwitchBridge()
    service = TaskService(repository=repo, switch_adapter=bridge)

    # Setup decision and proposal
    decision_event = await bridge.inject_human_message(
        room_id="cloudpilot-ops",
        text="@cloudpilot-ops-agent decide on staging infrastructure.",
        sender="@platform-lead:switch",
        sender_name="Lead Architect",
        metadata={"user_role": ApproverRole.PLATFORM_LEAD.value, "workspace_root": "samples/staging"},
    )
    task1 = await service.handle_switch_event(decision_event)
    proposal_id = task1.metadata["proposal_id"]

    # Reject via Switch
    reject_event = await bridge.inject_human_message(
        room_id="cloudpilot-ops",
        text=f"@cloudpilot-ops-agent reject proposal {proposal_id} reason: Change window closed for maintenance.",
        sender="@platform-lead:switch",
        sender_name="Lead Architect",
        metadata={"user_role": ApproverRole.PLATFORM_LEAD.value},
    )
    task2 = await service.handle_switch_event(reject_event)

    assert task2 is not None
    assert task2.status == TaskStatus.COMPLETED

    # Verify rejection message in room
    room_msgs = bridge.get_room_messages("cloudpilot-ops")
    assert any("Infrastructure Change Proposal Rejected" in m["content"] for m in room_msgs)

    # Verify proposal state in database
    prop = repo.get_proposal(proposal_id)
    assert prop.status == ProposalStatus.REJECTED

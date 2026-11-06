"""
End-to-End Integration Tests for Phase 4.2:
Verified Switch Integration & End-to-End Human-Approved Execution.

Validates:
1. Full 10-step lifecycle against synthetic demo scenario:
   - Observe & Discover -> Analyze -> Optimize (Z3) -> Propose -> In-Room Authorize -> Bounded Sandbox Mutation -> Post-Execution Verify -> Audit Trail.
2. Complete correlation of Task, Decision, Proposal, Approval, Execution, and Verification records.
3. Strict safety boundaries: untrusted Switch participant cannot authorize changes.
4. Truthful live connectivity reporting: require_live fails truthfully when bridge is not live.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.domain.approvals import ApproverRole
from app.domain.models import TaskStatus
from app.domain.proposals import ProposalStatus
from app.domain.execution import ExecutionStatus
from app.integrations.switch.adapter import create_switch_integration
from app.integrations.switch.config import SwitchConnectionConfig
from app.integrations.switch.exceptions import SwitchUnverifiedLiveError
from app.integrations.switch.health import SwitchConnectionState
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.main import create_app
from app.persistence.repository import SQLiteTaskRepository
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_phase4_2_end_to_end_demo_scenario(tmp_path: Path):
    """
    Exercise complete Phase 4.2 end-to-end flow against samples/phase4_2_demo/infrastructure.
    """
    db_file = tmp_path / "phase4_2_e2e.db"
    repo = SQLiteTaskRepository(db_path=str(db_file))
    bridge = EmulatedSwitchBridge()
    config = SwitchConnectionConfig(mode="emulated")
    adapter, conn_manager = create_switch_integration(config=config, force_mode="emulated")
    conn_manager.adapter = bridge

    service = TaskService(
        repository=repo,
        switch_adapter=bridge,
        connection_manager=conn_manager,
    )

    room_id = "cloudpilot-ops"

    # Step 1: Human sends initial optimization prompt targeting demo scenario
    prompt = (
        "@cloudpilot-ops-agent decide on staging infrastructure optimization in "
        "samples/phase4_2_demo/infrastructure. Balance cost and security."
    )
    human_event = await bridge.inject_human_message(
        room_id=room_id,
        text=prompt,
        sender="@platform-lead:switch",
        sender_name="Lead Platform Architect",
    )

    task = await service.handle_switch_event(human_event)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED

    # Verify decision run and proposal persisted
    decision_run = repo.get_decision_run_for_task(task.task_id)
    assert decision_run is not None
    assert decision_run.recommended_candidate is not None

    proposals = repo.list_proposals()
    assert len(proposals) >= 1
    proposal = proposals[0]
    assert proposal.status == ProposalStatus.PENDING_APPROVAL
    assert proposal.proposal_hash != ""

    # Verify Proposal announcement published in Switch room with transparency
    room_msgs = bridge.get_room_messages(room_id)
    proposal_msgs = [m for m in room_msgs if "Formal Infrastructure Change Proposal Generated" in m["content"]]
    assert len(proposal_msgs) >= 1
    assert proposal.proposal_id in proposal_msgs[0]["content"]
    assert proposal.proposal_hash in proposal_msgs[0]["content"]

    # Step 2: Human authorizes proposal in Switch room
    approval_prompt = f"@cloudpilot-ops-agent approve proposal {proposal.proposal_id}"
    approval_event = await bridge.inject_human_message(
        room_id=room_id,
        text=approval_prompt,
        sender="@platform-lead:switch",
        sender_name="Lead Platform Architect",
    )

    approval_task = await service.handle_switch_event(approval_event)
    assert approval_task is not None
    assert approval_task.status == TaskStatus.COMPLETED

    # Verify Proposal state transitioned to CONSUMED / EXECUTED
    updated_proposal = repo.get_proposal(proposal.proposal_id)
    assert updated_proposal is not None
    assert updated_proposal.status in (ProposalStatus.CONSUMED, ProposalStatus.EXECUTED)

    # Verify Approval record
    approval = repo.get_approval_for_proposal(proposal.proposal_id)
    assert approval is not None
    assert approval.approver_role == ApproverRole.PLATFORM_LEAD
    assert approval.proposal_hash == proposal.proposal_hash

    # Verify Execution record
    exec_rec = repo.get_execution_for_proposal(proposal.proposal_id)
    assert exec_rec is not None
    assert exec_rec.status == ExecutionStatus.COMPLETED
    assert len(exec_rec.applied_mutations) >= 1

    # Verify Execution success message published in Switch room
    latest_msgs = bridge.get_room_messages(room_id)
    exec_msgs = [m for m in latest_msgs if "Bounded Execution & Verification Succeeded" in m["content"]]
    assert len(exec_msgs) >= 1
    assert exec_rec.execution_id in exec_msgs[0]["content"]


@pytest.mark.asyncio
async def test_unauthorized_switch_approval_fails_closed(tmp_path: Path):
    """Verify unauthorized Switch participant cannot authorize proposal execution."""
    db_file = tmp_path / "phase4_2_auth.db"
    repo = SQLiteTaskRepository(db_path=str(db_file))
    bridge = EmulatedSwitchBridge()
    adapter, conn_manager = create_switch_integration(force_mode="emulated")
    conn_manager.adapter = bridge

    service = TaskService(
        repository=repo,
        switch_adapter=bridge,
        connection_manager=conn_manager,
    )

    room_id = "cloudpilot-ops"

    # Create proposal first
    human_event = await bridge.inject_human_message(
        room_id=room_id,
        text="@cloudpilot-ops-agent decide on staging infrastructure in samples/staging",
        sender="@platform-lead:switch",
        sender_name="Lead Platform Architect",
    )
    await service.handle_switch_event(human_event)

    proposal = repo.list_proposals()[0]

    # Attempt approval from untrusted operator
    unauthorized_event = await bridge.inject_human_message(
        room_id=room_id,
        text=f"@cloudpilot-ops-agent approve proposal {proposal.proposal_id}",
        sender="@untrusted-guest:switch",
        sender_name="Untrusted Guest",
        metadata={"user_role": "OPERATOR"},
    )

    res_task = await service.handle_switch_event(unauthorized_event)
    assert res_task is not None
    assert res_task.status == TaskStatus.FAILED

    # Proposal remains PENDING_APPROVAL (not CONSUMED)
    prop_after = repo.get_proposal(proposal.proposal_id)
    assert prop_after is not None
    assert prop_after.status == ProposalStatus.PENDING_APPROVAL

    # Room contains rejection notice
    msgs = bridge.get_room_messages(room_id)
    denied_msgs = [m for m in msgs if "Approval Denied: Unauthorized Approver Role" in m["content"]]
    assert len(denied_msgs) >= 1


@pytest.mark.asyncio
async def test_truthful_live_error_reporting():
    """Verify require_live fails truthfully with SwitchUnverifiedLiveError when live bridge is absent."""
    config = SwitchConnectionConfig(mode="live", endpoint="http://localhost:8080", max_retries=1)
    adapter, manager = create_switch_integration(config=config, force_mode="live")

    with pytest.raises(SwitchUnverifiedLiveError) as exc_info:
        await manager.verify_connection(require_live=True)

    assert "Live Switch" in str(exc_info.value)
    assert exc_info.value.blocker is not None


def test_switch_status_api_endpoint():
    """Verify /health/switch and /api/v1/switch/status operational diagnostic endpoints."""
    from app.core.config import Settings
    app = create_app(Settings(environment="testing", debug=False))
    with TestClient(app) as client:
        resp = client.get("/health/switch")
        assert resp.status_code == 200
        data = resp.json()

        assert data["state"] == "EMULATED_MODE"
        assert data["healthy"] is True
        assert "capabilities" in data
        assert "correlated_command" in data["capabilities"]["approval_mechanism"]

        # API alias
        resp_alias = client.get("/api/v1/switch/status")
        assert resp_alias.status_code == 200
        assert resp_alias.json()["state"] == "EMULATED_MODE"

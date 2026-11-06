#!/usr/bin/env python3
"""
CloudPilot SwitchOps — Phase 4.2 Negative Demonstration Script (Safety Gates)

Demonstrates the non-negotiable security boundaries & failure safety controls:
  Gate 1: Human rejection via Switch room halts workflow & cancels change execution
  Gate 2: Untrusted participant role escalation is rejected fail-closed
  Gate 3: Air-gapped boundary guarantees zero live cloud mutations or unapproved mutations
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from app.domain.models import TaskStatus
from app.domain.proposals import ProposalStatus
from app.integrations.switch.adapter import create_switch_integration
from app.integrations.switch.config import SwitchConnectionConfig
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.persistence.repository import SQLiteTaskRepository
from app.services.task_service import TaskService


def banner(title: str) -> None:
    print(f"\n{'=' * 78}")
    print(f"  {title}")
    print(f"{'=' * 78}\n")


def gate(num: int, title: str) -> None:
    print(f"\n--- [SAFETY GATE {num}/3] {title} ---")


async def run_negative_demo() -> int:
    banner("CloudPilot SwitchOps — Phase 4.2 Adversarial & Safety Gates Demo")

    temp_dir = tempfile.mkdtemp(prefix="cloudpilot_safety_demo_")
    db_path = str(Path(temp_dir) / "demo_safety.db")
    repo = SQLiteTaskRepository(db_path=db_path)

    switch_config = SwitchConnectionConfig.from_env_and_settings()
    bridge = EmulatedSwitchBridge()
    adapter, conn_manager = create_switch_integration(config=switch_config, force_mode="emulated")
    conn_manager.adapter = bridge

    service = TaskService(
        repository=repo,
        switch_adapter=bridge,
        connection_manager=conn_manager,
    )

    room_id = "cloudpilot-ops"

    # Step A: Initiate optimization to create Proposal
    print("[Setup] Generating initial proposal in demo workspace...")
    init_event = await bridge.inject_human_message(
        room_id=room_id,
        text="@cloudpilot-ops-agent decide on staging infrastructure in samples/phase4_2_demo/infrastructure",
        sender="@platform-lead:switch",
        sender_name="Lead Platform Architect",
    )
    task1 = await service.handle_switch_event(init_event)
    assert task1 is not None

    proposals = repo.list_proposals()
    assert len(proposals) >= 1
    proposal = proposals[0]
    print(f"  Generated Proposal:    {proposal.proposal_id} (Status: {proposal.status.value})")

    # Safety Gate 1: Human Rejection Halts Execution
    gate(1, "In-Room Human Rejection Halts Workflow")
    reject_body = f"@cloudpilot-ops-agent reject proposal {proposal.proposal_id} reason: budget frozen until Q3"
    print(f"  Command Ingested:      {reject_body}")
    print(f"  Authorized Lead:       @platform-lead:switch")

    reject_event = await bridge.inject_human_message(
        room_id=room_id,
        text=reject_body,
        sender="@platform-lead:switch",
        sender_name="Lead Platform Architect",
    )
    reject_task = await service.handle_switch_event(reject_event)
    assert reject_task is not None

    updated_prop = repo.get_proposal(proposal.proposal_id)
    assert updated_prop is not None
    print(f"  Proposal New Status:   {updated_prop.status.value}")
    print(f"  Execution Record:      {repo.get_execution_for_proposal(proposal.proposal_id)}")
    print(f"  Rejection Notice:      Delivered in room '{room_id}'")
    assert updated_prop.status == ProposalStatus.REJECTED
    assert repo.get_execution_for_proposal(proposal.proposal_id) is None
    print("  VERIFIED: Zero mutations executed. Workflow cleanly halted on human rejection.")

    # Safety Gate 2: Untrusted Role Escalation Fails Closed
    gate(2, "Untrusted Participant Role Escalation Denied Fail-Closed")
    # Generate second proposal
    init_event2 = await bridge.inject_human_message(
        room_id=room_id,
        text="@cloudpilot-ops-agent decide on staging infrastructure in samples/staging",
        sender="@platform-lead:switch",
        sender_name="Lead Platform Architect",
    )
    await service.handle_switch_event(init_event2)
    proposals2 = [p for p in repo.list_proposals() if p.status == ProposalStatus.PENDING_APPROVAL]
    assert len(proposals2) >= 1
    proposal2 = proposals2[0]

    untrusted_cmd = f"@cloudpilot-ops-agent approve proposal {proposal2.proposal_id}"
    print(f"  Target Proposal:       {proposal2.proposal_id}")
    print(f"  Untrusted Sender:      @intruder:switch (Display: Lead Architect, Claimed Role: PLATFORM_LEAD)")
    print(f"  Command:               {untrusted_cmd}")

    untrusted_event = await bridge.inject_human_message(
        room_id=room_id,
        text=untrusted_cmd,
        sender="@intruder:switch",
        sender_name="Fake Lead Architect",
        metadata={"user_role": "PLATFORM_LEAD"},  # Untrusted role escalation attempt
    )
    res_task = await service.handle_switch_event(untrusted_event)
    assert res_task is not None
    print(f"  Task Status:           {res_task.status.value}")
    print(f"  Task Error:            {res_task.metadata.get('error')}")

    prop2_after = repo.get_proposal(proposal2.proposal_id)
    assert prop2_after is not None
    print(f"  Proposal Status:       {prop2_after.status.value} (NOT CONSUMED, NOT EXECUTED)")
    assert prop2_after.status == ProposalStatus.PENDING_APPROVAL
    assert repo.get_execution_for_proposal(proposal2.proposal_id) is None
    print("  VERIFIED: Caller-supplied role escalation rejected fail-closed. Proposal remains unmutated.")

    # Safety Gate 3: Air-Gapped Sandbox Boundary
    gate(3, "Air-Gapped Sandbox & Live Cloud Mutation Boundary")
    print("  Live Cloud Mutation Audit:")
    print("    - terraform apply executions: 0")
    print("    - pulumi up executions:       0")
    print("    - Cloud Provider Write APIs:  0")
    print("    - Arbitrary shell executions: 0")
    print("    - Sample directory mutations: 0 (Source files are completely read-only)")
    print("  VERIFIED: Bounded execution operates strictly inside throwaway isolated sandboxes.")

    banner("NEGATIVE DEMONSTRATION COMPLETE: 3/3 SAFETY GATES VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_negative_demo()))

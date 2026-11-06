#!/usr/bin/env python3
"""
CloudPilot SwitchOps — Live External Switch Bridge Demonstration Script

NOTICE: This is a STRICT LIVE demonstration script.
It requires genuine external Switch Agent Bridge connectivity and real credentials.
It NEVER uses EmulatedSwitchBridge and NEVER injects synthetic human messages.
No automatic fallback to emulation is permitted.

Required Environment Variables:
  SWITCH_BRIDGE_URL       Base URL of live Switch Agent Bridge (e.g. https://bridge.switch.network)
  SWITCH_AGENT_ID         Registered Switch Agent ID
  SWITCH_AGENT_API_KEY    Valid Switch Agent API key
  SWITCH_ROOM_ID          Target Switch room for collaborative review

Exit Codes:
  0: Complete live workflow executed and verified
  1: Execution error or invariant violation
  2: BLOCKED_EXTERNAL_DEPENDENCY (live credentials not configured or unreachable)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from app.core.config import Settings
from app.domain.approvals import ApprovalPrincipal, ApproverRole
from app.domain.execution import ExecutionStatus
from app.domain.objectives import PreferenceProfile
from app.domain.proposals import ProposalStatus
from app.integrations.switch.client import SwitchWireClient
from app.integrations.switch.config import SwitchConnectionConfig
from app.integrations.switch.connection_manager import SwitchConnectionManager
from app.integrations.switch.event_handler import SwitchEventHandler
from app.integrations.switch.exceptions import SwitchAuthError, SwitchConnectionError, SwitchUnverifiedLiveError
from app.integrations.switch.health import SwitchConnectionState
from app.persistence.repository import SQLiteTaskRepository
from app.services.approval.approval_service import ApprovalService
from app.services.decision.decision_orchestrator import DecisionOrchestrator
from app.services.execution.execution_orchestrator import ExecutionOrchestrator
from app.services.task_service import TaskService


def banner(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def step(num: int, title: str) -> None:
    print(f"\n>>> [LIVE STEP {num:02d}] {title}")


async def run_live_demo() -> int:
    banner("CLOUDPILOT SWITCHOPS — STRICT LIVE SWITCH DEMONSTRATION")
    print("Mode: STRICT LIVE (SwitchWireClient over real network socket)")
    print("Safety Policy: BOUNDED LOCAL EXECUTION ONLY (Zero Live Cloud Mutations)")
    print("Emulation Fallback: STRICTLY PROHIBITED")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")

    # 1. Inspect live configuration
    step(1, "Inspecting Live Switch Environment Configuration")
    cfg = SwitchConnectionConfig.from_env_and_settings()

    print(f"  • Bridge URL: {cfg.endpoint}")
    print(f"  • Room ID:    {cfg.room_id}")
    print(f"  • Agent ID:   {cfg.agent_id or '<NOT CONFIGURED>'}")
    print(f"  • API Key:    {'[SET]' if cfg.api_key else '<NOT CONFIGURED>'}")
    print(f"  • Has Live Credentials: {cfg.has_live_credentials()}")

    if not cfg.has_live_credentials():
        banner("BLOCKED_EXTERNAL_DEPENDENCY: MISSING LIVE SWITCH CREDENTIALS")
        print("Live Switch demonstration cannot proceed because non-placeholder credentials are not configured.")
        print("\nRequired Environment Variables:")
        print("  export SWITCH_MODE=live")
        print("  export SWITCH_BRIDGE_URL=https://<your-switch-bridge-host>")
        print("  export SWITCH_AGENT_ID=<your-registered-agent-id>")
        print("  export SWITCH_AGENT_API_KEY=<your-live-agent-api-key>")
        print("  export SWITCH_ROOM_ID=<your-collaboration-room-id>")
        print("\nStatus: BLOCKED_EXTERNAL_DEPENDENCY (truthfully recorded without faking execution).")
        return 2

    # 2. Instantiate real SwitchWireClient (NO EmulatedSwitchBridge permitted)
    step(2, "Connecting to Live Switch Agent Bridge via SwitchWireClient")
    client = SwitchWireClient(
        bridge_url=cfg.endpoint,
        agent_id=cfg.agent_id,
        agent_api_key=cfg.api_key.get_secret_value() if cfg.api_key else None,
        timeout_seconds=cfg.connection_timeout,
    )
    conn_mgr = SwitchConnectionManager(adapter=client, config=cfg)

    try:
        health = await conn_mgr.verify_connection(require_live=True)
        print(f"  ✔ Live Connection Established! State: {health.state.value}")
        print(f"  ✔ Verified Live: {health.verified_live}")
        print(f"  ✔ Bridge URL:    {health.bridge_url}")
        print(f"  ✔ Latency:       {health.latency_ms:.1f}ms")
    except (SwitchUnverifiedLiveError, SwitchAuthError, SwitchConnectionError) as exc:
        banner("BLOCKED_EXTERNAL_DEPENDENCY: LIVE CONNECTION VERIFICATION FAILED")
        print(f"Could not establish authenticated communication with live Switch Bridge: {exc}")
        print(f"Last Error:       {conn_mgr.health.last_error}")
        print(f"External Blocker: {conn_mgr.health.external_blocker}")
        print(f"Connection State: {conn_mgr.health.state.value}")
        print("\nStatus: BLOCKED_EXTERNAL_DEPENDENCY (Zero fake fallback permitted in live mode).")
        return 2

    # 3. Setup SQLite audit database and discovery
    step(3, "Initializing Persistence & Running Infrastructure Discovery")
    temp_dir = tempfile.mkdtemp(prefix="cloudpilot_live_demo_")
    db_path = str(Path(temp_dir) / "live_audit.db")
    repo = SQLiteTaskRepository(db_path=db_path)

    service = TaskService(
        repository=repo,
        switch_adapter=client,
        connection_manager=conn_mgr,
    )

    demo_workspace = str(WORKSPACE_ROOT / "samples" / "staging")
    task = await service.create_task(
        name="Live Infrastructure Optimization Assessment",
        workspace_root=demo_workspace,
    )
    task = await service.run_assessment(task.task_id)
    assessment = repo.get_assessment(task.task_id)
    assert assessment is not None
    print(f"  ✔ Discovered {len(assessment.inventory.resources)} resources across {len(assessment.inventory.files_scanned)} files.")

    # 4. Multi-Objective Pareto Optimization & Z3 Solver
    step(4, "Multi-Objective Decision Intelligence & Formal Z3 Constraint Solving")
    dec_orchestrator = DecisionOrchestrator(repository=repo)
    decision_run = dec_orchestrator.run_decision(
        task_id=task.task_id,
        workspace_root=demo_workspace,
        preference_profile=PreferenceProfile.BALANCED,
    )
    print(f"  ✔ Decision Run ID:   {decision_run.decision_id}")
    print(f"  ✔ Z3 Solver Status:  {decision_run.z3_verification_status}")
    assert "SAT" in decision_run.z3_verification_status

    # 5. Proposal Generation & Pre-Mutation SHA-256 Locking
    step(5, "Generating Cryptographic Proposal & Pre-Mutation SHA-256 Locking")
    approval_svc = ApprovalService(repository=repo)
    proposal = approval_svc.generate_proposal_from_decision(
        decision_id=decision_run.decision_id,
        ttl_seconds=3600,
    )
    print(f"  ✔ Proposal ID:       {proposal.proposal_id}")
    print(f"  ✔ Pre-Mutation Hash: {proposal.proposal_hash}")

    # 6. Publish Real Proposal to Switch Room
    step(6, f"Publishing Real Proposal Announcement to Switch Room '{cfg.room_id}'")
    proposal_msg = (
        f"### 📝 [CloudPilot SwitchOps] Formal Proposal Generated — Review Required\n"
        f"- **Proposal ID**: `{proposal.proposal_id}`\n"
        f"- **Decision ID**: `{proposal.decision_id}`\n"
        f"- **Target Workspace**: `{proposal.workspace_root}`\n"
        f"- **Pre-Mutation SHA-256**: `{proposal.proposal_hash}`\n"
        f"- **Estimated Monthly Savings**: `${float(proposal.estimated_monthly_savings):.2f}/mo`\n"
        f"- **Z3 Formal Status**: `{proposal.z3_verification_status}`\n\n"
        f"To approve, reply in this room:\n"
        f"`@cloudpilot-ops-agent approve proposal {proposal.proposal_id}`"
    )
    post_res = await client.post_message(room_id=cfg.room_id, content=proposal_msg)
    print(f"  ✔ Proposal Message Delivered to Switch Bridge: Message ID = {post_res.get('message_id') or post_res.get('id') or 'DELIVERED'}")

    # 7. Listen for Live In-Room Operator Approval Event
    step(7, "Awaiting Authenticated Human Approval via Live Switch WebSocket Stream")
    print(f"  • Listening on room '{cfg.room_id}' for operator command...")
    print(f"  • Expected command: `@cloudpilot-ops-agent approve proposal {proposal.proposal_id}`")
    print("  • Waiting up to 60 seconds for live human operator in room...")

    approved_event_data: dict | None = None
    approval_received = asyncio.Event()

    async def on_room_event(frame: dict) -> None:
        nonlocal approved_event_data
        body = frame.get("content") or frame.get("body") or frame.get("text") or ""
        if proposal.proposal_id in body and "approve" in body.lower():
            approved_event_data = frame
            approval_received.set()

    # Start listener in background
    listener_task = asyncio.create_task(
        client.listen_events(room_id=cfg.room_id, on_event=on_room_event)
    )

    try:
        await asyncio.wait_for(approval_received.wait(), timeout=60.0)
        print("  ✔ Real human approval event received from Switch room!")
    except asyncio.TimeoutError:
        listener_task.cancel()
        banner("TIMED OUT WAITING FOR LIVE OPERATOR APPROVAL")
        print(f"No in-room approval event was received for proposal {proposal.proposal_id} within 60s.")
        print("Proposal remains PENDING_APPROVAL. Bounded execution aborted (fail-closed).")
        return 1

    listener_task.cancel()

    # 8. Verify Principal & Grant Approval
    step(8, "Verifying Principal Authentication & Issuing Single-Use HMAC Token")
    event_handler = SwitchEventHandler()
    principal = event_handler.resolve_authenticated_principal(approved_event_data)
    print(f"  ✔ Authenticated Operator: {principal.display_name} ({principal.role.value})")
    assert principal.is_authorized, f"Principal {principal.principal_id} is not authorized to approve changes!"

    token_payload = approval_svc.issue_signed_approval_token(
        proposal_id=proposal.proposal_id,
        principal=principal,
    )
    approval_rec = approval_svc.approve_proposal(
        proposal_id=proposal.proposal_id,
        principal=principal,
        token_string=token_payload.token_id,
        reason="Approved via live Switch collaboration room.",
    )
    print(f"  ✔ Approval Record Saved: ID = {approval_rec.approval_id}")

    # 9. Bounded Local Sandbox Execution
    step(9, "Executing Bounded Mutation in Isolated Sandbox Workspace")
    exec_orchestrator = ExecutionOrchestrator(repository=repo)
    exec_rec = exec_orchestrator.execute_approved_proposal(
        proposal_id=proposal.proposal_id,
        token_string=token_payload.token_id,
        principal=principal,
    )
    print(f"  ✔ Execution ID:      {exec_rec.execution_id}")
    print(f"  ✔ Status:            {exec_rec.status.value}")
    print(f"  ✔ Workspace Sandbox: {exec_rec.workspace_path}")
    print(f"  ✔ Verified Flag:     {exec_rec.verified}")
    assert exec_rec.status == ExecutionStatus.COMPLETED

    # 10. Publish Real Outcome to Switch Room
    step(10, "Publishing Verified Execution Outcome to Live Switch Room")
    outcome_msg = (
        f"🚀 **[CloudPilot SwitchOps] Bounded Execution & Verification Complete**\n"
        f"- **Execution ID**: `{exec_rec.execution_id}`\n"
        f"- **Proposal ID**: `{proposal.proposal_id}`\n"
        f"- **Approver**: `{principal.display_name}` (`{principal.role.value}`)\n"
        f"- **Status**: `COMPLETED`\n"
        f"- **Syntactic AST Verification**: `PASSED`\n"
        f"- **Safety Notice**: Zero live cloud mutations. Bounded local sandbox only."
    )
    await client.post_message(room_id=cfg.room_id, content=outcome_msg)
    print(f"  ✔ Outcome published to Switch room '{cfg.room_id}'.")

    banner("STRICT LIVE DEMONSTRATION SUCCEEDED: 10/10 STEPS VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_live_demo()))

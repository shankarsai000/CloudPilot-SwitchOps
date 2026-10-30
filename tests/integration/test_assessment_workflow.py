"""
CloudPilot SwitchOps — Integration Tests: End-to-End Switch Assessment Workflow

Tests full Switch-addressed operational lifecycle:
1. Operator submits assessment prompt in Switch room
2. Coordinator acknowledges in Switch room
3. Discovery engine runs with filesystem protections
4. FinOps specialist analyzes and posts intermediate breakdown
5. SecOps specialist analyzes and posts security/reliability posture
6. Consolidated assessment report posted to Switch room
7. Inventory, findings, and assessment summary persisted to SQLite
8. Confirms read-only execution: zero files modified
"""

from pathlib import Path
import pytest

from app.domain.models import TaskStatus
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.persistence.repository import SQLiteTaskRepository
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_end_to_end_switch_assessment_workflow(tmp_path: Path) -> None:
    db_file = tmp_path / "assessment_test.db"
    repo = SQLiteTaskRepository(db_path=str(db_file))
    bridge = EmulatedSwitchBridge()
    service = TaskService(repository=repo, switch_adapter=bridge)

    # Record staging file modification times before assessment
    staging_files = list(Path("samples/staging").glob("*.*"))
    assert len(staging_files) > 0
    mtimes_before = {f: f.stat().st_mtime for f in staging_files}

    # Operator sends Phase 2 prompt into Switch room
    prompt_text = (
        "@cloudpilot-ops-agent assess ./samples/staging for cost, security and reliability risks. "
        "Read-only assessment. Do not modify anything."
    )

    human_event = await bridge.inject_human_message(
        room_id="cloudpilot-ops",
        text=prompt_text,
        sender="@lead-architect:switch",
        sender_name="Lead Architect",
    )

    # Process Switch event frame
    task = await service.handle_switch_event(human_event)

    # Assertions on completed task
    assert task is not None
    assert task.status == TaskStatus.COMPLETED
    assert task.task_type == "infrastructure_assessment"
    assert "result_summary" in task.metadata

    # Verify messages posted to Switch room
    room_msgs = bridge.get_room_messages("cloudpilot-ops")
    # Message stream: Human(1) + Ack(2) + Disc Start(3) + Disc Done(4) + FinOps(5) + SecOps(6) + Final Report(7)
    assert len(room_msgs) >= 6

    # Verify specialist outputs in Switch room
    assert any("Acknowledged request" in m["content"] for m in room_msgs)
    assert any("Infrastructure Discovery" in m["content"] for m in room_msgs)
    assert any("FinOps Intelligence Report" in m["content"] for m in room_msgs)
    assert any("SecOps & SRE Audit Report" in m["content"] for m in room_msgs)
    assert any("Consolidated Assessment" in m["content"] for m in room_msgs)

    # Verify SQLite persistence
    persisted_task = repo.get_task(task.task_id)
    assert persisted_task is not None
    assert persisted_task.status == TaskStatus.COMPLETED

    # Verify inventory persistence
    inventory = repo.get_inventory_for_task(task.task_id)
    assert inventory is not None
    assert inventory.total_resources >= 8

    # Verify findings persistence
    findings = repo.get_findings_for_task(task.task_id)
    assert len(findings) >= 5

    # Verify assessment summary persistence
    assessment = repo.get_assessment_for_task(task.task_id)
    assert assessment is not None
    assert assessment.total_resources == inventory.total_resources
    assert assessment.total_findings == len(findings)
    assert assessment.critical_findings_count >= 2
    assert float(assessment.estimated_monthly_cost) > 50.0

    # Strict Read-Only Guarantee: verify no files were touched or altered
    mtimes_after = {f: f.stat().st_mtime for f in staging_files}
    for f in staging_files:
        assert mtimes_before[f] == mtimes_after[f], f"File '{f}' was modified during read-only assessment!"

    repo.close()

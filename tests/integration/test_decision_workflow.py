"""
CloudPilot SwitchOps — Integration Tests: End-to-End Decision Workflow

Tests full Switch-addressed decision intelligence lifecycle:
1. Operator submits decision/optimization prompt in Switch room
2. Coordinator acknowledges in Switch room
3. Assessment executes (Discovery + FinOps + SecOps)
4. Decision Intelligence engine generates candidates and verifies hard constraints with Z3
5. Pareto optimization calculates non-dominated frontier
6. Recommendation report posted into Switch team room
7. Decision run and evaluations persisted to SQLite
8. Confirms strict read-only execution: zero files modified
"""

from decimal import Decimal
from pathlib import Path
import pytest

from app.domain.decisions import ParetoStatus
from app.domain.models import TaskStatus
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.persistence.repository import SQLiteTaskRepository
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_end_to_end_switch_decision_workflow(tmp_path: Path) -> None:
    db_file = tmp_path / "decision_test.db"
    repo = SQLiteTaskRepository(db_path=str(db_file))
    bridge = EmulatedSwitchBridge()
    service = TaskService(repository=repo, switch_adapter=bridge)

    # Record staging file modification times before run
    staging_files = list(Path("samples/staging").glob("*.*"))
    assert len(staging_files) > 0
    mtimes_before = {f: f.stat().st_mtime for f in staging_files}

    # Operator sends Phase 3 decision prompt into Switch room
    prompt_text = (
        "@cloudpilot-ops-agent decide on staging infrastructure optimization. "
        "Recommend optimal trade-off balancing cost and security. Read-only."
    )

    human_event = await bridge.inject_human_message(
        room_id="cloudpilot-ops",
        text=prompt_text,
        sender="@lead-architect:switch",
        sender_name="Lead Architect",
    )

    # Process Switch event frame
    task = await service.handle_switch_event(human_event)

    # Verify task completion
    assert task is not None
    assert task.status == TaskStatus.COMPLETED
    assert task.task_type == "decision_optimization"
    assert "decision_id" in task.metadata

    decision_id = task.metadata["decision_id"]

    # Verify database persistence
    run = repo.get_decision_run(decision_id)
    assert run is not None
    assert run.task_id == task.task_id
    assert "samples/staging" in run.workspace_root.replace("\\", "/")
    assert run.total_candidates_generated > 0
    assert run.feasible_candidates_count > 0
    assert run.rejected_candidates_count > 0
    assert run.pareto_optimal_count > 0
    assert run.recommended_candidate_id is not None
    assert run.z3_verification_status in ["Z3_VERIFIED_SAT", "Z3_FALLBACK"]

    # Verify evaluated candidates in repository
    evals = repo.get_candidate_evaluations(decision_id)
    assert len(evals) == run.total_candidates_generated

    # Verify adversarial candidates were rejected
    unsafe_evals = [e for e in evals if e.candidate.candidate_id.startswith("cand-unsafe")]
    assert len(unsafe_evals) >= 2
    for ue in unsafe_evals:
        assert not ue.is_feasible
        assert ue.pareto_status == ParetoStatus.INFEASIBLE
        assert len(ue.rejection_reasons) > 0

    # Verify Switch room message flow
    room_msgs = bridge.get_room_messages("cloudpilot-ops")
    assert len(room_msgs) >= 5

    # Check for decision report in Switch messages
    decision_reports = [m for m in room_msgs if "Decision Intelligence & Optimization Report" in m["content"]]
    assert len(decision_reports) == 1
    report_content = decision_reports[0]["content"]

    assert "Executive Recommendation" in report_content
    assert "Pareto Frontier & Alternatives" in report_content
    assert "Rejected Alternatives" in report_content
    assert "Next Phase Governance" in report_content

    # Strict read-only guarantee: zero files modified
    mtimes_after = {f: f.stat().st_mtime for f in staging_files}
    for f in staging_files:
        assert mtimes_before[f] == mtimes_after[f], f"File modified: {f}"

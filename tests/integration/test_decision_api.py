"""
CloudPilot SwitchOps — Integration Tests: Decision Intelligence REST API Endpoints

Verifies HTTP endpoints for initiating decision runs, querying candidate evaluations,
inspecting Pareto frontiers, retrieving constraint failures, and full decision reports.
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from app.api.assessments import (
    get_repository as assessments_get_repo,
    get_task_service as assessments_get_service,
)
from app.api.decisions import (
    get_repository as decisions_get_repo,
    get_task_service as decisions_get_service,
)
from app.api.health import (
    get_repository as health_get_repo,
    get_switch_adapter as health_get_adapter,
)
from app.api.tasks import get_task_service as tasks_get_service
from app.core.config import Settings
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.main import create_app
from app.persistence.repository import SQLiteTaskRepository
from app.services.task_service import TaskService


@pytest.fixture
def decision_test_client(tmp_path: Path):
    db_file = tmp_path / "decision_api_test.db"
    settings = Settings(environment="testing", debug=False, database_url=str(db_file))
    repo = SQLiteTaskRepository(db_path=str(db_file))
    bridge = EmulatedSwitchBridge()
    service = TaskService(repository=repo, switch_adapter=bridge)

    app = create_app(settings=settings)
    app.dependency_overrides[health_get_repo] = lambda: repo
    app.dependency_overrides[health_get_adapter] = lambda: bridge
    app.dependency_overrides[tasks_get_service] = lambda: service
    app.dependency_overrides[assessments_get_repo] = lambda: repo
    app.dependency_overrides[assessments_get_service] = lambda: service
    app.dependency_overrides[decisions_get_repo] = lambda: repo
    app.dependency_overrides[decisions_get_service] = lambda: service

    with TestClient(app) as client:
        yield client, repo

    repo.close()


def test_decision_api_lifecycle(decision_test_client):
    client, repo = decision_test_client

    # 1. Trigger decision analysis via POST /api/v1/decisions/run
    run_resp = client.post(
        "/api/v1/decisions/run",
        json={
            "workspace_root": "samples/staging",
            "preference_profile": "BALANCED",
            "room_id": "cloudpilot-ops",
            "requested_by": "@operator:switch",
        },
    )
    assert run_resp.status_code == 200, run_resp.text
    run_data = run_resp.json()
    decision_id = run_data["decision_id"]
    task_id = run_data["task_id"]

    assert decision_id.startswith("dec-")
    assert run_data["total_candidates_generated"] > 0
    assert run_data["feasible_candidates_count"] > 0
    assert run_data["pareto_optimal_count"] > 0
    assert run_data["recommended_candidate_id"] is not None

    # 2. GET /api/v1/decisions/{decision_id}
    get_resp = client.get(f"/api/v1/decisions/{decision_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["decision_id"] == decision_id

    # 3. GET /api/v1/decisions/task/{task_id}
    task_run_resp = client.get(f"/api/v1/decisions/task/{task_id}")
    assert task_run_resp.status_code == 200
    assert task_run_resp.json()["decision_id"] == decision_id

    # 4. GET /api/v1/decisions/{decision_id}/candidates
    cands_resp = client.get(f"/api/v1/decisions/{decision_id}/candidates")
    assert cands_resp.status_code == 200
    cands = cands_resp.json()
    assert len(cands) == run_data["total_candidates_generated"]

    # Filter feasible only
    feas_resp = client.get(f"/api/v1/decisions/{decision_id}/candidates?feasible_only=true")
    assert feas_resp.status_code == 200
    feas = feas_resp.json()
    assert len(feas) == run_data["feasible_candidates_count"]
    for c in feas:
        assert c["is_feasible"] is True

    # 5. GET /api/v1/decisions/{decision_id}/pareto
    pareto_resp = client.get(f"/api/v1/decisions/{decision_id}/pareto")
    assert pareto_resp.status_code == 200
    pareto = pareto_resp.json()
    assert len(pareto) == run_data["pareto_optimal_count"]
    for p in pareto:
        assert p["pareto_status"] == "PARETO_OPTIMAL"

    # 6. GET /api/v1/decisions/{decision_id}/constraints
    const_resp = client.get(f"/api/v1/decisions/{decision_id}/constraints")
    assert const_resp.status_code == 200
    const_data = const_resp.json()
    assert const_data["decision_id"] == decision_id
    assert const_data["rejected_count"] == run_data["rejected_candidates_count"]
    assert len(const_data["rejected_candidates"]) > 0

    # 7. GET /api/v1/decisions/{decision_id}/report
    report_resp = client.get(f"/api/v1/decisions/{decision_id}/report")
    assert report_resp.status_code == 200
    report_data = report_resp.json()
    assert report_data["decision_id"] == decision_id
    assert report_data["executive_recommendation"] is not None
    assert len(report_data["pareto_optimal_candidates"]) == run_data["pareto_optimal_count"]
    assert len(report_data["rejected_candidates"]) == run_data["rejected_candidates_count"]

    # 8. 404 for nonexistent decision
    not_found = client.get("/api/v1/decisions/dec-nonexistent-123")
    assert not_found.status_code == 404

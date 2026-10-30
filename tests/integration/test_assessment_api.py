"""
CloudPilot SwitchOps — Integration Tests: Assessment REST API Endpoints

Verifies HTTP endpoints for initiating assessments, querying consolidated reports,
inspecting inventories, and filtering findings.
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from app.api.assessments import (
    get_repository as assessments_get_repo,
    get_task_service as assessments_get_service,
)
from app.api.health import (
    get_repository as health_get_repo,
    get_switch_adapter as health_get_adapter,
)
from app.api.tasks import get_task_service as tasks_get_service
from app.core.config import Settings
from app.domain.finding import FindingCategory, FindingSeverity
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.main import create_app
from app.persistence.repository import SQLiteTaskRepository
from app.services.task_service import TaskService


@pytest.fixture
def assessment_test_client(tmp_path: Path):
    db_file = tmp_path / "api_test.db"
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

    with TestClient(app) as client:
        yield client, repo

    repo.close()


def test_assessment_api_full_lifecycle(assessment_test_client) -> None:
    client, repo = assessment_test_client

    # 1. Trigger assessment via POST /api/v1/assessments/run
    run_resp = client.post(
        "/api/v1/assessments/run",
        json={
            "workspace_root": "samples/staging",
            "room_id": "cloudpilot-ops",
            "requested_by": "@architect:switch",
        },
    )
    assert run_resp.status_code == 200
    asm_data = run_resp.json()
    task_id = asm_data["task_id"]
    assert asm_data["status"] == "COMPLETED"
    assert asm_data["total_resources"] >= 8
    assert asm_data["total_findings"] >= 5

    # 2. Query GET /api/v1/assessments/{task_id}
    get_resp = client.get(f"/api/v1/assessments/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["assessment_id"] == asm_data["assessment_id"]

    # 3. Query GET /api/v1/assessments/{task_id}/inventory
    inv_resp = client.get(f"/api/v1/assessments/{task_id}/inventory")
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()
    assert len(inv_data["resources"]) >= 8
    assert len(inv_data["discovered_files"]) >= 2

    # 4. Query GET /api/v1/assessments/{task_id}/findings
    findings_resp = client.get(f"/api/v1/assessments/{task_id}/findings")
    assert findings_resp.status_code == 200
    findings = findings_resp.json()
    assert len(findings) >= 5

    # 5. Query with filter ?category=FINOPS
    finops_findings = client.get(f"/api/v1/assessments/{task_id}/findings?category=FINOPS").json()
    assert len(finops_findings) >= 1
    assert all(f["category"] == "FINOPS" for f in finops_findings)

    # 6. Query with filter ?severity=CRITICAL
    crit_findings = client.get(f"/api/v1/assessments/{task_id}/findings?severity=CRITICAL").json()
    assert len(crit_findings) >= 2
    assert all(f["severity"] == "CRITICAL" for f in crit_findings)

    # 7. Query single finding GET /api/v1/assessments/{task_id}/findings/{finding_id}
    first_finding_id = findings[0]["finding_id"]
    single_f_resp = client.get(f"/api/v1/assessments/{task_id}/findings/{first_finding_id}")
    assert single_f_resp.status_code == 200
    assert single_f_resp.json()["finding_id"] == first_finding_id

    # 8. Query cost breakdown GET /api/v1/assessments/{task_id}/cost-breakdown
    cost_resp = client.get(f"/api/v1/assessments/{task_id}/cost-breakdown")
    assert cost_resp.status_code == 200
    cost_data = cost_resp.json()
    assert "total_monthly_cost" in cost_data
    assert float(cost_data["total_monthly_cost"]) > 50.0
    assert len(cost_data["items"]) >= 5

"""
CloudPilot SwitchOps — Integration Tests: SQLite Persistence & HTTP API Probes
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.api.health import (
    get_repository as health_get_repo,
)
from app.api.health import (
    get_switch_adapter as health_get_adapter,
)
from app.api.tasks import get_task_service as tasks_get_service
from app.core.config import Settings
from app.core.errors import TaskConflictError, TaskNotFoundError
from app.domain.models import (
    ActorType,
    Evidence,
    EvidenceSeverity,
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
)
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.main import create_app
from app.persistence.repository import SQLiteTaskRepository
from app.services.task_service import TaskService


@pytest.fixture
def temp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def repo(temp_db: str) -> SQLiteTaskRepository:
    r = SQLiteTaskRepository(db_path=temp_db)
    yield r
    r.close()


@pytest.fixture
def mock_switch() -> EmulatedSwitchBridge:
    return EmulatedSwitchBridge()


@pytest.fixture
def task_service(repo: SQLiteTaskRepository, mock_switch: EmulatedSwitchBridge) -> TaskService:
    return TaskService(repository=repo, switch_adapter=mock_switch)


@pytest.fixture
def client(repo: SQLiteTaskRepository, mock_switch: EmulatedSwitchBridge, task_service: TaskService) -> TestClient:
    settings = Settings(environment="testing", debug=False)
    app = create_app(settings=settings)

    # Override dependencies with test fixtures
    app.dependency_overrides[health_get_repo] = lambda: repo
    app.dependency_overrides[health_get_adapter] = lambda: mock_switch
    app.dependency_overrides[tasks_get_service] = lambda: task_service

    return TestClient(app)


class TestPersistenceLayer:
    """Validate SQLite persistence, constraints, append-only history, and evidence."""

    def test_task_save_and_get(self, repo: SQLiteTaskRepository) -> None:
        task = Task(
            title="Database persistence test",
            description="Testing SQLite storage",
            room_id="cloudpilot-ops",
            requested_by="@bob:switch",
        )
        saved = repo.save_task(task)
        assert saved.task_id == task.task_id

        fetched = repo.get_task(task.task_id)
        assert fetched is not None
        assert fetched.task_id == task.task_id
        assert fetched.title == "Database persistence test"
        assert fetched.status == TaskStatus.RECEIVED

    def test_task_conflict_raised(self, repo: SQLiteTaskRepository) -> None:
        task = Task(title="Duplicate test", room_id="r1", requested_by="u1")
        repo.save_task(task)

        # Attempting to save same task_id raises TaskConflictError
        with pytest.raises(TaskConflictError):
            repo.save_task(task)

    def test_task_update_and_missing(self, repo: SQLiteTaskRepository) -> None:
        task = Task(title="Update test", room_id="r1", requested_by="u1")
        repo.save_task(task)

        task.transition_to(TaskStatus.ACKNOWLEDGED)
        updated = repo.update_task(task)
        assert updated.status == TaskStatus.ACKNOWLEDGED

        # Nonexistent task raises TaskNotFoundError
        ghost = Task(task_id="ghost-task", title="Ghost", room_id="r1", requested_by="u1")
        with pytest.raises(TaskNotFoundError):
            repo.update_task(ghost)

    def test_append_only_event_history(self, repo: SQLiteTaskRepository) -> None:
        task = Task(title="Audit test", room_id="r1", requested_by="u1")
        repo.save_task(task)

        evt1 = TaskEvent(
            task_id=task.task_id,
            event_type=TaskEventType.TASK_RECEIVED,
            actor_id="u1",
            actor_type=ActorType.HUMAN,
            correlation_id=task.correlation_id,
            payload={"step": 1},
        )
        evt2 = TaskEvent(
            task_id=task.task_id,
            event_type=TaskEventType.TASK_ACKNOWLEDGED,
            actor_id="agent",
            actor_type=ActorType.AGENT,
            correlation_id=task.correlation_id,
            payload={"step": 2},
        )
        repo.append_event(evt1)
        repo.append_event(evt2)

        history = repo.get_events_for_task(task.task_id)
        assert len(history) == 2
        assert history[0].event_type == TaskEventType.TASK_RECEIVED
        assert history[1].event_type == TaskEventType.TASK_ACKNOWLEDGED

    def test_evidence_persistence(self, repo: SQLiteTaskRepository) -> None:
        task = Task(title="Evidence task", room_id="r1", requested_by="u1")
        repo.save_task(task)

        evi = Evidence(
            task_id=task.task_id,
            source_type="terraform",
            source_reference="main.tf:42",
            finding_category="UNRESTRICTED_INGRESS",
            observed_value={"port": 22, "cidr": "0.0.0.0/0"},
            expected_value={"cidr": "10.0.0.0/8"},
            severity=EvidenceSeverity.HIGH,
            provenance={"scanner": "tfsec"},
        )
        saved = repo.save_evidence(evi)
        assert saved.evidence_id == evi.evidence_id

        findings = repo.get_evidence_for_task(task.task_id)
        assert len(findings) == 1
        assert findings[0].finding_category == "UNRESTRICTED_INGRESS"
        assert findings[0].severity == EvidenceSeverity.HIGH


class TestAPIEndpoints:
    """Validate HTTP API routes, probes, and diagnostic triggers."""

    def test_liveness_probe(self, client: TestClient) -> None:
        resp = client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert data["app_name"] == "CloudPilot SwitchOps"

    def test_readiness_probe_healthy(self, client: TestClient) -> None:
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["database"] == "healthy"
        assert data["switch_integration"]["status"] == "healthy"

    def test_task_lifecycle_simulation_endpoint(self, client: TestClient, mock_switch: EmulatedSwitchBridge) -> None:
        payload = {
            "room_id": "cloudpilot-ops",
            "text": "@CloudPilot review the staging infrastructure for a cost and security assessment. Do not modify any files or infrastructure.",
            "sender": "@lead-architect:switch",
            "sender_name": "Lead Architect",
        }
        resp = client.post("/api/v1/switch/simulate-message", json=payload)
        assert resp.status_code == 200
        task_data = resp.json()

        # Task must have reached COMPLETED
        assert task_data["status"] == TaskStatus.COMPLETED.value
        task_id = task_data["task_id"]

        # Verify task lookup endpoint
        get_resp = client.get(f"/api/v1/tasks/{task_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["task_id"] == task_id

        # Verify event history endpoint
        evt_resp = client.get(f"/api/v1/tasks/{task_id}/events")
        assert evt_resp.status_code == 200
        events = evt_resp.json()
        assert len(events) >= 4  # RECEIVED, ACKNOWLEDGED, STARTED, COMPLETED
        event_types = [e["event_type"] for e in events]
        assert "TASK_RECEIVED" in event_types
        assert "TASK_ACKNOWLEDGED" in event_types
        assert "TASK_STARTED" in event_types
        assert "TASK_COMPLETED" in event_types

        # Verify messages posted to the Switch room
        room_msgs = mock_switch.get_room_messages("cloudpilot-ops")
        assert len(room_msgs) >= 2  # acknowledgment message + final execution report
        assert any("Acknowledged request" in m["content"] for m in room_msgs)
        assert any("Task Execution Report" in m["content"] for m in room_msgs)

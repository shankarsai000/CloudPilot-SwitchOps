"""
CloudPilot SwitchOps — Unit Tests: Domain Models, Lifecycle Transitions, Config & Logging
"""

from datetime import timezone

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import InvalidStateTransitionError
from app.core.logging import (
    get_correlation_id,
    redact_secrets,
    set_correlation_id,
)
from app.domain.models import (
    ActorType,
    Evidence,
    EvidenceSeverity,
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
)


class TestDomainTaskLifecycle:
    """Validate task domain model, field constraints, and transition policy."""

    def test_task_creation_defaults(self) -> None:
        task = Task(
            title="Review staging cluster",
            description="Perform security assessment",
            room_id="cloudpilot-ops",
            requested_by="@alice:switch",
        )
        assert task.task_id.startswith("task-")
        assert task.status == TaskStatus.RECEIVED
        assert task.correlation_id.startswith("corr-")
        assert task.created_at.tzinfo == timezone.utc
        assert task.updated_at.tzinfo == timezone.utc

    def test_task_validation_rejection(self) -> None:
        with pytest.raises(ValidationError):
            # Title cannot be empty
            Task(title="", room_id="cloudpilot-ops", requested_by="@alice:switch")

        with pytest.raises(ValidationError):
            # room_id cannot be empty
            Task(title="Valid title", room_id="", requested_by="@alice:switch")

    def test_valid_task_state_transitions(self) -> None:
        task = Task(
            title="Valid lifecycle run",
            room_id="cloudpilot-ops",
            requested_by="@alice:switch",
        )
        assert task.status == TaskStatus.RECEIVED

        # RECEIVED -> ACKNOWLEDGED
        task.transition_to(TaskStatus.ACKNOWLEDGED)
        assert task.status == TaskStatus.ACKNOWLEDGED

        # ACKNOWLEDGED -> IN_PROGRESS
        task.transition_to(TaskStatus.IN_PROGRESS)
        assert task.status == TaskStatus.IN_PROGRESS

        # IN_PROGRESS -> COMPLETED
        task.transition_to(TaskStatus.COMPLETED)
        assert task.status == TaskStatus.COMPLETED

    def test_valid_failure_transition(self) -> None:
        task = Task(
            title="Failure lifecycle run",
            room_id="cloudpilot-ops",
            requested_by="@alice:switch",
        )
        task.transition_to(TaskStatus.ACKNOWLEDGED)
        task.transition_to(TaskStatus.IN_PROGRESS)
        task.transition_to(TaskStatus.FAILED)
        assert task.status == TaskStatus.FAILED

    def test_valid_cancellation_paths(self) -> None:
        # Cancel from RECEIVED
        t1 = Task(title="Cancel 1", room_id="r1", requested_by="u1")
        t1.transition_to(TaskStatus.CANCELLED)
        assert t1.status == TaskStatus.CANCELLED

        # Cancel from ACKNOWLEDGED
        t2 = Task(title="Cancel 2", room_id="r1", requested_by="u1")
        t2.transition_to(TaskStatus.ACKNOWLEDGED)
        t2.transition_to(TaskStatus.CANCELLED)
        assert t2.status == TaskStatus.CANCELLED

        # Cancel from IN_PROGRESS
        t3 = Task(title="Cancel 3", room_id="r1", requested_by="u1")
        t3.transition_to(TaskStatus.ACKNOWLEDGED)
        t3.transition_to(TaskStatus.IN_PROGRESS)
        t3.transition_to(TaskStatus.CANCELLED)
        assert t3.status == TaskStatus.CANCELLED

    def test_invalid_state_transitions_rejected(self) -> None:
        task = Task(title="Illegal jump", room_id="r1", requested_by="u1")

        # Cannot jump RECEIVED -> COMPLETED directly
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            task.transition_to(TaskStatus.COMPLETED)
        assert exc_info.value.code == "INVALID_STATE_TRANSITION"

        # Cannot jump RECEIVED -> FAILED directly
        with pytest.raises(InvalidStateTransitionError):
            task.transition_to(TaskStatus.FAILED)

        # Advance to COMPLETED
        task.transition_to(TaskStatus.ACKNOWLEDGED)
        task.transition_to(TaskStatus.IN_PROGRESS)
        task.transition_to(TaskStatus.COMPLETED)

        # COMPLETED is terminal: cannot transition to IN_PROGRESS or CANCELLED
        with pytest.raises(InvalidStateTransitionError):
            task.transition_to(TaskStatus.IN_PROGRESS)
        with pytest.raises(InvalidStateTransitionError):
            task.transition_to(TaskStatus.CANCELLED)


class TestEventAndEvidenceContracts:
    """Validate event models and evidence findings structure."""

    def test_task_event_creation(self) -> None:
        event = TaskEvent(
            task_id="task-123",
            event_type=TaskEventType.TASK_RECEIVED,
            actor_id="@operator:switch",
            actor_type=ActorType.HUMAN,
            correlation_id="corr-999",
            payload={"action": "review"},
        )
        assert event.event_id.startswith("evt-")
        assert event.schema_version == "1.0"
        assert event.timestamp.tzinfo == timezone.utc

    def test_evidence_contract_validation(self) -> None:
        evidence = Evidence(
            source_type="aws",
            source_reference="arn:aws:ec2:us-east-1:123456789012:instance/i-0abcdef",
            finding_category="IDLE_RESOURCE",
            observed_value={"cpu_utilization_avg_pct": 1.2, "days_idle": 14},
            expected_value={"min_cpu_utilization_pct": 10.0},
            severity=EvidenceSeverity.HIGH,
            provenance={"rule_id": "FIN-001", "scanner": "CloudPilot-CostEngine"},
            confidence=0.95,
        )
        assert evidence.evidence_id.startswith("evi-")
        assert evidence.confidence == 0.95
        assert evidence.severity == EvidenceSeverity.HIGH

    def test_evidence_invalid_confidence_rejected(self) -> None:
        # Confidence must be between 0.0 and 1.0
        with pytest.raises(ValidationError):
            Evidence(
                source_type="simulator",
                source_reference="res-1",
                finding_category="TEST",
                observed_value=1,
                expected_value=2,
                confidence=1.5,
            )


class TestConfigAndSecurity:
    """Validate environment settings, defaults, and secret redaction."""

    def test_settings_defaults(self) -> None:
        settings = Settings()
        assert settings.app_name == "CloudPilot SwitchOps"
        assert settings.environment in ("development", "testing")
        assert settings.is_production is False
        assert settings.switch_room_id == "cloudpilot-ops"

    def test_secret_redaction(self) -> None:
        msg = "Connecting with Bearer mysecrettoken123456 and api_key=supersecretkey999"
        sanitized = redact_secrets(msg)
        assert "mysecrettoken123456" not in sanitized
        assert "supersecretkey999" not in sanitized
        assert "Bearer [REDACTED]" in sanitized
        assert "api_key=[REDACTED]" in sanitized

    def test_correlation_id_propagation(self) -> None:
        set_correlation_id("test-corr-456")
        assert get_correlation_id() == "test-corr-456"
        set_correlation_id(None)
        assert get_correlation_id() is None

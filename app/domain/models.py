"""
CloudPilot SwitchOps — Domain Models, Enums & Lifecycle Contracts

Defines the typed domain contracts for tasks, append-only events, and evidence.
Enforces strict state transitions and validation rules.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.errors import InvalidStateTransitionError


class TaskStatus(str, Enum):
    """
    Strict lifecycle statuses for a CloudPilot task.
    """
    RECEIVED = "RECEIVED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Allowed state transitions: key is current status, values are set of permitted target statuses
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.RECEIVED: {TaskStatus.ACKNOWLEDGED, TaskStatus.CANCELLED},
    TaskStatus.ACKNOWLEDGED: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),  # Terminal state
    TaskStatus.FAILED: set(),     # Terminal state
    TaskStatus.CANCELLED: set(),  # Terminal state
}


class ActorType(str, Enum):
    """Type of entity taking action on a task or emitting an event."""
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class TaskEventType(str, Enum):
    """Standardized event types for task audit trail."""
    TASK_RECEIVED = "TASK_RECEIVED"
    TASK_ACKNOWLEDGED = "TASK_ACKNOWLEDGED"
    TASK_STARTED = "TASK_STARTED"
    TASK_UPDATED = "TASK_UPDATED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    EVIDENCE_ATTACHED = "EVIDENCE_ATTACHED"
    MESSAGE_POSTED = "MESSAGE_POSTED"


class TaskEvent(BaseModel):
    """
    Immutable, append-only audit event representing a milestone in a task lifecycle.
    """
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    task_id: str
    event_type: TaskEventType
    actor_id: str
    actor_type: ActorType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = Field(default="1.0")

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class EvidenceSeverity(str, Enum):
    """Severity classification for infrastructure evidence findings."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Evidence(BaseModel):
    """
    Structured, versioned evidence contract for FinOps, SecOps, or Reliability findings.
    """
    evidence_id: str = Field(default_factory=lambda: f"evi-{uuid.uuid4().hex[:12]}")
    task_id: str | None = None
    source_type: str = Field(..., description="Source system e.g. aws, azure, simulator, terraform")
    source_reference: str = Field(..., description="Identifier of inspected resource or config")
    finding_category: str = Field(..., description="Category: COST_ANOMALY, SECURITY_EXPOSURE, IDLE_RESOURCE, etc.")
    observed_value: Any = Field(..., description="Actual value or state detected")
    expected_value: Any = Field(..., description="Expected baseline, threshold, or policy specification")
    severity: EvidenceSeverity = Field(default=EvidenceSeverity.LOW)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: dict[str, Any] = Field(default_factory=dict, description="Metadata on tool, scanner, or rule used")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Defensible confidence score (0.0-1.0)")
    schema_version: str = Field(default="1.0")

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class Task(BaseModel):
    """
    Core domain model representing a human-directed or agent-collaborative CloudPilot task.
    """
    task_id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:12]}")
    task_type: str = Field(default="infrastructure_review", description="Type of operational task requested")
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    room_id: str = Field(..., min_length=1, description="Originating Switch room ID")
    requested_by: str = Field(..., min_length=1, description="Participant ID (e.g. @operator:switch or username)")
    status: TaskStatus = Field(default=TaskStatus.RECEIVED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str = Field(default_factory=lambda: f"corr-{uuid.uuid4().hex[:12]}")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at", "updated_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    def can_transition_to(self, target_status: TaskStatus) -> bool:
        """Check if transitioning from current status to target status is valid."""
        return target_status in ALLOWED_TRANSITIONS.get(self.status, set())

    def transition_to(self, target_status: TaskStatus) -> None:
        """
        Transition task to target status if valid under policy; raises InvalidStateTransitionError otherwise.
        """
        if not self.can_transition_to(target_status):
            raise InvalidStateTransitionError(
                current_status=self.status.value,
                target_status=target_status.value,
                task_id=self.task_id,
            )
        self.status = target_status
        self.updated_at = datetime.now(timezone.utc)

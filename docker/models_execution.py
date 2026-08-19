"""
Autonomous Execution & Control Layer - Pydantic Models

Defines models for execution states, records, rollout progress, rollback events,
and execution-specific logs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════


class ExecutionState(str, Enum):
    """Possible states for an execution pipeline run."""

    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RUNNING = "RUNNING"
    MONITORING = "MONITORING"
    COMPLETED = "COMPLETED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class RolloutStrategy(str, Enum):
    """Deployment rollout strategy."""

    CANARY = "CANARY"
    BLUE_GREEN = "BLUE_GREEN"
    ROLLING = "ROLLING"
    SHADOW = "SHADOW"
    DIRECT = "DIRECT"


# ═══════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════


class RolloutProgress(BaseModel):
    """Progress tracking for rollout actions."""

    strategy: RolloutStrategy = Field(default=RolloutStrategy.DIRECT)
    target_percentage: float = Field(default=100.0, ge=0.0, le=100.0)
    current_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    active_slice: str = Field(default="primary", description="primary, canary, green, blue")
    step_index: int = Field(default=0)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class RollbackRecord(BaseModel):
    """Record of a rollback execution."""

    rollback_id: str = Field(..., description="Unique rollback identifier")
    execution_id: str = Field(..., description="Associated execution run ID")
    trigger_reason: str = Field(..., description="Why the rollback was triggered")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(None)
    status: str = Field(default="RUNNING", description="RUNNING, COMPLETED, FAILED")
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionRecord(BaseModel):
    """Database representation of an execution process."""

    execution_id: str = Field(..., description="Unique execution identifier")
    decision_id: str = Field(..., description="Associated Decision Engine ID")
    target_id: str = Field(..., description="Target resource or application")
    action: str = Field(..., description="Action name (e.g. RESIZE, TERMINATE)")
    state: ExecutionState = Field(default=ExecutionState.PENDING)
    rollout: RolloutProgress = Field(default_factory=RolloutProgress)
    rollback_history: list[RollbackRecord] = Field(default_factory=list)
    lock_acquired: bool = Field(default=False)
    started_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)
    error_message: Optional[str] = Field(None)
    metrics_summary: dict[str, Any] = Field(default_factory=dict, description="Live monitored telemetry during execution")
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExecutionEvent(BaseModel):
    """Fired for progress updates or metric anomalies."""

    event_id: str = Field(..., description="Unique event identifier")
    execution_id: str = Field(..., description="Associated execution run ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str = Field(default="INFO", description="INFO, WARNING, ERROR, CRITICAL")
    message: str = Field(..., description="Event details description")
    details: dict[str, Any] = Field(default_factory=dict)

"""
CloudPilot SwitchOps — Execution Domain Models (Phase 4)

Defines isolated workspace execution lifecycles, structured file mutations,
post-execution verification reports, and rollback recovery states.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator


class ExecutionStatus(str, Enum):
    """Execution lifecycle state."""
    INITIALIZING = "INITIALIZING"
    PRE_CHECK_PASSED = "PRE_CHECK_PASSED"
    PRE_CHECK_FAILED = "PRE_CHECK_FAILED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    POST_CHECK_FAILED = "POST_CHECK_FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class FileMutationRecord(BaseModel):
    """
    Audit record of an individual structured file modification applied to a workspace.
    """
    file_path: str = Field(..., description="Relative path of modified file")
    before_hash: str = Field(..., description="SHA256 digest before mutation")
    after_hash: str = Field(..., description="SHA256 digest after mutation")
    operation: str = Field(default="UPDATE_ATTRIBUTE", description="UPDATE_ATTRIBUTE, REPLACE_VALUE, REMOVE_BLOCK")
    resource_id: str
    attribute_path: str
    old_value: str
    new_value: str
    status: str = Field(default="APPLIED", description="APPLIED, FAILED, REVERTED")

    @property
    def relative_path(self) -> str:
        return self.file_path

    @property
    def mutation_type(self) -> str:
        return self.operation


class ExecutionRecord(BaseModel):
    """
    Consolidated audit record of an execution attempt within an isolated workspace.
    """
    execution_id: str = Field(default_factory=lambda: f"exec-{uuid.uuid4().hex[:10]}")
    proposal_id: str
    proposal_hash: str
    approver_id: str
    status: ExecutionStatus = Field(default=ExecutionStatus.INITIALIZING)
    workspace_path: str = Field(..., description="Filesystem path of the isolated workspace")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    applied_mutations: List[FileMutationRecord] = Field(default_factory=list)
    validation_results: Dict[str, Any] = Field(default_factory=dict)
    recovery_status: Optional[str] = None
    error_message: Optional[str] = None
    disclaimer: str = Field(
        default="CloudPilot SwitchOps Bounded Execution completed in isolated sandbox. Read-only boundary on production/samples preserved. Live cloud mutation (terraform apply/cloud provider APIs) strictly prohibited."
    )
    schema_version: str = Field(default="1.0")

    @field_validator("started_at", "completed_at")
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    def mark_completed(self, now: Optional[datetime] = None) -> None:
        self.status = ExecutionStatus.COMPLETED
        self.completed_at = now or datetime.now(timezone.utc)

    def mark_failed(self, error: str, now: Optional[datetime] = None) -> None:
        self.status = ExecutionStatus.FAILED
        self.error_message = error
        self.completed_at = now or datetime.now(timezone.utc)

    def mark_rolled_back(self, recovery_status: str, now: Optional[datetime] = None) -> None:
        self.status = ExecutionStatus.ROLLED_BACK
        self.recovery_status = recovery_status
        self.completed_at = now or datetime.now(timezone.utc)

    @property
    def mutations(self) -> List[FileMutationRecord]:
        return self.applied_mutations

    @property
    def isolated_workspace_path(self) -> str:
        return self.workspace_path

    @property
    def audit_trail_hash(self) -> str:
        return self.proposal_hash


class AuditLogEvent(BaseModel):
    """
    Append-only cryptographically chained execution audit log entry.
    """
    audit_id: str = Field(default_factory=lambda: f"audit-{uuid.uuid4().hex[:12]}")
    execution_id: str
    proposal_id: str
    event_type: str
    actor_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = Field(default_factory=dict)
    prev_audit_hash: str = Field(default="0" * 64)
    audit_hash: str = Field(default="")

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    def compute_audit_hash(self) -> str:
        """Computes hash chain digest linking event to previous audit entry."""
        payload = {
            "audit_id": self.audit_id,
            "execution_id": self.execution_id,
            "proposal_id": self.proposal_id,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "prev_audit_hash": self.prev_audit_hash,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

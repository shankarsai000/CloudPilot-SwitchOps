"""
CloudPilot SwitchOps — Approval Domain Models (Phase 4)

Defines explicit approval lifecycles, authenticated principals, cryptographic
approval token contracts, and tamper-evident approval records.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator


class ApprovalStatus(str, Enum):
    """Lifecycle status of an approval record."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONSUMED = "CONSUMED"


class ApproverRole(str, Enum):
    """Authorized human approver roles."""
    PLATFORM_LEAD = "PLATFORM_LEAD"
    SRE_ADMIN = "SRE_ADMIN"
    FINOPS_ADMIN = "FINOPS_ADMIN"
    SECURITY_ADMIN = "SECURITY_ADMIN"
    CLOUD_OPS_LEAD = "CLOUD_OPS_LEAD"
    OPERATOR = "OPERATOR"  # Non-authoritative (cannot approve hard changes)


# Authorized roles permitted to approve infrastructure mutations
PERMITTED_APPROVAL_ROLES = {
    ApproverRole.PLATFORM_LEAD,
    ApproverRole.SRE_ADMIN,
    ApproverRole.FINOPS_ADMIN,
    ApproverRole.SECURITY_ADMIN,
    ApproverRole.CLOUD_OPS_LEAD,
}


class ApprovalPrincipal(BaseModel):
    """
    Authenticated human operator identity authorized to evaluate and grant change approvals.
    Prevents unauthenticated identity spoofing.
    """
    principal_id: str = Field(..., description="Unique user identifier e.g. user-ops-lead-01")
    display_name: str = Field(..., description="Human-readable name")
    role: ApproverRole = Field(..., description="Assigned organizational role")
    authenticated: bool = Field(default=False, description="Whether identity was verified by auth provider")
    auth_mechanism: str = Field(
        default="UNAUTHENTICATED",
        description="SWITCH_AUTHENTICATED_SESSION, API_BEARER_TOKEN, RBAC_TOKEN"
    )

    @property
    def is_authorized(self) -> bool:
        """Returns True if the principal is authenticated and holds an authorized approval role."""
        return self.authenticated and self.role in PERMITTED_APPROVAL_ROLES


class ApprovalTokenPayload(BaseModel):
    """
    Canonical data payload signed into HMAC-SHA256 approval tokens.
    """
    token_id: str = Field(default_factory=lambda: f"tok-{uuid.uuid4().hex[:12]}")
    proposal_id: str
    proposal_hash: str
    approver_id: str
    approver_role: str
    decision_id: str
    task_id: str
    issued_at: int = Field(description="Unix timestamp (seconds)")
    expires_at: int = Field(description="Unix timestamp (seconds)")


class ApprovalRecord(BaseModel):
    """
    Persistent, auditable record binding an authenticated approval decision
    to an exact proposal ID, proposal hash, and single-use token ID.
    """
    approval_id: str = Field(default_factory=lambda: f"appr-{uuid.uuid4().hex[:10]}")
    proposal_id: str
    proposal_hash: str
    approver_id: str
    approver_role: ApproverRole
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    approval_token_id: str
    decision_id: str
    task_id: str
    rejection_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    consumed_at: Optional[datetime] = None
    schema_version: str = Field(default="1.0")

    @field_validator("created_at", "expires_at", "consumed_at")
    @classmethod
    def ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Checks if approval expiration timestamp has elapsed."""
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        return current_time > self.expires_at

    def mark_approved(self) -> None:
        """Transitions to APPROVED status."""
        self.status = ApprovalStatus.APPROVED

    def mark_rejected(self, reason: str) -> None:
        """Transitions to REJECTED status with reason."""
        self.status = ApprovalStatus.REJECTED
        self.rejection_reason = reason

    def mark_consumed(self, now: Optional[datetime] = None) -> None:
        """Marks the approval as single-use consumed upon execution initiation."""
        self.status = ApprovalStatus.CONSUMED
        self.consumed_at = now or datetime.now(timezone.utc)

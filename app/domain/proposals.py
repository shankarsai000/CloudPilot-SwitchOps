"""
CloudPilot SwitchOps — Proposal Domain Models (Phase 4)

Defines exact, deterministic infrastructure change proposals generated from
verified DecisionRuns and evaluated Candidates for human-in-the-loop approval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.candidates import Candidate, CandidateType, ProposedChange


class ProposalStatus(str, Enum):
    """Lifecycle status of a change proposal."""
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"


class Proposal(BaseModel):
    """
    Exact, proposal-bound immutable specification of proposed infrastructure mutations.
    Bound to a specific DecisionRun, candidate, source file hashes, and proposal hash.
    """
    proposal_id: str = Field(default_factory=lambda: f"prop-{uuid.uuid4().hex[:10]}")
    decision_id: str
    task_id: str
    candidate_id: str
    title: str
    description: str
    candidate_type: CandidateType = CandidateType.CUSTOM
    workspace_root: str
    source_finding_ids: List[str] = Field(default_factory=list)
    affected_resource_ids: List[str] = Field(default_factory=list)
    source_file_paths: List[str] = Field(default_factory=list, description="Relative paths inside workspace root")
    canonical_proposed_changes: List[ProposedChange] = Field(default_factory=list)
    before_state_file_hashes: Dict[str, str] = Field(
        default_factory=dict,
        description="Relative file path -> SHA256 digest of before-state content"
    )
    expected_after_state_file_hashes: Dict[str, str] = Field(
        default_factory=dict,
        description="Relative file path -> predicted SHA256 digest after applied mutations"
    )
    proposal_hash: str = Field(description="Deterministic SHA256 digest of proposed mutations")
    policy_version: str = Field(default="1.0")
    pricing_catalog_version: str = Field(default="1.0")
    objective_model_version: str = Field(default="1.1")
    z3_verification_status: str = Field(default="Z3_CONSTRAINTS_SAT")
    optimization_scope: str = Field(default="BOUNDED_COMBINATION (k=3)")
    rejected_alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    estimated_monthly_savings: str = "0.00"
    estimated_monthly_cost_before: str = "0.00"
    estimated_monthly_cost_after: str = "0.00"
    security_impact: str = "NEUTRAL"
    reliability_impact: str = "NEUTRAL"
    operational_complexity: str = "LOW"
    status: ProposalStatus = Field(default=ProposalStatus.PENDING_APPROVAL)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    schema_version: str = Field(default="1.0")

    @field_validator("created_at", "expires_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_proposal(self) -> Proposal:
        if not self.proposal_hash:
            self.proposal_hash = self.compute_proposal_hash()
        return self

    def compute_proposal_hash(self) -> str:
        """Computes deterministic SHA256 digest over canonical mutation payload."""
        payload = [
            {
                "resource_id": ch.resource_id,
                "attribute_path": ch.attribute_path,
                "current_value": str(ch.current_value),
                "proposed_value": str(ch.proposed_value),
                "action_type": ch.action_type,
            }
            for ch in sorted(self.canonical_proposed_changes, key=lambda x: (x.resource_id, x.attribute_path))
        ]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Returns True if proposal expiration timestamp has passed."""
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        return current_time > self.expires_at

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Returns canonical dictionary representation for auditing and hashing."""
        return {
            "proposal_id": self.proposal_id,
            "decision_id": self.decision_id,
            "task_id": self.task_id,
            "candidate_id": self.candidate_id,
            "proposal_hash": self.proposal_hash,
            "policy_version": self.policy_version,
            "pricing_catalog_version": self.pricing_catalog_version,
            "z3_verification_status": self.z3_verification_status,
            "source_finding_ids": sorted(self.source_finding_ids),
            "affected_resource_ids": sorted(self.affected_resource_ids),
            "source_file_paths": sorted(self.source_file_paths),
            "before_state_file_hashes": dict(sorted(self.before_state_file_hashes.items())),
            "expected_after_state_file_hashes": dict(sorted(self.expected_after_state_file_hashes.items())),
            "expires_at": self.expires_at.isoformat(),
        }


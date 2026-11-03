"""
CloudPilot SwitchOps — Candidate Change Proposals Domain Models

Represents actionable, typed candidate infrastructure changes derived
from FinOps, SecOps, SRE findings, and inventory declarations.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator


class CandidateType(str, Enum):
    """Classification of the proposed change."""
    RESIZE_COMPUTE = "RESIZE_COMPUTE"
    RIGHTSIZE_COMPUTE = "RESIZE_COMPUTE"
    DOWNGRADE_STORAGE = "DOWNGRADE_STORAGE"
    TERMINATE_UNATTACHED_STORAGE = "DOWNGRADE_STORAGE"
    SCHEDULE_DATABASE = "SCHEDULE_DATABASE"
    RESTRICT_INGRESS = "RESTRICT_INGRESS"
    RESTRICT_SECURITY_GROUP = "RESTRICT_INGRESS"
    ISOLATE_SERVICE = "ISOLATE_SERVICE"
    REMOVE_PRIVILEGED = "REMOVE_PRIVILEGED"
    CONTAINER_SECURITY = "REMOVE_PRIVILEGED"
    REMOVE_DOCKER_SOCKET = "REMOVE_DOCKER_SOCKET"
    ENABLE_ENCRYPTION = "ENABLE_ENCRYPTION"
    ENABLE_STORAGE_ENCRYPTION = "ENABLE_ENCRYPTION"
    ADD_HEALTHCHECK = "ADD_HEALTHCHECK"
    ADD_PERSISTENT_VOLUME = "ADD_PERSISTENT_VOLUME"
    SET_RESTART_POLICY = "SET_RESTART_POLICY"
    SET_RESOURCE_LIMITS = "SET_RESOURCE_LIMITS"
    MULTI_AZ_FAILOVER = "MULTI_AZ_FAILOVER"
    MULTI_AZ_DEPLOYMENT = "MULTI_AZ_FAILOVER"
    COMPOSITE_PLAN = "COMPOSITE_PLAN"      # Bounded combination of multiple compatible candidates
    DROP_PERSISTENCE = "DROP_PERSISTENCE"  # Deliberate anti-pattern candidate for testing rejection
    DISABLE_AUTH = "DISABLE_AUTH"          # Deliberate anti-pattern candidate for testing rejection
    OTHER = "OTHER"
    CUSTOM = "CUSTOM"


class ImpactLevel(str, Enum):
    """Standardized impact level for security and reliability."""
    HIGH_POSITIVE = "HIGH_POSITIVE"
    HIGHLY_POSITIVE = "HIGH_POSITIVE"
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    HIGH_NEGATIVE = "HIGH_NEGATIVE"
    HIGHLY_NEGATIVE = "HIGH_NEGATIVE"


class OperationalComplexity(str, Enum):
    """Operational friction and implementation risk."""
    LOW = "LOW"        # In-place restart or simple config update
    MEDIUM = "MEDIUM"  # Scheduled downtime, snapshot migration
    HIGH = "HIGH"      # Network re-architecture, stateful data migration


class ApplicabilityStatus(str, Enum):
    """Feasibility of the proposal given the declaring provider and syntax."""
    APPLICABLE = "APPLICABLE"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class ProposedChange(BaseModel):
    """Individual attribute mutation proposed on a discovered resource."""
    resource_id: str
    resource_name: str = ""
    resource_type: str = ""
    source_file: str = ""
    attribute_path: str = ""
    current_value: Any = None
    proposed_value: Any = None
    action_type: str = Field(default="MODIFY", description="MODIFY, ADD, REMOVE")


class Candidate(BaseModel):
    """
    Actionable, evidence-backed candidate change proposal.
    Generated deterministically from Phase 2 assessment findings and inventory attributes.
    """
    candidate_id: str = Field(default_factory=lambda: f"cand-{uuid.uuid4().hex[:10]}")
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., max_length=2048)
    candidate_type: CandidateType
    affected_resource_ids: List[str] = Field(default_factory=list)
    target_resource_ids: List[str] = Field(default_factory=list)
    source_finding_ids: List[str] = Field(default_factory=list)
    proposed_changes: List[ProposedChange] = Field(default_factory=list)
    estimated_monthly_cost_before: str = Field(default="0.00", description="Decimal string in USD")
    estimated_monthly_cost_after: str = Field(default="0.00", description="Decimal string in USD")
    estimated_monthly_savings: str = Field(default="0.00", description="Decimal string in USD (positive = savings)")
    security_impact: ImpactLevel = Field(default=ImpactLevel.NEUTRAL)
    reliability_impact: ImpactLevel = Field(default=ImpactLevel.NEUTRAL)
    operational_complexity: OperationalComplexity = Field(default=OperationalComplexity.LOW)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    assumptions: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    applicability: ApplicabilityStatus = Field(default=ApplicabilityStatus.APPLICABLE)
    reversibility: str = Field(default="HIGH", description="HIGH, MEDIUM, LOW")
    member_candidate_ids: List[str] = Field(default_factory=list, description="IDs of component candidates if COMPOSITE_PLAN")
    assessment_id: Optional[str] = Field(default=None, description="Assessment provenance reference")
    pricing_catalog_version: str = Field(default="1.0")
    policy_version: str = Field(default="1.0")
    objective_model_version: str = Field(default="1.1")
    schema_version: str = Field(default="1.1")

    @field_validator(
        "estimated_monthly_cost_before",
        "estimated_monthly_cost_after",
        "estimated_monthly_savings",
        mode="before",
    )
    @classmethod
    def convert_decimal_to_str(cls, v: Any) -> str:
        if v is None:
            return "0.00"
        return str(v)

    @model_validator(mode="before")
    @classmethod
    def sync_resource_ids(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "target_resource_ids" in data and "affected_resource_ids" not in data:
                data["affected_resource_ids"] = data["target_resource_ids"]
            elif "affected_resource_ids" in data and "target_resource_ids" not in data:
                data["target_resource_ids"] = data["affected_resource_ids"]
        return data

    @property
    def is_cost_saving(self) -> bool:
        from decimal import Decimal
        return Decimal(self.estimated_monthly_savings) > Decimal("0.00")

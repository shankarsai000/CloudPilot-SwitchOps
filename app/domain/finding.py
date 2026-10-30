"""
CloudPilot SwitchOps — Findings & Assessment Summary Domain Models

Provides versioned, evidence-backed finding structures for FinOps, SecOps,
and SRE/Reliability intelligence engines.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator


class FindingCategory(str, Enum):
    """Classification category for specialist findings."""
    DISCOVERY = "DISCOVERY"
    FINOPS = "FINOPS"
    SECURITY = "SECURITY"
    RELIABILITY = "RELIABILITY"


class FindingSeverity(str, Enum):
    """Standardized severity classification."""
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Finding(BaseModel):
    """
    Structured, evidence-backed finding emitted by FinOps, SecOps, or SRE specialist engines.
    """
    finding_id: str = Field(default_factory=lambda: f"fnd-{uuid.uuid4().hex[:10]}")
    task_id: str
    agent_id: str = Field(..., description="Specialist component identifier e.g. finops-agent, secops-agent")
    category: FindingCategory
    rule_id: str = Field(..., description="Stable rule identifier e.g. SEC-001, FIN-002, REL-001")
    severity: FindingSeverity
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., max_length=2048)
    source_file: str = Field(..., description="Declaring configuration file relative to workspace")
    source_location: Optional[str] = Field(None, description="Line number or resource identifier")
    observed_value: Any = Field(..., description="Actual configuration or metric detected")
    expected_value: Any = Field(..., description="Policy expectation or baseline requirement")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Concrete proof and extraction context")
    recommendation: str = Field(..., description="Actionable remediation guidance")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Defensible confidence score")
    status: str = Field(default="OPEN", description="Finding lifecycle status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0")

    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class AssessmentSummary(BaseModel):
    """
    Consolidated operational assessment across inventory, FinOps, SecOps, and SRE dimensions.
    """
    assessment_id: str = Field(default_factory=lambda: f"asm-{uuid.uuid4().hex[:10]}")
    task_id: str
    workspace_root: str
    total_resources: int = 0
    total_findings: int = 0
    critical_findings_count: int = 0
    high_findings_count: int = 0
    medium_findings_count: int = 0
    low_findings_count: int = 0
    estimated_monthly_cost: str = Field(default="0.00", description="Decimal string for total estimated monthly cost")
    currency: str = Field(default="USD")
    finops_summary: str = ""
    secops_summary: str = ""
    reliability_summary: str = ""
    next_phase_recommendations: List[str] = Field(default_factory=list)
    status: str = Field(default="COMPLETED", description="Assessment state: COMPLETED, PARTIAL, FAILED")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0")

    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

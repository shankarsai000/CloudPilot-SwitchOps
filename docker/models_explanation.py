"""
Explainability Engine (M7-EXA) - Models

Defines the structure for decision explanations, evidence collection graphs,
confidence breakdowns, and audit trails.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ConfidenceBreakdown(BaseModel):
    """Detailed transparent breakdown of confidence score parameters."""

    infrastructure: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from Infrastructure Discovery M1 (weight: 30%)")
    application: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from Application boundaries M3 (weight: 25%)")
    simulation: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from Digital Twin Simulation M6 (weight: 20%)")
    history: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from historical deployment logs (weight: 15%)")
    policies: float = Field(..., ge=0.0, le=100.0, description="Confidence contribution from policy checklist matches (weight: 10%)")
    final_score: float = Field(..., ge=0.0, le=100.0, description="Final aggregate weighted score")


class EvidenceNode(BaseModel):
    """A single node representing an evidence parameter (CPU, compliance framework, etc.)."""

    id: str = Field(...)
    label: str = Field(...)
    source_module: str = Field(..., description="M1, M2, M3, M4, M5, or M6")
    value: str = Field(..., description="Stringified value or metric metric")


class EvidenceEdge(BaseModel):
    """Linkage showing how evidence supports a specific decision node."""

    source: str = Field(...)
    target: str = Field(...)
    weight: float = Field(default=1.0)


class EvidenceGraph(BaseModel):
    """Graph structure displaying supporting evidence chains."""

    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[EvidenceEdge] = Field(default_factory=list)


class ExplanationReport(BaseModel):
    """Aggregated natural language rationale justifying recommendation/simulation decisions."""

    decision_id: str = Field(..., description="The unique decision ID being explained")
    why_explanation: str = Field(..., description="Detailed paragraph explaining what should be done and why")
    why_now_explanation: str = Field(..., description="Explaining why now is the appropriate timing")
    why_strategy_explanation: str = Field(..., description="Why this strategy was picked over alternatives")
    why_not_alternatives: str = Field(..., description="Specifically why alternative strategy options were bypassed")
    evidence_summary: list[str] = Field(default_factory=list, description="Bullet points of concrete evidence metrics")
    supporting_metrics: dict[str, Any] = Field(default_factory=dict, description="Numerical backing parameters")
    confidence: ConfidenceBreakdown = Field(..., description="Detailed confidence parameters")


class AuditTrail(BaseModel):
    """Audit log tracking actors, operations, approvals, and outcomes."""

    audit_id: str = Field(..., description="Unique audit event entry ID")
    decision_id: str = Field(...)
    requested_by: str = Field(...)
    approved_by: Optional[str] = Field(None)
    executed_by: Optional[str] = Field(None)
    action: str = Field(...)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    outcome: str = Field(default="PENDING", description="SUCCESS, FAILED, PENDING, ROLLBACK")

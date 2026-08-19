"""
Risk Intelligence Agent - Pydantic Models for Risk

Defines the core risk categorization, scores, simulations, and assessment records.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class RiskCategory(str, Enum):
    """Categorization of operational risk levels."""

    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskScore(BaseModel):
    """Details of individual component risk scores contributing to the overall risk."""

    overall_score: float = Field(..., ge=0.0, le=100.0, description="Overall risk score (0-100)")
    infrastructure_health: float = Field(..., ge=0.0, le=100.0, description="Risk from resource health")
    dependency_complexity: float = Field(..., ge=0.0, le=100.0, description="Risk from dependency counts/cycles")
    business_impact: float = Field(..., ge=0.0, le=100.0, description="Risk of business/revenue damage")
    cost_correlation: float = Field(..., ge=0.0, le=100.0, description="Risk correlated with cost factors")
    compliance_violation: float = Field(..., ge=0.0, le=100.0, description="Risk from compliance/policy violations")
    history_score: float = Field(..., ge=0.0, le=100.0, description="Risk based on historical failures/events")


class ActionType(str, Enum):
    """Types of infrastructure changes that can be simulated."""

    TERMINATE = "TERMINATE"
    STOP = "STOP"
    START = "START"
    RESIZE = "RESIZE"
    RESTART = "RESTART"
    MODIFY_SECURITY_GROUP = "MODIFY_SECURITY_GROUP"
    DEPLOY = "DEPLOY"
    UNKNOWN = "UNKNOWN"


class SimulationRequest(BaseModel):
    """Request schema for simulating infrastructure changes."""

    target_id: str = Field(..., description="Resource ID or Application ID to apply change to")
    action: ActionType = Field(default=ActionType.TERMINATE, description="Infrastructure action type")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Additional parameters (e.g. resize_to='t3.large')")
    performed_by: Optional[str] = Field(None, description="Identifier of the operator/pipeline simulating the change")


class RiskAssessment(BaseModel):
    """Complete assessment report of the predicted impact of an action."""

    assessment_id: str = Field(..., description="Unique risk assessment ID")
    target_id: str = Field(..., description="Target resource or application ID")
    action: ActionType = Field(..., description="Action simulated")
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Calculated risk score")
    risk_category: RiskCategory = Field(..., description="Classified risk level")
    confidence_score: float = Field(..., ge=0.0, le=100.0, description="Engine confidence level (0-100%)")
    assessed_at: datetime = Field(default_factory=datetime.utcnow, description="Assessment timestamp")
    explanation: list[str] = Field(default_factory=list, description="Reasoning and evidence traces")
    policy_violations: list[str] = Field(default_factory=list, description="Violations of org policies")
    mitigations: list[str] = Field(default_factory=list, description="Actionable mitigation recommendations")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra context/metadata")


class SimulationResult(BaseModel):
    """Result of an infrastructure change simulation run."""

    simulation_id: str = Field(..., description="Unique simulation run identifier")
    request: SimulationRequest = Field(..., description="Original simulation request")
    assessment: RiskAssessment = Field(..., description="Calculated risk assessment")
    blast_radius: Any = Field(..., description="Calculated blast radius details")
    impact_graph: Any = Field(..., description="Impact propagation details")
    timeline: Any = Field(..., description="Temporal risk progression prediction")
    simulated_at: datetime = Field(default_factory=datetime.utcnow)


class RiskHistoryRecord(BaseModel):
    """Historical record stored in risk repository."""

    assessment_id: str = Field(...)
    target_id: str = Field(...)
    action: str = Field(...)
    risk_score: float = Field(...)
    risk_category: str = Field(...)
    confidence_score: float = Field(...)
    policy_violations: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)

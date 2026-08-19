"""
Organizational Intelligence & Continuous Learning Layer - Pydantic Models

Defines structures for learning events, Cloud DNA profiles, experience records,
feedback records, pattern records, knowledge graph entities, and learning metrics.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════


class EventType(str, Enum):
    """Types of events tracked in organizational memory."""

    INFRASTRUCTURE_CHANGE = "INFRASTRUCTURE_CHANGE"
    OPTIMIZATION = "OPTIMIZATION"
    DEPLOYMENT = "DEPLOYMENT"
    INCIDENT = "INCIDENT"
    ROLLBACK = "ROLLBACK"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    APPROVAL = "APPROVAL"
    REJECTION = "REJECTION"
    SCALING = "SCALING"
    COST_SPIKE = "COST_SPIKE"


class OutcomeType(str, Enum):
    """Outcome classification for tracked events."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"
    ROLLBACK = "ROLLBACK"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


class DeploymentStyle(str, Enum):
    """Organization deployment behavior classification."""

    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class RiskToleranceLevel(str, Enum):
    """Organization risk appetite classification."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ScalingPattern(str, Enum):
    """Organization scaling behavior classification."""

    REACTIVE = "REACTIVE"
    PREDICTIVE = "PREDICTIVE"
    MANUAL = "MANUAL"
    HYBRID = "HYBRID"


class PatternType(str, Enum):
    """Categories of detected recurring patterns."""

    COST_SPIKE = "COST_SPIKE"
    DEPLOYMENT_FAILURE = "DEPLOYMENT_FAILURE"
    SEASONAL_SCALING = "SEASONAL_SCALING"
    GROWTH_TREND = "GROWTH_TREND"
    RECURRING_OUTAGE = "RECURRING_OUTAGE"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"
    APPROVAL_DELAY = "APPROVAL_DELAY"


class FeedbackVerdict(str, Enum):
    """Human verdict on a recommendation."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    MODIFIED = "MODIFIED"


class KnowledgeNodeType(str, Enum):
    """Types of nodes in the knowledge graph."""

    INFRASTRUCTURE = "INFRASTRUCTURE"
    APPLICATION = "APPLICATION"
    DECISION = "DECISION"
    OUTCOME = "OUTCOME"
    INCIDENT = "INCIDENT"
    ENGINEER = "ENGINEER"
    POLICY = "POLICY"
    STRATEGY = "STRATEGY"


class KnowledgeEdgeType(str, Enum):
    """Types of edges in the knowledge graph."""

    DEPENDS_ON = "DEPENDS_ON"
    CAUSED = "CAUSED"
    RESOLVED_BY = "RESOLVED_BY"
    APPROVED_BY = "APPROVED_BY"
    OWNS = "OWNS"
    VIOLATED = "VIOLATED"
    PRODUCED = "PRODUCED"
    AFFECTED = "AFFECTED"


# ═══════════════════════════════════════════════════════════════
# Core Models
# ═══════════════════════════════════════════════════════════════


class LearningEvent(BaseModel):
    """Event sourcing record representing a single organizational event."""

    event_id: str = Field(..., description="Unique event identifier")
    event_type: EventType = Field(..., description="Classification of the event")
    target_id: str = Field(..., description="Resource or application affected")
    action: str = Field(..., description="Action performed")
    outcome: OutcomeType = Field(default=OutcomeType.PENDING, description="Result of the action")
    actor: str = Field(default="CloudPilot-System", description="Who or what initiated the event")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary event context")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CloudDNAProfile(BaseModel):
    """Organization-specific behavioral profile that evolves over time."""

    organization_id: str = Field(..., description="Organization identifier")
    deployment_style: DeploymentStyle = Field(default=DeploymentStyle.MODERATE)
    risk_tolerance: RiskToleranceLevel = Field(default=RiskToleranceLevel.MEDIUM)
    scaling_pattern: ScalingPattern = Field(default=ScalingPattern.REACTIVE)
    peak_hours: str = Field(default="09:00-17:00", description="Business peak hours")
    preferred_regions: list[str] = Field(default_factory=lambda: ["us-east-1"])
    average_approval_time_hours: float = Field(default=2.0, description="Average time to approve changes")
    rollback_frequency_percentage: float = Field(default=5.0, ge=0.0, le=100.0)
    automation_level_percentage: float = Field(default=50.0, ge=0.0, le=100.0)
    deployment_frequency_per_week: float = Field(default=5.0, ge=0.0)
    total_events_analyzed: int = Field(default=0, ge=0)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class ExperienceRecord(BaseModel):
    """Historical outcome record used for experience replay."""

    experience_id: str = Field(..., description="Unique experience identifier")
    context: dict[str, Any] = Field(..., description="Infrastructure and application context at decision time")
    decision: str = Field(..., description="Decision made")
    action: str = Field(..., description="Action executed")
    outcome: OutcomeType = Field(..., description="Outcome of the action")
    confidence_at_decision: float = Field(default=50.0, ge=0.0, le=100.0)
    actual_savings_usd: float = Field(default=0.0)
    similarity_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Relevance to a query context")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class FeedbackRecord(BaseModel):
    """Human feedback on a specific recommendation or decision."""

    feedback_id: str = Field(..., description="Unique feedback identifier")
    decision_id: str = Field(..., description="Decision being reviewed")
    source: str = Field(..., description="Who provided feedback (engineer, SRE, manager)")
    verdict: FeedbackVerdict = Field(..., description="Approval status")
    reason: str = Field(default="", description="Free-text explanation")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PatternRecord(BaseModel):
    """A detected recurring operational or business pattern."""

    pattern_id: str = Field(..., description="Unique pattern identifier")
    pattern_type: PatternType = Field(..., description="Classification of the pattern")
    frequency: int = Field(default=1, ge=1, description="Number of occurrences detected")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Detection confidence")
    description: str = Field(..., description="Human-readable description")
    affected_resources: list[str] = Field(default_factory=list)
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class KnowledgeNode(BaseModel):
    """A node in the organizational knowledge graph."""

    node_id: str = Field(..., description="Unique node identifier")
    node_type: KnowledgeNodeType = Field(..., description="Classification")
    label: str = Field(..., description="Human-readable label")
    properties: dict[str, Any] = Field(default_factory=dict)


class KnowledgeEdge(BaseModel):
    """A directed edge in the organizational knowledge graph."""

    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    edge_type: KnowledgeEdgeType = Field(..., description="Relationship type")
    weight: float = Field(default=1.0, ge=0.0)
    properties: dict[str, Any] = Field(default_factory=dict)


class LearningMetrics(BaseModel):
    """Continuous improvement KPI metrics."""

    recommendation_acceptance_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    execution_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    rollback_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    prediction_accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    simulation_accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_calibration: float = Field(default=0.0, ge=0.0, le=1.0)
    engineer_satisfaction: float = Field(default=0.0, ge=0.0, le=1.0)
    cost_savings_accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    incident_reduction_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    total_events_processed: int = Field(default=0, ge=0)
    total_feedback_collected: int = Field(default=0, ge=0)
    calculated_at: datetime = Field(default_factory=datetime.utcnow)

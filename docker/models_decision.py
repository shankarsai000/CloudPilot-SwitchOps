"""
Executive Decision Intelligence Layer - Pydantic Models

Defines structures for decision states, agent votes, consensus results,
decision scores, approval routes, policy compliance, execution packages,
decision records, and override records.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════


class DecisionState(str, Enum):
    """Possible states for a decision."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    AUTO_APPROVED = "AUTO_APPROVED"
    CONDITIONAL = "CONDITIONAL"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class VoteVerdict(str, Enum):
    """Individual module vote on a recommendation."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"
    CONDITIONAL = "CONDITIONAL"


class ApprovalLevel(str, Enum):
    """Approval routing destination."""

    AUTO_EXECUTE = "AUTO_EXECUTE"
    ENGINEERING_LEAD = "ENGINEERING_LEAD"
    SRE_TEAM = "SRE_TEAM"
    SECURITY_TEAM = "SECURITY_TEAM"
    EXECUTIVE_APPROVAL = "EXECUTIVE_APPROVAL"


class ConflictResolutionStrategy(str, Enum):
    """Strategy for resolving conflicting votes."""

    RISK_PRIORITY = "RISK_PRIORITY"
    COST_PRIORITY = "COST_PRIORITY"
    CONSERVATIVE = "CONSERVATIVE"
    MAJORITY_WINS = "MAJORITY_WINS"


class OverrideAction(str, Enum):
    """Human override action types."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    MODIFY = "MODIFY"
    DELAY = "DELAY"
    MANUAL_EXECUTION = "MANUAL_EXECUTION"


# ═══════════════════════════════════════════════════════════════
# Core Models
# ═══════════════════════════════════════════════════════════════


class AgentVote(BaseModel):
    """Individual intelligence module vote on a recommendation."""

    agent_name: str = Field(..., description="Module name (e.g. 'Infrastructure', 'Cost', 'Risk')")
    verdict: VoteVerdict = Field(..., description="Module recommendation")
    confidence: float = Field(default=50.0, ge=0.0, le=100.0, description="Module confidence in verdict")
    reasoning: str = Field(default="", description="Explanation for the vote")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Supporting numerical evidence")


class ConsensusResult(BaseModel):
    """Aggregated outcome from multi-agent voting."""

    votes: list[AgentVote] = Field(default_factory=list)
    approve_count: int = Field(default=0)
    reject_count: int = Field(default=0)
    abstain_count: int = Field(default=0)
    conditional_count: int = Field(default=0)
    consensus_type: str = Field(default="SPLIT", description="UNANIMOUS, MAJORITY, SPLIT, DEADLOCK")
    recommended_action: VoteVerdict = Field(default=VoteVerdict.ABSTAIN)


class DecisionScore(BaseModel):
    """Weighted composite decision score with component breakdown."""

    overall_score: float = Field(..., ge=0.0, le=100.0, description="Final composite score")
    business_value_score: float = Field(default=0.0, ge=0.0, le=100.0)
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    simulation_score: float = Field(default=0.0, ge=0.0, le=100.0)
    learning_score: float = Field(default=0.0, ge=0.0, le=100.0)
    roi_score: float = Field(default=0.0, ge=0.0, le=100.0)
    policy_score: float = Field(default=0.0, ge=0.0, le=100.0)
    confidence_score: float = Field(default=0.0, ge=0.0, le=100.0)
    weights_used: dict[str, float] = Field(default_factory=dict)


class ApprovalRoute(BaseModel):
    """Routing destination for a decision."""

    level: ApprovalLevel = Field(...)
    reason: str = Field(default="")
    risk_category: str = Field(default="LOW")
    estimated_savings_usd: float = Field(default=0.0)


class PolicyComplianceReport(BaseModel):
    """Results of policy validation checks."""

    is_compliant: bool = Field(default=True)
    violations: list[str] = Field(default_factory=list)
    checks_passed: list[str] = Field(default_factory=list)
    change_freeze_active: bool = Field(default=False)
    maintenance_window_ok: bool = Field(default=True)


class ExecutionPackage(BaseModel):
    """Complete package prepared for M10 execution."""

    package_id: str = Field(..., description="Unique package identifier")
    decision_id: str = Field(..., description="Associated decision ID")
    target_id: str = Field(..., description="Resource or application to act on")
    action: str = Field(..., description="Action to execute")
    strategy_summary: str = Field(default="")
    rollback_plan: dict[str, Any] = Field(default_factory=dict)
    simulation_summary: dict[str, Any] = Field(default_factory=dict)
    risk_summary: dict[str, Any] = Field(default_factory=dict)
    execution_steps: list[dict[str, Any]] = Field(default_factory=list)
    approval_metadata: dict[str, Any] = Field(default_factory=dict)
    estimated_duration_minutes: float = Field(default=5.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DecisionRecord(BaseModel):
    """Full decision audit record."""

    decision_id: str = Field(..., description="Unique decision identifier")
    target_id: str = Field(..., description="Resource or application evaluated")
    action: str = Field(..., description="Proposed action")
    state: DecisionState = Field(default=DecisionState.PENDING)
    consensus: ConsensusResult = Field(default_factory=ConsensusResult)
    score: Optional[DecisionScore] = Field(None)
    approval_route: Optional[ApprovalRoute] = Field(None)
    policy_report: Optional[PolicyComplianceReport] = Field(None)
    execution_package: Optional[ExecutionPackage] = Field(None)
    decision_confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    explanation: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    decided_at: Optional[datetime] = Field(None)


class OverrideRecord(BaseModel):
    """Human override log entry."""

    override_id: str = Field(..., description="Unique override identifier")
    decision_id: str = Field(..., description="Decision being overridden")
    action: OverrideAction = Field(...)
    actor: str = Field(..., description="Person performing the override")
    reason: str = Field(default="")
    original_state: DecisionState = Field(...)
    new_state: DecisionState = Field(...)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

"""
Strategic Decision Intelligence Layer - Pydantic Models for Strategy

Defines structures for candidates, ROI parameters, roadmaps, portfolios,
approval rules, and complete Optimization Plans.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class OptimizationCategory(str, Enum):
    """Broad categories for cloud infrastructure optimization."""

    COMPUTE = "COMPUTE"
    STORAGE = "STORAGE"
    NETWORKING = "NETWORKING"
    CONTAINERS = "CONTAINERS"
    DATABASES = "DATABASES"
    SERVERLESS = "SERVERLESS"
    KUBERNETES = "KUBERNETES"
    AUTOSCALING = "AUTOSCALING"
    SECURITY = "SECURITY"
    ARCHITECTURE = "ARCHITECTURE"
    GOVERNANCE = "GOVERNANCE"


class ApprovalLevel(str, Enum):
    """Categorization of deployment automation/approval levels."""

    AUTO_EXECUTE = "AUTO_EXECUTE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    EXECUTIVE_APPROVAL = "EXECUTIVE_APPROVAL"
    BLOCKED = "BLOCKED"


class ROIMetrics(BaseModel):
    """ROI financial and effort metrics for an optimization strategy."""

    expected_savings_monthly: float = Field(..., ge=0.0, description="Predicted monthly savings in USD")
    implementation_cost: float = Field(..., ge=0.0, description="Predicted cost of engineering effort/downtime in USD")
    engineering_hours: float = Field(..., ge=0.0, description="Estimated developer time required in hours")
    payback_period_days: float = Field(..., ge=0.0, description="Payback time in days")
    roi_score: float = Field(..., ge=0.0, description="Return on investment ratio score")


class CandidateStrategy(BaseModel):
    """Single candidate strategy representing one potential solution path."""

    strategy_id: str = Field(..., description="Unique strategy candidate ID")
    name: str = Field(..., description="Actionable name (e.g. Resize instances)")
    expected_savings_monthly: float = Field(..., ge=0.0, description="Expected monthly savings")
    risk_level: str = Field(..., description="Risk category: SAFE, LOW, MEDIUM, HIGH, CRITICAL")
    confidence_score: float = Field(..., ge=0.0, le=100.0, description="Confidence rating (0-100%)")
    description: str = Field(..., description="Detailed text explanation")


class Recommendation(BaseModel):
    """A synthesized recommendation grouping multiple candidate strategies."""

    recommendation_id: str = Field(..., description="Unique recommendation ID")
    target_id: str = Field(..., description="Affected Resource or Application ID")
    description: str = Field(..., description="Problem description")
    category: OptimizationCategory = Field(..., description="Optimization classification")
    recommended_strategy_name: str = Field(..., description="The chosen strategy name")
    candidates: list[CandidateStrategy] = Field(default_factory=list, description="Alternative strategy options")
    roi: ROIMetrics = Field(..., description="Calculated ROI details of recommended strategy")
    risk_category: str = Field(..., description="M4 Risk Level of recommended strategy")
    confidence_score: float = Field(..., ge=0.0, le=100.0, description="M4 confidence level")
    complexity: str = Field(..., description="Complexity details (LOW, MEDIUM, HIGH)")
    priority_score: float = Field(..., ge=0.0, le=100.0, description="Calculated priority score")
    approval_level: ApprovalLevel = Field(..., description="Authorized approval workflow")
    explanation: list[str] = Field(default_factory=list, description="Architect rationale explainers")


class OptimizationPlan(BaseModel):
    """Structured Optimization Plan — the primary M5 output standard.

    Every strategy outputs this plan containing summaries, candidate lists,
    trade-off details, and blueprints.
    """

    plan_id: str = Field(..., description="Unique plan ID")
    executive_summary: str = Field(..., description="High-level Principal Architect summary")
    current_state: str = Field(..., description="Current running infrastructure status")
    problem_statement: str = Field(..., description="What is inefficient and why")
    candidate_strategies: list[CandidateStrategy] = Field(default_factory=list)
    trade_off_analysis: str = Field(..., description="Details comparing options")
    recommended_strategy: CandidateStrategy = Field(..., description="Recommended strategy details")
    expected_savings_monthly: float = Field(..., ge=0.0)
    risk_assessment: dict[str, Any] = Field(default_factory=dict, description="Risk report mappings (from M4)")
    roi_analysis: ROIMetrics = Field(...)
    execution_blueprint: list[dict[str, Any]] = Field(default_factory=list, description="Phased execution instructions for M10")
    success_metrics: list[str] = Field(default_factory=list, description="Validation checkpoints to confirm success")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RoadmapPhase(BaseModel):
    """A single phase in a chronological roadmap."""

    phase_name: str = Field(..., description="e.g. Week 1: Compute")
    timeline: str = Field(..., description="Time marker (e.g. Week 1)")
    plans: list[OptimizationPlan] = Field(default_factory=list)
    dependency_blueprint: list[str] = Field(default_factory=list)


class StrategyPortfolio(BaseModel):
    """Recommendation portfolio organizing plans into priority buckets."""

    immediate_wins: list[OptimizationPlan] = Field(default_factory=list)
    medium_term_wins: list[OptimizationPlan] = Field(default_factory=list)
    long_term_architecture: list[OptimizationPlan] = Field(default_factory=list)
    technical_debt: list[OptimizationPlan] = Field(default_factory=list)
    operational_improvements: list[OptimizationPlan] = Field(default_factory=list)


class ScenarioParameter(BaseModel):
    """Scenario conditions for what-if simulation runs."""

    gpu_demand_multiplier: float = Field(default=1.0)
    traffic_drop_percentage: float = Field(default=0.0)
    add_new_region: Optional[str] = Field(None)
    k8s_failure_simulation: bool = Field(default=False)
    purchase_reserved_instances: bool = Field(default=False)

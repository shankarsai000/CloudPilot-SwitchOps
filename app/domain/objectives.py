"""
CloudPilot SwitchOps — Multi-Objective Evaluation Models

Defines the 4-dimensional objective scoring contracts:
1. Cost (normalized 0-100, higher = greater relative savings / lower spend)
2. Security (normalized 0-100, higher = higher security posture improvement)
3. Reliability (normalized 0-100, higher = improved resilience and recovery)
4. Operational Simplicity (normalized 0-100, higher = lower friction / lower risk)
"""

from __future__ import annotations

from enum import Enum
from decimal import Decimal
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ObjectiveDimension(str, Enum):
    """The four core evaluation dimensions of CloudPilot SwitchOps."""
    COST = "COST"
    SECURITY = "SECURITY"
    RELIABILITY = "RELIABILITY"
    SIMPLICITY = "SIMPLICITY"


class PreferenceProfile(str, Enum):
    """Operator preference profile used strictly for ranking feasible Pareto candidates."""
    BALANCED = "BALANCED"
    COST_FIRST = "COST_FIRST"
    SECURITY_FIRST = "SECURITY_FIRST"
    RELIABILITY_FIRST = "RELIABILITY_FIRST"


class ObjectiveScores(BaseModel):
    """
    Normalized multi-objective scores for a single candidate or change plan.
    All scores are bounded in [0.0, 100.0] with consistent directionality:
    HIGHER SCORE ALWAYS MEANS A BETTER ENGINEERING OUTCOME.
    """
    cost_score: float = Field(..., ge=0.0, le=100.0, description="Cost efficiency score (0=no savings, 100=max savings)")
    security_score: float = Field(..., ge=0.0, le=100.0, description="Security improvement score (0=no improvement/worse, 100=max fix)")
    reliability_score: float = Field(..., ge=0.0, le=100.0, description="Reliability score (0=no improvement/worse, 100=max resilience)")
    simplicity_score: float = Field(..., ge=0.0, le=100.0, description="Operational ease (100=low complexity, 60=medium, 20=high)")
    uncertainty_penalty: float = Field(default=0.0, ge=0.0, le=50.0, description="Score reduction applied for unverified assumptions")
    cost_savings_amount: Optional[Decimal] = Field(default=None, description="Exact Decimal monetary savings in USD")
    raw_metrics: Dict[str, str] = Field(default_factory=dict, description="Underlying raw metrics (e.g. savings_usd, complexity)")
    model_version: str = Field(default="1.0")

    @property
    def vector(self) -> tuple[float, float, float, float]:
        """Returns the 4D objective vector for dominance comparison."""
        return (self.cost_score, self.security_score, self.reliability_score, self.simplicity_score)

    def dominates(self, other: ObjectiveScores, tolerance: float = 1e-6) -> bool:
        """
        True Pareto Dominance: self dominates other iff:
        self is at least as good as other in all dimensions, AND
        self is strictly better than other in at least one dimension.
        """
        s_v = self.vector
        o_v = other.vector

        at_least_as_good = all(s >= o - tolerance for s, o in zip(s_v, o_v))
        strictly_better = any(s > o + tolerance for s, o in zip(s_v, o_v))

        return at_least_as_good and strictly_better


# Default weights applied for ranking among the non-dominated Pareto frontier
PREFERENCE_WEIGHTS: Dict[PreferenceProfile, Dict[ObjectiveDimension, float]] = {
    PreferenceProfile.BALANCED: {
        ObjectiveDimension.COST: 0.30,
        ObjectiveDimension.SECURITY: 0.30,
        ObjectiveDimension.RELIABILITY: 0.25,
        ObjectiveDimension.SIMPLICITY: 0.15,
    },
    PreferenceProfile.COST_FIRST: {
        ObjectiveDimension.COST: 0.60,
        ObjectiveDimension.SECURITY: 0.15,
        ObjectiveDimension.RELIABILITY: 0.15,
        ObjectiveDimension.SIMPLICITY: 0.10,
    },
    PreferenceProfile.SECURITY_FIRST: {
        ObjectiveDimension.COST: 0.10,
        ObjectiveDimension.SECURITY: 0.60,
        ObjectiveDimension.RELIABILITY: 0.20,
        ObjectiveDimension.SIMPLICITY: 0.10,
    },
    PreferenceProfile.RELIABILITY_FIRST: {
        ObjectiveDimension.COST: 0.15,
        ObjectiveDimension.SECURITY: 0.15,
        ObjectiveDimension.RELIABILITY: 0.55,
        ObjectiveDimension.SIMPLICITY: 0.15,
    },
}

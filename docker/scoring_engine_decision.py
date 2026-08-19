"""
Scoring Engine (Decision) Component

Configurable weighted scoring combining Business Value, Risk, Simulation,
Learning, ROI, Policies, and Confidence into a composite decision score.
"""

from __future__ import annotations

import logging
from typing import Any

from models_decision import DecisionScore

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "business_value": 0.25,
    "risk": 0.25,
    "simulation": 0.15,
    "learning": 0.15,
    "roi": 0.10,
    "policies": 0.05,
    "confidence": 0.05,
}


class ScoringEngineDecision:
    """Produces weighted composite decision scores."""

    def __init__(self, weights: dict[str, float] = None) -> None:
        """Initialize Scoring Engine with configurable weights.

        Args:
            weights: Dict of component -> weight (must sum to ~1.0)
        """
        self.weights = weights or dict(DEFAULT_WEIGHTS)

    def calculate_score(
        self,
        business_value: float = 50.0,
        risk: float = 50.0,
        simulation: float = 50.0,
        learning: float = 50.0,
        roi: float = 50.0,
        policies: float = 50.0,
        confidence: float = 50.0,
    ) -> DecisionScore:
        """Calculate the weighted composite decision score.

        All inputs are 0-100 scales. For risk, higher means *safer* (inverted).

        Args:
            business_value: Business value score (0-100)
            risk: Risk safety score (0-100, higher = safer)
            simulation: Simulation safety score (0-100)
            learning: Historical success score (0-100)
            roi: ROI score (0-100)
            policies: Policy compliance score (0-100)
            confidence: Aggregate confidence score (0-100)

        Returns:
            DecisionScore with component breakdown
        """
        overall = (
            business_value * self.weights.get("business_value", 0.0)
            + risk * self.weights.get("risk", 0.0)
            + simulation * self.weights.get("simulation", 0.0)
            + learning * self.weights.get("learning", 0.0)
            + roi * self.weights.get("roi", 0.0)
            + policies * self.weights.get("policies", 0.0)
            + confidence * self.weights.get("confidence", 0.0)
        )

        overall = max(min(overall, 100.0), 0.0)

        return DecisionScore(
            overall_score=round(overall, 2),
            business_value_score=round(business_value, 2),
            risk_score=round(risk, 2),
            simulation_score=round(simulation, 2),
            learning_score=round(learning, 2),
            roi_score=round(roi, 2),
            policy_score=round(policies, 2),
            confidence_score=round(confidence, 2),
            weights_used=dict(self.weights),
        )

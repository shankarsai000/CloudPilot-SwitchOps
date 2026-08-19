"""
Recommendation Optimizer Component

Evolves confidence scores based on accumulated execution outcomes.
Uses Bayesian-style updating: as successes accumulate, confidence rises;
failures pull it down.
"""

from __future__ import annotations

import logging
from typing import Any

from models_learning import OutcomeType

logger = logging.getLogger(__name__)


class RecommendationOptimizer:
    """Evolves recommendation confidence based on historical execution outcomes."""

    def __init__(self, prior_alpha: float = 2.0, prior_beta: float = 2.0) -> None:
        """Initialize Recommendation Optimizer with Beta-distribution priors.

        Args:
            prior_alpha: Prior success count (pseudo-observations)
            prior_beta: Prior failure count (pseudo-observations)
        """
        self._alpha = prior_alpha
        self._beta = prior_beta
        # Per-action trackers: action -> (successes, failures)
        self._action_stats: dict[str, tuple[int, int]] = {}

    def record_outcome(self, action: str, outcome: OutcomeType) -> None:
        """Record an execution outcome for a given action type.

        Args:
            action: Action type
            outcome: Execution outcome
        """
        s, f = self._action_stats.get(action, (0, 0))
        if outcome == OutcomeType.SUCCESS:
            s += 1
        elif outcome in (OutcomeType.FAILURE, OutcomeType.ROLLBACK):
            f += 1
        self._action_stats[action] = (s, f)

    def get_evolved_confidence(self, action: str, base_confidence: float = 50.0) -> float:
        """Calculate the evolved confidence score for an action type.

        Uses the Beta distribution mean: alpha / (alpha + beta) where
        alpha = prior_alpha + successes and beta = prior_beta + failures.

        Args:
            action: Action type
            base_confidence: Original static confidence (used as a floor anchor)

        Returns:
            Evolved confidence score between 0.0 and 100.0
        """
        s, f = self._action_stats.get(action, (0, 0))
        alpha = self._alpha + s
        beta = self._beta + f

        bayesian_confidence = (alpha / (alpha + beta)) * 100.0

        # Blend with base confidence, giving more weight to data as observations grow
        total_observations = s + f
        data_weight = min(total_observations / (total_observations + 10.0), 0.9)
        blended = (data_weight * bayesian_confidence) + ((1.0 - data_weight) * base_confidence)

        return round(min(max(blended, 0.0), 100.0), 2)

    def get_action_stats(self, action: str) -> dict[str, Any]:
        """Get raw success/failure statistics for an action.

        Args:
            action: Action type

        Returns:
            Dict with successes, failures, and evolved confidence
        """
        s, f = self._action_stats.get(action, (0, 0))
        return {
            "action": action,
            "successes": s,
            "failures": f,
            "evolved_confidence": self.get_evolved_confidence(action),
        }

    def get_all_stats(self) -> list[dict[str, Any]]:
        """Get statistics for all tracked actions.

        Returns:
            List of stats dicts
        """
        return [self.get_action_stats(action) for action in self._action_stats]

    def bulk_ingest_outcomes(self, outcomes: list[tuple[str, OutcomeType]]) -> None:
        """Ingest multiple outcomes at once.

        Args:
            outcomes: List of (action, outcome) tuples
        """
        for action, outcome in outcomes:
            self.record_outcome(action, outcome)

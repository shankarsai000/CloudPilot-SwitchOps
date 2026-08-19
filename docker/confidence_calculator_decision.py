"""
Confidence Calculator (Decision) Component

Aggregates confidence scores from all intelligence modules into a single
decision-level confidence score.
"""

from __future__ import annotations

import logging
from typing import Any

from models_decision import AgentVote

logger = logging.getLogger(__name__)


class ConfidenceCalculatorDecision:
    """Aggregates module confidence scores into a single decision confidence."""

    def __init__(self) -> None:
        """Initialize Confidence Calculator."""
        pass

    def calculate(self, votes: list[AgentVote]) -> float:
        """Calculate aggregate decision confidence from module votes.

        Uses weighted average where higher-confidence modules contribute more.

        Args:
            votes: List of AgentVote from each module

        Returns:
            Aggregate confidence score (0-100)
        """
        if not votes:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for vote in votes:
            # Weight each module's confidence by itself (self-weighted average)
            weight = vote.confidence / 100.0  # normalize to 0-1
            weighted_sum += vote.confidence * weight
            total_weight += weight

        if total_weight == 0.0:
            return 0.0

        result = weighted_sum / total_weight
        return round(min(max(result, 0.0), 100.0), 2)

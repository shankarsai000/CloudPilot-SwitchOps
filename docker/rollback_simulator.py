"""
Rollback Simulator Component

Predicts the duration, complexity, probability, and confidence of recovery configurations.
"""

from __future__ import annotations

import logging
from typing import Any
from models_simulation import RollbackReport

logger = logging.getLogger(__name__)


class RollbackSimulator:
    """Simulates rollback durations and recovery probability details."""

    def __init__(self) -> None:
        """Initialize Rollback Simulator."""
        pass

    def simulate_rollback(
        self,
        target_id: str,
        action: str,
        twin_context: Any
    ) -> RollbackReport:
        """Estimate rollback metrics.

        Args:
            target_id: Target ID
            action: Action simulated
            twin_context: Twin context

        Returns:
            RollbackReport object
        """
        # Default low-risk metrics
        duration = 5.0
        complexity = "LOW"
        probability = 5.0
        confidence = 98.0

        # Adjust based on target action
        if action == "TERMINATE":
            duration = 35.0
            complexity = "HIGH"
            probability = 40.0
            confidence = 75.0  # harder to revert deletion

        elif action == "STOP":
            duration = 10.0
            complexity = "LOW"
            probability = 15.0
            confidence = 95.0  # easy to start back up

        elif action == "RESIZE":
            duration = 15.0
            complexity = "MEDIUM"
            probability = 10.0
            confidence = 90.0

        return RollbackReport(
            rollback_duration_minutes=duration,
            rollback_complexity=complexity,
            rollback_probability_percentage=probability,
            recovery_confidence_percentage=confidence
        )

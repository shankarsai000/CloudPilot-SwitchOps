"""
Execution Readiness Component

Computes an execution readiness score (0-100) based on safety checkpoints, policy checks, and rollback reports.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ExecutionReadinessEvaluator:
    """Evaluates whether a change can proceed to execution agent pipeline steps."""

    def __init__(self) -> None:
        """Initialize Execution Readiness."""
        pass

    def evaluate_readiness(
        self,
        target_id: str,
        safety_score: float,
        policy_violations: list[str],
        rollback_confidence: float
    ) -> float:
        """Calculate numerical execution readiness score.

        Args:
            target_id: Resource/Application ID
            safety_score: Calculated safety score
            policy_violations: Active policy violations
            rollback_confidence: Estimated recovery confidence

        Returns:
            Readiness score float (0-100)
        """
        readiness = 100.0

        # Adjust based on safety score
        readiness -= (100.0 - safety_score) * 0.4

        # Deduct heavily for policy violations
        if policy_violations:
            # Check for blocked keywords
            is_blocked = any("BLOCKED" in v or "CRITICAL" in v for v in policy_violations)
            if is_blocked:
                return 0.0  # blocked changes have 0 readiness
            readiness -= len(policy_violations) * 20.0

        # Incorporate rollback confidence
        readiness -= (100.0 - rollback_confidence) * 0.2

        return max(min(readiness, 100.0), 0.0)

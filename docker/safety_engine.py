"""
Safety Engine Component

Calculates simulation safety scores (0-100) and classifies them into:
- Safe, Unsafe, or Requires Approval.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SafetyEngine:
    """Evaluates the composite safety score and status of optimization plans."""

    def __init__(self) -> None:
        """Initialize Safety Engine."""
        pass

    def calculate_safety_score(
        self,
        target_id: str,
        action: str,
        cascading_failures: list[str],
        performance_forecast: Any,
        policy_violations: list[str]
    ) -> tuple[float, str]:
        """Compute safety score and status category.

        Args:
            target_id: Resource/Application ID
            action: Action simulated
            cascading_failures: Mapped cascade events list
            performance_forecast: Predicted performance metrics
            policy_violations: List of policy violations

        Returns:
            Tuple of (safety_score, safety_status)
        """
        score = 95.0  # start with maximum safety

        # 1. Action type deduction
        if action in ("TERMINATE", "DELETE"):
            score -= 25.0
        elif action == "STOP":
            score -= 15.0
        elif action == "RESIZE":
            score -= 10.0

        # 2. Performance forecasts degradation
        availability = performance_forecast.availability_percentage
        if availability < 95.0:
            score -= 20.0
        elif availability < 99.0:
            score -= 10.0

        # 3. Cascading failures deduction
        if len(cascading_failures) > 2:
            score -= 30.0

        # 4. Policy violations penalty
        if policy_violations:
            score -= 40.0

        # Bound score between 0 and 100
        score = max(min(score, 100.0), 0.0)

        # Map to category status
        if score >= 80.0:
            status = "Safe"
        elif score >= 40.0:
            status = "Requires Approval"
        else:
            status = "Unsafe"

        return score, status
class SimulationScoreEvaluator(SafetyEngine):
    """Alias for SafetyEngine to support potential naming alternatives."""
    pass

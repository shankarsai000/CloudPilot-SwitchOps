"""
Risk Classifier Component

Classifies numerical risk scores into qualitative RiskCategory enums.
Evaluates resource health, availability, and redundancy checks.
"""

from __future__ import annotations

import logging
from models_risk import RiskCategory
from models_resource import CloudResource, ResourceState

logger = logging.getLogger(__name__)


class RiskClassifier:
    """Classifies risk scores and evaluates technical/infrastructure resilience risks."""

    def __init__(self) -> None:
        """Initialize Risk Classifier."""
        pass

    def classify_score(self, score: float) -> RiskCategory:
        """Classify a numerical risk score (0-100) into a RiskCategory.

        Args:
            score: Risk score from 0 to 100

        Returns:
            Corresponding RiskCategory enum value
        """
        if score < 20.0:
            return RiskCategory.SAFE
        elif score < 40.0:
            return RiskCategory.LOW
        elif score < 60.0:
            return RiskCategory.MEDIUM
        elif score < 80.0:
            return RiskCategory.HIGH
        else:
            return RiskCategory.CRITICAL

    def evaluate_redundancy_and_health(
        self, resource: CloudResource, all_resources: list[CloudResource]
    ) -> dict[str, Any]:
        """Evaluate resource redundancy (SPOF checks) and health status.

        Args:
            resource: Resource being analyzed
            all_resources: List of all discovered resources for context

        Returns:
            Dict containing redundancy details and failure probability
        """
        has_redundancy = False
        is_spof = True
        failure_prob = 10.0  # default base probability in percentage

        # Check if other resources of the same type/role exist in the same environment/app group
        resource_app = resource.tags.get("app") or resource.tags.get("application")
        if resource_app:
            siblings = [
                r for r in all_resources
                if r.id != resource.id and
                (r.tags.get("app") == resource_app or r.tags.get("application") == resource_app) and
                r.type == resource.type
            ]
            if len(siblings) > 0:
                has_redundancy = True
                is_spof = False
                failure_prob = 2.0  # redundancy lowers failure probability

        # If resource state is not running/available, increase failure probability
        if resource.state not in (ResourceState.RUNNING, ResourceState.AVAILABLE):
            failure_prob += 50.0
            if failure_prob > 100.0:
                failure_prob = 100.0

        return {
            "has_redundancy": has_redundancy,
            "is_spof": is_spof,
            "failure_probability": failure_prob,
            "state_health_risk": 0.0 if resource.state in (ResourceState.RUNNING, ResourceState.AVAILABLE) else 40.0
        }

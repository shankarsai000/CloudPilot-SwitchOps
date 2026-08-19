"""
Priority Engine Component

Computes weighted prioritization scores (0-100) based on configurable scoring metrics.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PriorityEngine:
    """Calculates weighted priority rankings for optimization proposals."""

    def __init__(self, weights: dict[str, float] = None) -> None:
        """Initialize Priority Engine.

        Args:
            weights: Configuration overrides (must sum to 1.0)
        """
        self.weights = weights or {
            "roi": 0.30,
            "risk": 0.25,
            "business_value": 0.20,
            "confidence": 0.15,
            "complexity": 0.10
        }
        logger.info("PriorityEngine initialized with weights: %s", self.weights)

    def calculate_priority(
        self,
        roi_score: float,
        risk_category: str,
        confidence_score: float,
        complexity: str,
        business_criticality_score: float = 50.0
    ) -> float:
        """Compute the composite priority score (0-100) using configurable weights.

        Args:
            roi_score: ROI ratio score
            risk_category: qualitative Risk category
            confidence_score: Confidence level (0-100)
            complexity: Complexity label
            business_criticality_score: Application criticality score (0-100)

        Returns:
            Priority score float between 0 and 100
        """
        # 1. ROI Score mapping (capped at 100.0)
        roi_term = min(roi_score * 5.0, 100.0)

        # 2. Risk mapping (lower risk gives higher priority)
        risk_mapping = {
            "SAFE": 100.0,
            "LOW": 80.0,
            "MEDIUM": 50.0,
            "HIGH": 20.0,
            "CRITICAL": 0.0
        }
        risk_term = risk_mapping.get(risk_category.upper(), 50.0)

        # 3. Business Value mapping
        # Higher criticality application optimization is worth more business value
        # But conversely, optimizing less critical things is safer.
        # Let's map business value to a combination of criticality & savings potential
        biz_term = business_criticality_score

        # 4. Confidence mapping (0-100)
        conf_term = confidence_score

        # 5. Complexity mapping (lower complexity gives higher priority)
        comp_mapping = {
            "LOW": 100.0,
            "MEDIUM": 60.0,
            "HIGH": 20.0
        }
        comp_term = comp_mapping.get(complexity.upper(), 50.0)

        # Sum terms
        total = (
            (roi_term * self.weights.get("roi", 0.30))
            + (risk_term * self.weights.get("risk", 0.25))
            + (biz_term * self.weights.get("business_value", 0.20))
            + (conf_term * self.weights.get("confidence", 0.15))
            + (comp_term * self.weights.get("complexity", 0.10))
        )

        return min(max(total, 0.0), 100.0)

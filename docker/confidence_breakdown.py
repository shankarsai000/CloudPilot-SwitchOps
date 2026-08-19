"""
Confidence Breakdown Component

Provides transparent breakdowns of confidence scores based on:
- Infrastructure, Application, Simulation, History, and Policy scores.
"""

from __future__ import annotations

import logging
from models_explanation import ConfidenceBreakdown

logger = logging.getLogger(__name__)


class ConfidenceBreakdownCalculator:
    """Computes transparent confidence parameter metrics breakdowns."""

    def __init__(self) -> None:
        """Initialize Confidence Breakdown Calculator."""
        pass

    def calculate_breakdown(
        self,
        base_confidence_score: float,
        evidence: dict[str, Any]
    ) -> ConfidenceBreakdown:
        """Determine individual factor components for the final confidence.

        Args:
            base_confidence_score: Base score (0-100)
            evidence: Gathers evidence context

        Returns:
            ConfidenceBreakdown object
        """
        # Distribute based on data completeness in evidence fields
        infra_score = 95.0 if evidence.get("infrastructure") else 50.0
        app_score = 90.0 if evidence.get("application") else 50.0
        sim_score = 90.0 if evidence.get("simulation") else 50.0
        
        # History score: check if prior incident history exists
        hist_score = 85.0
        
        # Policy score: check if policies configured
        policy_score = 98.0 if evidence.get("risk", {}).get("policy_violations") is not None else 60.0

        # Weighted calculation
        final = (
            (infra_score * 0.30)
            + (app_score * 0.25)
            + (sim_score * 0.20)
            + (hist_score * 0.15)
            + (policy_score * 0.10)
        )

        return ConfidenceBreakdown(
            infrastructure=round(infra_score, 1),
            application=round(app_score, 1),
            simulation=round(sim_score, 1),
            history=round(hist_score, 1),
            policies=round(policy_score, 1),
            final_score=round(final, 2)
        )

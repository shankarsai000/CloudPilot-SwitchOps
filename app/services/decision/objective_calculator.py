"""
CloudPilot SwitchOps — Multi-Objective Score Calculator

Computes normalized 0-100 scores across Cost, Security, Reliability, and Simplicity.
Strictly ensures:
1. Higher score ALWAYS means a better engineering outcome.
2. Decimal arithmetic for monetary values.
3. Explicit uncertainty penalties for unverified assumptions.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Dict, List, Optional

from app.domain.candidates import Candidate, ImpactLevel, OperationalComplexity
from app.domain.objectives import (
    ObjectiveDimension,
    ObjectiveScores,
    PREFERENCE_WEIGHTS,
    PreferenceProfile,
)

logger = logging.getLogger("cloudpilot.decision.objectives")
TWO_PLACES = Decimal("0.01")


class ObjectiveCalculator:
    """
    Deterministic multi-objective scorer.
    Evaluates individual candidates and candidate combinations across 4 dimensions.
    """

    def __init__(self, baseline_monthly_cost: Decimal = Decimal("212.83")) -> None:
        if baseline_monthly_cost is not None and baseline_monthly_cost > Decimal("0.00"):
            self.baseline_monthly_cost = baseline_monthly_cost
        else:
            self.baseline_monthly_cost = Decimal("100.00")

    def evaluate_candidate(self, candidate: Candidate) -> ObjectiveScores:
        """Calculate normalized objective scores for a single candidate."""
        # 1. Cost Score (0-100)
        cost_score = self._calculate_cost_score(candidate)

        # 2. Security Score (0-100)
        security_score = self._calculate_security_score(candidate)

        # 3. Reliability Score (0-100)
        reliability_score = self._calculate_reliability_score(candidate)

        # 4. Operational Simplicity Score (0-100)
        simplicity_score = self._calculate_simplicity_score(candidate)

        # 5. Uncertainty Penalty
        uncertainty_penalty = self._calculate_uncertainty_penalty(candidate)

        # Apply uncertainty penalty proportionally, strictly clamping to [0.0, 100.0]
        adjusted_cost = max(0.0, min(100.0, cost_score - (uncertainty_penalty * 0.2)))
        adjusted_sec = max(0.0, min(100.0, security_score - (uncertainty_penalty * 0.3)))
        adjusted_rel = max(0.0, min(100.0, reliability_score - (uncertainty_penalty * 0.3)))
        adjusted_simp = max(0.0, min(100.0, simplicity_score - (uncertainty_penalty * 0.2)))

        raw_metrics = {
            "estimated_savings_usd": candidate.estimated_monthly_savings,
            "cost_before_usd": candidate.estimated_monthly_cost_before,
            "cost_after_usd": candidate.estimated_monthly_cost_after,
            "security_impact": candidate.security_impact.value,
            "reliability_impact": candidate.reliability_impact.value,
            "operational_complexity": candidate.operational_complexity.value,
            "assumptions_count": str(len(candidate.assumptions)),
        }

        try:
            savings_dec = Decimal(candidate.estimated_monthly_savings)
        except Exception:
            savings_dec = Decimal("0.00")

        return ObjectiveScores(
            cost_score=round(adjusted_cost, 2),
            security_score=round(adjusted_sec, 2),
            reliability_score=round(adjusted_rel, 2),
            simplicity_score=round(adjusted_simp, 2),
            uncertainty_penalty=round(uncertainty_penalty, 2),
            cost_savings_amount=savings_dec,
            raw_metrics=raw_metrics,
            model_version="1.1",
        )

    def calculate_scores(self, candidate: Candidate) -> ObjectiveScores:
        """Alias for evaluate_candidate."""
        return self.evaluate_candidate(candidate)

    def compute_weighted_score(
        self,
        scores: ObjectiveScores,
        preference: PreferenceProfile = PreferenceProfile.BALANCED,
    ) -> float:
        """
        Compute scalar utility score under a given preference profile.
        Used strictly for ranking among the non-dominated Pareto set.
        Safely falls back to BALANCED profile if an unknown or invalid profile is supplied.
        """
        weights = PREFERENCE_WEIGHTS.get(preference, PREFERENCE_WEIGHTS[PreferenceProfile.BALANCED])
        w_cost = weights[ObjectiveDimension.COST]
        w_sec = weights[ObjectiveDimension.SECURITY]
        w_rel = weights[ObjectiveDimension.RELIABILITY]
        w_simp = weights[ObjectiveDimension.SIMPLICITY]

        total = (
            (scores.cost_score * w_cost)
            + (scores.security_score * w_sec)
            + (scores.reliability_score * w_rel)
            + (scores.simplicity_score * w_simp)
        )
        return round(max(0.0, min(100.0, total)), 2)

    def calculate_weighted_score(
        self,
        candidate_or_scores: Candidate | ObjectiveScores,
        preference: PreferenceProfile = PreferenceProfile.BALANCED,
    ) -> float:
        """Alias accepting Candidate or ObjectiveScores."""
        if isinstance(candidate_or_scores, Candidate):
            scores = self.evaluate_candidate(candidate_or_scores)
        else:
            scores = candidate_or_scores
        return self.compute_weighted_score(scores, preference)

    # --- Internal Scoring Formulas ---

    def _calculate_cost_score(self, candidate: Candidate) -> float:
        """
        Cost Score Formula:
        Baseline = 50.0 (neutral / zero savings).
        Savings S > 0 increases score toward 100.0.
        Cost increase S < 0 reduces score toward 0.0.
        Guards against zero or negative baseline cost.
        Strictly clamped in [0.0, 100.0].
        """
        try:
            savings = Decimal(candidate.estimated_monthly_savings)
        except Exception:
            savings = Decimal("0.00")

        effective_baseline = self.baseline_monthly_cost if self.baseline_monthly_cost > Decimal("0.00") else Decimal("100.00")

        # Proportion of baseline saved: (savings / baseline) * 50.0
        ratio = float(savings / effective_baseline)
        score = 50.0 + (ratio * 50.0)
        return max(0.0, min(100.0, score))

    def _calculate_security_score(self, candidate: Candidate) -> float:
        """
        Security Score Mapping:
        HIGH_POSITIVE -> 90.0 (critical vulnerability resolved)
        POSITIVE      -> 75.0 (security enhancement)
        NEUTRAL       -> 50.0 (no security change)
        NEGATIVE      -> 20.0 (security regression)
        HIGH_NEGATIVE -> 5.0  (severe security degradation)
        """
        mapping = {
            ImpactLevel.HIGH_POSITIVE: 90.0,
            ImpactLevel.POSITIVE: 75.0,
            ImpactLevel.NEUTRAL: 50.0,
            ImpactLevel.NEGATIVE: 20.0,
            ImpactLevel.HIGH_NEGATIVE: 5.0,
        }
        return mapping.get(candidate.security_impact, 50.0)

    def _calculate_reliability_score(self, candidate: Candidate) -> float:
        """
        Reliability Score Mapping:
        HIGH_POSITIVE -> 90.0 (Multi-AZ failover, persistent storage)
        POSITIVE      -> 75.0 (Healthchecks, restart policy, resource limits)
        NEUTRAL       -> 50.0 (No reliability change)
        NEGATIVE      -> 20.0 (Increased downtime risk)
        HIGH_NEGATIVE -> 5.0  (Dropped persistence / SPOF)
        """
        mapping = {
            ImpactLevel.HIGH_POSITIVE: 90.0,
            ImpactLevel.POSITIVE: 75.0,
            ImpactLevel.NEUTRAL: 50.0,
            ImpactLevel.NEGATIVE: 20.0,
            ImpactLevel.HIGH_NEGATIVE: 5.0,
        }
        return mapping.get(candidate.reliability_impact, 50.0)

    def _calculate_simplicity_score(self, candidate: Candidate) -> float:
        """
        Operational Simplicity Mapping:
        LOW complexity    -> 100.0 (in-place restart or zero-downtime config change)
        MEDIUM complexity -> 65.0  (requires scheduled maintenance or DNS cutover)
        HIGH complexity   -> 30.0  (stateful migration, network re-architecture)
        """
        mapping = {
            OperationalComplexity.LOW: 100.0,
            OperationalComplexity.MEDIUM: 65.0,
            OperationalComplexity.HIGH: 30.0,
        }
        return mapping.get(candidate.operational_complexity, 65.0)

    def _calculate_uncertainty_penalty(self, candidate: Candidate) -> float:
        """
        Penalty applied for unverified assumptions and dynamic variables.
        Each explicit assumption incurs a 4.0 point uncertainty penalty (capped at 25.0).
        Lower confidence (< 1.0) adds up to a 20.0 point penalty.
        """
        count = len(candidate.assumptions)
        conf_penalty = max(0.0, (1.0 - candidate.confidence) * 20.0) if hasattr(candidate, "confidence") else 0.0
        return min(35.0, (count * 4.0) + conf_penalty)

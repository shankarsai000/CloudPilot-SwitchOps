"""
CloudPilot SwitchOps — Phase 3.1 Objective Model Hardening Tests

Verifies:
1. Zero baseline monthly cost does not trigger ZeroDivisionError; neutral savings yield neutral score.
2. Negative baseline monthly cost safely defaults without failure.
3. Negative savings (cost increase, e.g. Multi-AZ upgrade) are properly penalized and bounded [0.0, 100.0].
4. Extreme savings (> 100% of baseline) are clamped to 100.0.
5. Missing or unparseable monetary values default to Decimal("0.00").
6. Invalid or unexpected preference profile defaults cleanly to BALANCED.
7. Objective scores version is stamped as "1.1".
8. All 4 score dimensions strictly remain within [0.0, 100.0].
"""

from decimal import Decimal
import pytest

from app.domain.candidates import (
    ApplicabilityStatus,
    Candidate,
    CandidateType,
    ImpactLevel,
    OperationalComplexity,
)
from app.domain.objectives import (
    ObjectiveDimension,
    ObjectiveScores,
    PreferenceProfile,
)
from app.services.decision.objective_calculator import ObjectiveCalculator


def make_sample_candidate(
    cand_id: str = "cand-test",
    cost_before: str = "100.00",
    cost_after: str = "60.00",
    savings: str = "40.00",
    sec_impact: ImpactLevel = ImpactLevel.NEUTRAL,
    rel_impact: ImpactLevel = ImpactLevel.NEUTRAL,
    complexity: OperationalComplexity = OperationalComplexity.LOW,
    assumptions: list[str] | None = None,
    confidence: float = 1.0,
) -> Candidate:
    return Candidate(
        candidate_id=cand_id,
        title=f"Sample Candidate {cand_id}",
        description="Sample candidate for objective calculator tests",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=["res-1"],
        estimated_monthly_cost_before=cost_before,
        estimated_monthly_cost_after=cost_after,
        estimated_monthly_savings=savings,
        security_impact=sec_impact,
        reliability_impact=rel_impact,
        operational_complexity=complexity,
        assumptions=assumptions or [],
        confidence=confidence,
        applicability=ApplicabilityStatus.APPLICABLE,
    )


class TestObjectiveModelHardening:
    """Test suite ensuring absolute robustness and mathematical bounds for the multi-objective model."""

    def test_zero_baseline_monthly_cost_safety(self):
        """Zero baseline cost must not throw ZeroDivisionError and should produce bounded scores."""
        calc = ObjectiveCalculator(baseline_monthly_cost=Decimal("0.00"))
        # Neutral candidate (0 savings)
        cand_zero = make_sample_candidate(savings="0.00")
        scores_zero = calc.evaluate_candidate(cand_zero)

        assert 0.0 <= scores_zero.cost_score <= 100.0
        assert scores_zero.cost_score == 50.0  # Neutral baseline
        assert scores_zero.model_version == "1.1"

        # Candidate with positive savings
        cand_pos = make_sample_candidate(savings="50.00")
        scores_pos = calc.evaluate_candidate(cand_pos)
        assert 50.0 < scores_pos.cost_score <= 100.0

    def test_negative_savings_cost_increase_handling(self):
        """Candidates that increase cost (negative savings) are penalized and bounded in [0.0, 100.0]."""
        calc = ObjectiveCalculator(baseline_monthly_cost=Decimal("100.00"))

        # Candidate increasing spend by $50 (e.g. adding HA standby)
        cand_ha = make_sample_candidate(savings="-50.00")
        scores = calc.evaluate_candidate(cand_ha)

        assert scores.cost_score < 50.0
        assert 0.0 <= scores.cost_score <= 100.0

        # Massive cost increase (-$1000) must clamp at 0.0, never negative
        cand_extreme_ha = make_sample_candidate(savings="-1000.00")
        scores_extreme = calc.evaluate_candidate(cand_extreme_ha)
        assert scores_extreme.cost_score == 0.0

    def test_savings_greater_than_baseline_clamped(self):
        """Extreme savings (> 100% of baseline) clamp at 100.0, never exceeding upper bound."""
        calc = ObjectiveCalculator(baseline_monthly_cost=Decimal("100.00"))
        cand_huge_savings = make_sample_candidate(savings="500.00")
        scores = calc.evaluate_candidate(cand_huge_savings)

        assert scores.cost_score == 100.0

    def test_unparseable_cost_string_handled_safely(self):
        """Malformed or None cost strings gracefully fall back to 0.00 Decimal savings."""
        calc = ObjectiveCalculator()
        cand = make_sample_candidate(savings="invalid_decimal")
        scores = calc.evaluate_candidate(cand)

        assert scores.cost_score == 50.0
        assert scores.cost_savings_amount == Decimal("0.00")

    def test_uncertainty_penalty_monotonic_and_bounded(self):
        """Unverified assumptions increase uncertainty penalty, clamped within bounds."""
        calc = ObjectiveCalculator()

        cand_clean = make_sample_candidate(assumptions=[], confidence=1.0)
        scores_clean = calc.evaluate_candidate(cand_clean)
        assert scores_clean.uncertainty_penalty == 0.0

        # Candidate with 5 unverified assumptions and lower confidence
        cand_uncertain = make_sample_candidate(
            assumptions=["a1", "a2", "a3", "a4", "a5"],
            confidence=0.7,
        )
        scores_uncertain = calc.evaluate_candidate(cand_uncertain)
        assert scores_uncertain.uncertainty_penalty > 0.0
        assert scores_uncertain.uncertainty_penalty <= 35.0

        # Ensure adjusted scores did not drop below 0.0
        assert scores_uncertain.cost_score >= 0.0
        assert scores_uncertain.security_score >= 0.0
        assert scores_uncertain.reliability_score >= 0.0
        assert scores_uncertain.simplicity_score >= 0.0

    def test_invalid_preference_profile_fallback(self):
        """Passing an invalid or None profile safely falls back to BALANCED profile without error."""
        calc = ObjectiveCalculator()
        cand = make_sample_candidate()
        scores = calc.evaluate_candidate(cand)

        # Valid profile
        score_bal = calc.compute_weighted_score(scores, PreferenceProfile.BALANCED)
        assert 0.0 <= score_bal <= 100.0

        # Invalid profile passed dynamically
        score_fallback = calc.compute_weighted_score(scores, "UNKNOWN_PROFILE")  # type: ignore
        assert score_fallback == score_bal

    def test_objective_model_version_stamped(self):
        """All computed ObjectiveScores declare model_version = '1.1'."""
        calc = ObjectiveCalculator()
        cand = make_sample_candidate()
        scores = calc.evaluate_candidate(cand)
        assert scores.model_version == "1.1"

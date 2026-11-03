"""
CloudPilot SwitchOps — Unit Tests: Objective Calculator

Tests 4D multi-objective scoring (Cost, Security, Reliability, Simplicity),
Decimal arithmetic precision, score directionality, uncertainty penalties,
and preference weighting.
"""

from decimal import Decimal
import pytest

from app.domain.candidates import (
    Candidate,
    CandidateType,
    ImpactLevel,
    OperationalComplexity,
    ProposedChange,
)
from app.domain.objectives import (
    ObjectiveScores,
    PreferenceProfile,
    PREFERENCE_WEIGHTS,
)
from app.services.decision.objective_calculator import ObjectiveCalculator


def make_test_candidate(
    cid: str = "cand-test",
    savings: str = "50.00",
    sec_impact: ImpactLevel = ImpactLevel.POSITIVE,
    rel_impact: ImpactLevel = ImpactLevel.NEUTRAL,
    complexity: OperationalComplexity = OperationalComplexity.LOW,
    confidence: float = 1.0,
) -> Candidate:
    return Candidate(
        candidate_id=cid,
        title="Test Candidate",
        description="Testing candidate scoring",
        candidate_type=CandidateType.RIGHTSIZE_COMPUTE,
        target_resource_ids=["res-1"],
        proposed_changes=[
            ProposedChange(
                resource_id="res-1",
                resource_type="aws_instance",
                attribute_path="instance_type",
                current_value="t3.xlarge",
                proposed_value="t3.medium",
            )
        ],
        estimated_monthly_cost_before=Decimal("150.00"),
        estimated_monthly_cost_after=Decimal("150.00") - Decimal(savings),
        estimated_monthly_savings=Decimal(savings),
        security_impact=sec_impact,
        reliability_impact=rel_impact,
        operational_complexity=complexity,
        confidence=confidence,
    )


def test_objective_scores_range_and_decimal_precision():
    calculator = ObjectiveCalculator(baseline_monthly_cost=Decimal("300.00"))
    cand = make_test_candidate(savings="100.00")

    scores = calculator.calculate_scores(cand)

    assert 0.0 <= scores.cost_score <= 100.0
    assert 0.0 <= scores.security_score <= 100.0
    assert 0.0 <= scores.reliability_score <= 100.0
    assert 0.0 <= scores.simplicity_score <= 100.0
    assert scores.cost_savings_amount == Decimal("100.00")


def test_score_directionality_higher_savings_yields_higher_cost_score():
    calculator = ObjectiveCalculator(baseline_monthly_cost=Decimal("500.00"))
    low_save = make_test_candidate(cid="cand-low", savings="20.00")
    high_save = make_test_candidate(cid="cand-high", savings="200.00")

    scores_low = calculator.calculate_scores(low_save)
    scores_high = calculator.calculate_scores(high_save)

    assert scores_high.cost_score > scores_low.cost_score


def test_score_directionality_security_impact():
    calculator = ObjectiveCalculator(baseline_monthly_cost=Decimal("500.00"))
    sec_pos = make_test_candidate(cid="c1", sec_impact=ImpactLevel.POSITIVE)
    sec_neut = make_test_candidate(cid="c2", sec_impact=ImpactLevel.NEUTRAL)
    sec_neg = make_test_candidate(cid="c3", sec_impact=ImpactLevel.NEGATIVE)

    assert calculator.calculate_scores(sec_pos).security_score > calculator.calculate_scores(sec_neut).security_score
    assert calculator.calculate_scores(sec_neut).security_score > calculator.calculate_scores(sec_neg).security_score


def test_uncertainty_penalty_reduces_score():
    calculator = ObjectiveCalculator(baseline_monthly_cost=Decimal("500.00"))
    high_conf = make_test_candidate(cid="c-high-conf", savings="100.00", confidence=1.0)
    low_conf = make_test_candidate(cid="c-low-conf", savings="100.00", confidence=0.5)

    scores_high = calculator.calculate_scores(high_conf)
    scores_low = calculator.calculate_scores(low_conf)

    assert scores_low.cost_score < scores_high.cost_score


def test_weighted_score_preference_profiles():
    calculator = ObjectiveCalculator(baseline_monthly_cost=Decimal("500.00"))
    cand = make_test_candidate(savings="150.00", sec_impact=ImpactLevel.NEGATIVE, rel_impact=ImpactLevel.HIGHLY_POSITIVE)

    w_balanced = calculator.calculate_weighted_score(cand, PreferenceProfile.BALANCED)
    w_cost = calculator.calculate_weighted_score(cand, PreferenceProfile.COST_FIRST)
    w_sec = calculator.calculate_weighted_score(cand, PreferenceProfile.SECURITY_FIRST)
    w_rel = calculator.calculate_weighted_score(cand, PreferenceProfile.RELIABILITY_FIRST)

    assert isinstance(w_balanced, float)
    assert 0.0 <= w_balanced <= 100.0
    # Cost-first profile should weight high cost savings more favorably than security-first
    assert w_cost > w_sec

"""
CloudPilot SwitchOps — Unit Tests: Pareto Optimizer

Tests true multi-objective Pareto dominance calculation, non-dominated set
filtering, preference ranking across 4 dimensions, and handling of empty sets.
"""

from decimal import Decimal
import pytest

from app.domain.candidates import (
    Candidate,
    CandidateType,
    ImpactLevel,
    OperationalComplexity,
)
from app.domain.decisions import CandidateEvaluation, ParetoStatus
from app.domain.objectives import ObjectiveScores, PreferenceProfile
from app.services.decision.pareto_optimizer import ParetoOptimizer


def make_eval(
    cid: str,
    cost: float,
    sec: float,
    rel: float,
    simp: float,
    is_feasible: bool = True,
    savings: str = "50.00",
) -> CandidateEvaluation:
    cand = Candidate(
        candidate_id=cid,
        title=f"Candidate {cid}",
        description="Testing Pareto",
        candidate_type=CandidateType.CUSTOM,
        target_resource_ids=["res-1"],
        proposed_changes=[],
        estimated_monthly_cost_before=Decimal("200.00"),
        estimated_monthly_cost_after=Decimal("200.00") - Decimal(savings),
        estimated_monthly_savings=Decimal(savings),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )
    scores = ObjectiveScores(
        cost_score=cost,
        security_score=sec,
        reliability_score=rel,
        simplicity_score=simp,
        cost_savings_amount=Decimal(savings),
    )
    return CandidateEvaluation(
        candidate=cand,
        objective_scores=scores,
        is_feasible=is_feasible,
    )


def test_pareto_dominance_filtering():
    # A clearly dominates B: A has higher cost, higher security, equal rel and simp
    # C is incomparable: lower cost than A, but higher security than A
    cand_a = make_eval("A", cost=80.0, sec=70.0, rel=80.0, simp=90.0)
    cand_b = make_eval("B", cost=60.0, sec=50.0, rel=80.0, simp=90.0)
    cand_c = make_eval("C", cost=70.0, sec=95.0, rel=80.0, simp=90.0)

    optimizer = ParetoOptimizer()
    pareto, dominated, rejected = optimizer.calculate_pareto_frontier(
        evaluations=[cand_a, cand_b, cand_c],
        preference_profile=PreferenceProfile.BALANCED,
    )

    pareto_ids = {e.candidate.candidate_id for e in pareto}
    dominated_ids = {e.candidate.candidate_id for e in dominated}

    # A and C must be on the Pareto frontier (incomparable)
    assert "A" in pareto_ids
    assert "C" in pareto_ids

    # B must be dominated by A
    assert "B" in dominated_ids
    b_eval = next(e for e in dominated if e.candidate.candidate_id == "B")
    assert b_eval.pareto_status == ParetoStatus.DOMINATED
    assert "A" in b_eval.dominated_by


def test_infeasible_candidates_excluded_from_pareto():
    cand_valid = make_eval("Valid", cost=50.0, sec=50.0, rel=50.0, simp=50.0, is_feasible=True)
    cand_invalid = make_eval("Invalid", cost=99.0, sec=99.0, rel=99.0, simp=99.0, is_feasible=False)

    optimizer = ParetoOptimizer()
    pareto, dominated, rejected = optimizer.calculate_pareto_frontier(
        evaluations=[cand_valid, cand_invalid],
        preference_profile=PreferenceProfile.BALANCED,
    )

    pareto_ids = {e.candidate.candidate_id for e in pareto}
    rejected_ids = {e.candidate.candidate_id for e in rejected}

    assert "Valid" in pareto_ids
    assert "Invalid" in rejected_ids
    assert "Invalid" not in pareto_ids


def test_preference_profile_ranks_pareto_frontier():
    # Candidate Cheaper: high cost score (90), medium security (50)
    # Candidate Safer: medium cost score (50), high security (95)
    cand_cheaper = make_eval("Cheaper", cost=90.0, sec=50.0, rel=70.0, simp=80.0, savings="100.00")
    cand_safer = make_eval("Safer", cost=50.0, sec=95.0, rel=70.0, simp=80.0, savings="30.00")

    optimizer = ParetoOptimizer()

    # Under COST_FIRST: Cheaper must be ranked #1
    p_cost, _, _ = optimizer.calculate_pareto_frontier([cand_cheaper, cand_safer], PreferenceProfile.COST_FIRST)
    assert p_cost[0].candidate.candidate_id == "Cheaper"

    # Under SECURITY_FIRST: Safer must be ranked #1
    p_sec, _, _ = optimizer.calculate_pareto_frontier([cand_cheaper, cand_safer], PreferenceProfile.SECURITY_FIRST)
    assert p_sec[0].candidate.candidate_id == "Safer"


def test_empty_feasible_candidate_set():
    cand_bad = make_eval("Bad", cost=10.0, sec=10.0, rel=10.0, simp=10.0, is_feasible=False)

    optimizer = ParetoOptimizer()
    pareto, dominated, rejected = optimizer.calculate_pareto_frontier([cand_bad])

    assert len(pareto) == 0
    assert len(dominated) == 0
    assert len(rejected) == 1

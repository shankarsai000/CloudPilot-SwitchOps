"""
CloudPilot SwitchOps — Phase 3.2 Unit Tests: Z3 Semantics and Selection Verification

Tests and documents the formal boundary and explicit taxonomy distinguishing:
1. Rule-Engine Validation (deterministic Python checks)
2. Z3 Satisfiability (Z3_CONSTRAINTS_SAT) — encoded constraint satisfiability only;
   NEVER described as proof of global safety or Pareto optimality.
3. Z3 Unsatisfiability (Z3_CONSTRAINTS_UNSAT) — contradictory constraint set.
4. Z3 Unknown (Z3_UNKNOWN) — solver timeout or undecidability.
5. Z3 Unavailable (Z3_UNAVAILABLE) — runtime library missing; fail-safe reporting.
6. Pareto Optimality vs Z3 SAT — Pareto optimality ranks non-dominated trade-offs
   among feasible candidates, whereas Z3 only checks constraint satisfiability.
7. Decoded Model Verification — solver model decoding guarantees no invariant-violating
   or mutually contradictory candidates are ever returned in selected combinations.
"""

from decimal import Decimal
from unittest.mock import patch
import pytest

from app.domain.candidates import (
    Candidate,
    CandidateType,
    ImpactLevel,
    OperationalComplexity,
    ProposedChange,
)
from app.domain.decisions import CandidateEvaluation, CandidateInteraction, InteractionType
from app.domain.objectives import ObjectiveScores, PreferenceProfile
from app.domain.policies import PolicyConfiguration
from app.services.decision.constraint_engine import ConstraintEngine, Z3_AVAILABLE
from app.services.decision.pareto_optimizer import ParetoOptimizer


def make_test_candidate(cid: str, cost_after: str = "50.00", savings: str = "50.00") -> Candidate:
    return Candidate(
        candidate_id=cid,
        title=f"Candidate {cid}",
        description="Testing Z3 semantics and selection verification",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=[f"res-{cid}"],
        target_resource_ids=[f"res-{cid}"],
        proposed_changes=[
            ProposedChange(
                resource_id=f"res-{cid}",
                resource_type="aws_instance",
                attribute_path="instance_type",
                current_value="m5.xlarge",
                proposed_value="t3.medium",
            )
        ],
        estimated_monthly_cost_before=Decimal("100.00"),
        estimated_monthly_cost_after=Decimal(cost_after),
        estimated_monthly_savings=Decimal(savings),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )


def test_rule_engine_validated_status_on_empty_candidate_set():
    """Empty candidate set returns RULE_ENGINE_VALIDATED without solver execution."""
    engine = ConstraintEngine()
    status, diag = engine.verify_satisfiability_with_z3(
        candidates=[],
        baseline_cost=Decimal("100.00"),
    )
    assert status == "RULE_ENGINE_VALIDATED"
    assert diag["solver_result"] == "empty"


@pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 solver required")
def test_z3_sat_semantics_does_not_claim_global_safety_or_optimality():
    """
    Z3_CONSTRAINTS_SAT indicates only that the encoded constraints are satisfiable.
    The formal guarantee string explicitly disclaims global safety or optimization.
    """
    policy = PolicyConfiguration(monthly_budget_ceiling="200.00")
    engine = ConstraintEngine(policy=policy)
    c1 = make_test_candidate("c1", cost_after="80.00")

    status, diag = engine.verify_satisfiability_with_z3(
        candidates=[c1],
        baseline_cost=Decimal("100.00"),
    )
    assert status == "Z3_CONSTRAINTS_SAT"
    assert diag["solver_result"] == "sat"
    assert "c1" in diag["satisfiable_sample_selection"]
    guarantee = diag["formal_guarantee"]
    assert "SAT indicates constraint satisfiability, not global proof of runtime safety" in guarantee


@pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 solver required")
def test_z3_unsat_when_mandatory_invariants_make_selection_impossible():
    """When all candidates violate invariants and enforce_at_least_one is True, status is UNSAT."""
    policy = PolicyConfiguration(disallow_public_database=True)
    engine = ConstraintEngine(policy=policy)

    # Deliberate anti-pattern candidate: disable auth
    cand_unsafe = Candidate(
        candidate_id="c-unsafe",
        title="Disable Auth",
        description="Unsafe anti-pattern",
        candidate_type=CandidateType.DISABLE_AUTH,
        affected_resource_ids=["db"],
        target_resource_ids=["db"],
        proposed_changes=[],
        estimated_monthly_cost_before=Decimal("100.00"),
        estimated_monthly_cost_after=Decimal("100.00"),
        estimated_monthly_savings=Decimal("0.00"),
        security_impact=ImpactLevel.NEGATIVE,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    status, diag = engine.verify_satisfiability_with_z3(
        candidates=[cand_unsafe],
        baseline_cost=Decimal("100.00"),
        enforce_at_least_one=True,
    )
    assert status == "Z3_CONSTRAINTS_UNSAT"
    assert diag["solver_result"] == "unsat"
    assert diag["rejected_by_invariant_count"] >= 1


@pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 solver required")
def test_z3_unknown_on_solver_timeout():
    """Z3 solver returning unknown (e.g. timeout) maps to Z3_UNKNOWN."""
    engine = ConstraintEngine()
    c1 = make_test_candidate("c1")

    # Pass 1ms timeout with mock or complex solver to test timeout handling
    with patch("z3.Solver.check") as mock_check:
        import z3
        mock_check.return_value = z3.unknown
        status, diag = engine.verify_satisfiability_with_z3(
            candidates=[c1],
            baseline_cost=Decimal("100.00"),
            solver_timeout_ms=1,
        )
        assert status == "Z3_UNKNOWN"
        assert diag["solver_result"] == "unknown"


def test_z3_unavailable_reporting_when_library_missing():
    """When Z3 is unavailable, ConstraintEngine returns Z3_UNAVAILABLE and does not claim SAT."""
    with patch("app.services.decision.constraint_engine.Z3_AVAILABLE", False):
        engine = ConstraintEngine()
        status, diag = engine.verify_satisfiability_with_z3(
            candidates=[make_test_candidate("c1")],
            baseline_cost=Decimal("100.00"),
        )
        assert status == "Z3_UNAVAILABLE"
        assert "not installed or available" in diag["reason"]


def test_pareto_optimality_is_distinct_from_z3_satisfiability():
    """
    Demonstrates the semantic difference:
    - Z3 SAT checks feasibility (does candidate satisfy hard boundaries?).
    - Pareto Optimality evaluates multi-objective dominance (is candidate non-dominated across
      cost, security, reliability, simplicity?).
    Two candidates can both be Z3 SAT feasible, yet one strictly dominates the other in Pareto ranking.
    """
    c_superior = make_test_candidate("c-sup", cost_after="40.00", savings="60.00")
    c_inferior = make_test_candidate("c-inf", cost_after="80.00", savings="20.00")

    eval_superior = CandidateEvaluation(
        candidate=c_superior,
        objective_scores=ObjectiveScores(
            cost_score=0.9,
            security_score=0.8,
            reliability_score=0.8,
            simplicity_score=0.9,
        ),
        is_feasible=True,
    )
    eval_inferior = CandidateEvaluation(
        candidate=c_inferior,
        objective_scores=ObjectiveScores(
            cost_score=0.3,
            security_score=0.5,
            reliability_score=0.5,
            simplicity_score=0.6,
        ),
        is_feasible=True,
    )

    optimizer = ParetoOptimizer()
    pareto_frontier, dominated, rejected = optimizer.calculate_pareto_frontier(
        evaluations=[eval_superior, eval_inferior],
        preference_profile=PreferenceProfile.BALANCED,
    )

    # Both were feasible (would pass Z3 SAT), but only superior is on the Pareto frontier!
    assert len(pareto_frontier) == 1
    assert pareto_frontier[0].candidate.candidate_id == "c-sup"
    assert len(dominated) == 1
    assert dominated[0].candidate.candidate_id == "c-inf"


@pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 solver required")
def test_decoded_model_cannot_select_conflicting_candidates():
    """
    Decoded model verification: If two candidates are conflicting, the solver model
    can NEVER include both in satisfiable_sample_selection.
    """
    engine = ConstraintEngine()
    c1 = make_test_candidate("c1")
    c2 = make_test_candidate("c2")

    interaction = CandidateInteraction(
        candidate_ids=["c1", "c2"],
        interaction_type=InteractionType.CONFLICTING,
        conflicting_resource_id="res-shared",
        reason="Conflicting mutations",
    )

    status, diag = engine.verify_satisfiability_with_z3(
        candidates=[c1, c2],
        baseline_cost=Decimal("100.00"),
        interactions=[interaction],
        enforce_at_least_one=True,
    )
    assert status == "Z3_CONSTRAINTS_SAT"
    selection = diag["satisfiable_sample_selection"]
    # Exactly one can be selected, NEVER both
    assert not ("c1" in selection and "c2" in selection)
    assert len(selection) >= 1

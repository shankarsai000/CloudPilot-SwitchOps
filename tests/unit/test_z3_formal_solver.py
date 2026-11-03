"""
CloudPilot SwitchOps — Phase 3.1 Z3 Formal SMT Solver Verification Tests

Tests the formal satisfiability verification engine across:
1. Valid SAT scenarios with compatible budgets and invariants.
2. Hard invariant violations (CONST-SEC-01, CONST-REL-01).
3. Budget violations (CONST-FIN-01).
4. Contradictory candidate selections (mutual exclusions / conflicts).
5. Dependency satisfaction and violations.
6. Unsatisfiable policy combinations.
7. Simulated Z3 unavailable and unknown solver behavior.
8. Standardized status reporting (Z3_CONSTRAINTS_SAT, Z3_CONSTRAINTS_UNSAT, Z3_UNKNOWN, Z3_UNAVAILABLE, RULE_ENGINE_VALIDATED).
"""

from decimal import Decimal
from unittest.mock import patch
import pytest

from app.domain.candidates import (
    ApplicabilityStatus,
    Candidate,
    CandidateType,
    ImpactLevel,
    OperationalComplexity,
    ProposedChange,
)
from app.domain.decisions import CandidateInteraction, InteractionType
from app.domain.policies import PolicyConfiguration
from app.services.decision.constraint_engine import ConstraintEngine, Z3_AVAILABLE


def make_test_candidate(
    cand_id: str,
    changes: list[ProposedChange],
    cand_type: CandidateType = CandidateType.RESIZE_COMPUTE,
    cost_before: str = "100.00",
    cost_after: str = "80.00",
    savings: str = "20.00",
    applicability: ApplicabilityStatus = ApplicabilityStatus.APPLICABLE,
) -> Candidate:
    return Candidate(
        candidate_id=cand_id,
        title=f"Test Candidate {cand_id}",
        description="Test description",
        candidate_type=cand_type,
        affected_resource_ids=[ch.resource_id for ch in changes] if changes else ["res-1"],
        proposed_changes=changes,
        estimated_monthly_cost_before=cost_before,
        estimated_monthly_cost_after=cost_after,
        estimated_monthly_savings=savings,
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
        applicability=applicability,
    )


class TestZ3FormalSolver:
    """Rigorous formal methods testing for the Z3 SMT constraint engine."""

    def test_z3_sat_with_compliant_candidates(self):
        """Valid candidates with budget headroom and valid invariants produce Z3_CONSTRAINTS_SAT."""
        policy = PolicyConfiguration(monthly_budget_ceiling="250.00")
        engine = ConstraintEngine(policy=policy)
        cand1 = make_test_candidate("cand-1", [], cost_after="150.00")
        cand2 = make_test_candidate("cand-2", [], cost_after="180.00")

        status, diag = engine.verify_satisfiability_with_z3(
            candidates=[cand1, cand2],
            baseline_cost=Decimal("200.00"),
        )
        if Z3_AVAILABLE:
            assert status == "Z3_CONSTRAINTS_SAT"
            assert diag["solver_result"] == "sat"
            assert len(diag["satisfiable_sample_selection"]) > 0
            assert "formal_guarantee" in diag
        else:
            assert status == "Z3_UNAVAILABLE"

    def test_z3_unsat_on_unsafe_public_database_exposure(self):
        """Unsafe candidate proposing 0.0.0.0 binding for database listener is formally blocked by Z3."""
        policy = PolicyConfiguration(disallow_public_database=True)
        engine = ConstraintEngine(policy=policy)

        unsafe_change = ProposedChange(
            resource_id="res-db-pg",
            resource_name="postgres",
            resource_type="aws_db_instance",
            attribute_path="ports",
            current_value=["127.0.0.1:5432:5432"],
            proposed_value=["0.0.0.0:5432:5432"],
            action_type="MODIFY",
        )
        unsafe_cand = make_test_candidate(
            "cand-unsafe-db",
            [unsafe_change],
            cand_type=CandidateType.DISABLE_AUTH,
        )

        status, diag = engine.verify_satisfiability_with_z3(
            candidates=[unsafe_cand],
            baseline_cost=Decimal("200.00"),
            enforce_at_least_one=True,
        )
        if Z3_AVAILABLE:
            assert status == "Z3_CONSTRAINTS_UNSAT"
            assert diag["solver_result"] == "unsat"
        else:
            assert status == "Z3_UNAVAILABLE"

    def test_z3_unsat_on_persistence_removal(self):
        """Candidate proposing volume removal on stateful database is formally blocked by Z3."""
        policy = PolicyConfiguration(mandatory_persistence_for_stateful=True)
        engine = ConstraintEngine(policy=policy)

        drop_vol_change = ProposedChange(
            resource_id="res-db-volume",
            resource_name="postgres_data",
            resource_type="docker_volume",
            attribute_path="volumes",
            current_value=["postgres_data:/var/lib/data"],
            proposed_value=None,
            action_type="REMOVE",
        )
        drop_cand = make_test_candidate(
            "cand-drop-vol",
            [drop_vol_change],
            cand_type=CandidateType.DROP_PERSISTENCE,
        )

        status, diag = engine.verify_satisfiability_with_z3(
            candidates=[drop_cand],
            baseline_cost=Decimal("200.00"),
            enforce_at_least_one=True,
        )
        if Z3_AVAILABLE:
            assert status == "Z3_CONSTRAINTS_UNSAT"
            assert diag["solver_result"] == "unsat"
        else:
            assert status == "Z3_UNAVAILABLE"

    def test_z3_unsat_on_budget_violation(self):
        """When budget ceiling is impossible to satisfy, solver formally reports UNSAT."""
        policy = PolicyConfiguration(monthly_budget_ceiling="50.00")
        engine = ConstraintEngine(policy=policy)

        # Candidate post-change cost is $120, which strictly exceeds budget $50
        expensive_cand = make_test_candidate("cand-expensive", [], cost_after="120.00")

        status, diag = engine.verify_satisfiability_with_z3(
            candidates=[expensive_cand],
            baseline_cost=Decimal("200.00"),
            enforce_at_least_one=True,
        )
        if Z3_AVAILABLE:
            assert status == "Z3_CONSTRAINTS_UNSAT"
            assert diag["solver_result"] == "unsat"
        else:
            assert status == "Z3_UNAVAILABLE"

    def test_z3_mutual_exclusion_conflicting_candidates(self):
        """Solver enforces mutual exclusion Not(And(c1, c2)) when candidates conflict."""
        policy = PolicyConfiguration()
        engine = ConstraintEngine(policy=policy)

        cand_a = make_test_candidate("cand-a", [], cost_after="90.00")
        cand_b = make_test_candidate("cand-b", [], cost_after="80.00")

        conflict_interaction = CandidateInteraction(
            candidate_ids=["cand-a", "cand-b"],
            interaction_type=InteractionType.CONFLICTING,
            conflicting_resource_id="res-compute",
            reason="Both candidates modify the same compute instance type contradictorily.",
        )

        # When both are present and conflict, solver should allow selection of either, but NOT both simultaneously
        status, diag = engine.verify_satisfiability_with_z3(
            candidates=[cand_a, cand_b],
            baseline_cost=Decimal("150.00"),
            interactions=[conflict_interaction],
            enforce_at_least_one=True,
        )
        if Z3_AVAILABLE:
            assert status == "Z3_CONSTRAINTS_SAT"
            selected = diag["satisfiable_sample_selection"]
            # Both cannot be selected simultaneously in any valid model
            assert not (("cand-a" in selected) and ("cand-b" in selected))
        else:
            assert status == "Z3_UNAVAILABLE"

    def test_z3_dependency_implication(self):
        """Solver encodes dependent -> parent implication correctly."""
        policy = PolicyConfiguration()
        engine = ConstraintEngine(policy=policy)

        parent_cand = make_test_candidate("cand-parent", [], cost_after="100.00")
        dep_cand = make_test_candidate("cand-dependent", [], cost_after="90.00")

        dep_interaction = CandidateInteraction(
            candidate_ids=["cand-dependent", "cand-parent"],
            interaction_type=InteractionType.DEPENDENT,
            reason="cand-dependent requires cand-parent.",
        )

        status, diag = engine.verify_satisfiability_with_z3(
            candidates=[parent_cand, dep_cand],
            baseline_cost=Decimal("150.00"),
            interactions=[dep_interaction],
            enforce_at_least_one=True,
        )
        if Z3_AVAILABLE:
            assert status == "Z3_CONSTRAINTS_SAT"
        else:
            assert status == "Z3_UNAVAILABLE"

    def test_z3_empty_candidates_returns_rule_engine_validated(self):
        """Empty candidate pool returns RULE_ENGINE_VALIDATED without failure."""
        engine = ConstraintEngine()
        status, diag = engine.verify_satisfiability_with_z3(
            candidates=[],
            baseline_cost=Decimal("100.00"),
        )
        assert status == "RULE_ENGINE_VALIDATED"
        assert diag["solver_result"] == "empty"

    def test_z3_unavailable_reporting(self):
        """When Z3 is unavailable, engine truthfully reports Z3_UNAVAILABLE instead of faking SAT."""
        with patch("app.services.decision.constraint_engine.Z3_AVAILABLE", False):
            engine = ConstraintEngine()
            cand = make_test_candidate("c1", [])
            status, diag = engine.verify_satisfiability_with_z3(
                candidates=[cand],
                baseline_cost=Decimal("100.00"),
            )
            assert status == "Z3_UNAVAILABLE"
            assert "not installed or available" in diag["reason"]

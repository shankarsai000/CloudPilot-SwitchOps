"""
CloudPilot SwitchOps — Unit Tests: Constraint Engine & Z3 SMT Solver

Tests deterministic hard constraint enforcement:
- CONST-SEC-01 (No public database ingress)
- CONST-SEC-02 (No privileged containers)
- CONST-SEC-03 (No unencrypted databases)
- CONST-REL-01 (No deleting persistent data volumes)
- CONST-FIN-01 (Budget ceiling adherence)
- Z3 formal SMT satisfiability checking (SAT and UNSAT scenarios)
- Immutability of hard constraints under preference profiles
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
from app.domain.constraints import ConstraintStatus, ConstraintType
from app.domain.policies import PolicyConfiguration
from app.services.decision.constraint_engine import ConstraintEngine


def make_candidate(
    cid: str,
    changes: list[ProposedChange],
    cost_after: str = "100.00",
    savings: str = "50.00",
) -> Candidate:
    return Candidate(
        candidate_id=cid,
        title=f"Candidate {cid}",
        description="Testing constraints",
        candidate_type=CandidateType.CUSTOM,
        target_resource_ids=[ch.resource_id for ch in changes],
        proposed_changes=changes,
        estimated_monthly_cost_before=Decimal("150.00"),
        estimated_monthly_cost_after=Decimal(cost_after),
        estimated_monthly_savings=Decimal(savings),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )


def test_hard_constraint_rejects_public_database():
    policy = PolicyConfiguration(disallow_public_databases=True)
    engine = ConstraintEngine(policy=policy)

    unsafe_change = ProposedChange(
        resource_id="db_sec_group",
        resource_type="aws_security_group_rule",
        attribute_path="cidr_blocks",
        current_value=["10.0.0.0/16"],
        proposed_value=["0.0.0.0/0"],
        change_metadata={"from_port": 5432, "to_port": 5432},
    )
    cand = make_candidate("cand-public-db", [unsafe_change])

    is_feasible, results, reasons = engine.evaluate(cand)
    assert not is_feasible
    assert any(not r.passed and r.constraint_id == "CONST-SEC-01" for r in results)
    assert any("CONST-SEC-01" in r for r in reasons)


def test_hard_constraint_rejects_privileged_container():
    policy = PolicyConfiguration(disallow_privileged_containers=True)
    engine = ConstraintEngine(policy=policy)

    unsafe_change = ProposedChange(
        resource_id="api_container",
        resource_type="docker_container",
        attribute_path="privileged",
        current_value=False,
        proposed_value=True,
    )
    cand = make_candidate("cand-priv-container", [unsafe_change])

    is_feasible, results, reasons = engine.evaluate(cand)
    assert not is_feasible
    assert any(not r.passed and r.constraint_id == "CONST-SEC-02" for r in results)


def test_hard_constraint_rejects_unencrypted_database():
    policy = PolicyConfiguration(require_storage_encryption=True)
    engine = ConstraintEngine(policy=policy)

    unsafe_change = ProposedChange(
        resource_id="staging_db",
        resource_type="aws_db_instance",
        attribute_path="storage_encrypted",
        current_value=True,
        proposed_value=False,
    )
    cand = make_candidate("cand-unencrypted-db", [unsafe_change])

    is_feasible, results, reasons = engine.evaluate(cand)
    assert not is_feasible
    assert any(not r.passed and r.constraint_id in ["CONST-SEC-03", "CONST-SEC-05"] for r in results)


def test_hard_constraint_rejects_deleting_persistent_volume():
    policy = PolicyConfiguration(prevent_data_volume_deletion=True)
    engine = ConstraintEngine(policy=policy)

    unsafe_change = ProposedChange(
        resource_id="postgres_data_vol",
        resource_type="docker_volume",
        attribute_path="volumes",
        current_value="postgres_data:/var/lib/postgresql/data",
        proposed_value=None,
    )
    cand = make_candidate("cand-drop-volume", [unsafe_change])

    is_feasible, results, reasons = engine.evaluate(cand)
    assert not is_feasible
    assert any(not r.passed and r.constraint_id == "CONST-REL-01" for r in results)


def test_hard_constraint_budget_ceiling_enforcement():
    policy = PolicyConfiguration(max_monthly_budget=Decimal("120.00"))
    engine = ConstraintEngine(policy=policy)

    # Cost after is 150.00 > budget 120.00
    expensive_cand = make_candidate("cand-expensive", [], cost_after="150.00")
    is_feasible, results, reasons = engine.evaluate(expensive_cand)
    assert not is_feasible
    assert any(not r.passed and r.constraint_id == "CONST-FIN-01" for r in results)

    # Cost after is 100.00 <= budget 120.00
    affordable_cand = make_candidate("cand-affordable", [], cost_after="100.00")
    is_feasible, results, reasons = engine.evaluate(affordable_cand)
    assert is_feasible


def test_z3_verification_sat_and_unsat():
    # SAT Scenario: Baseline is 200, budget is 250
    policy_sat = PolicyConfiguration(max_monthly_budget=Decimal("250.00"))
    engine_sat = ConstraintEngine(policy=policy_sat)
    cand1 = make_candidate("c1", [], cost_after="180.00")

    status_sat, diag_sat = engine_sat.verify_satisfiability_with_z3(
        candidates=[cand1],
        baseline_cost=Decimal("200.00"),
    )
    assert status_sat in ("Z3_CONSTRAINTS_SAT", "Z3_VERIFIED_SAT")

    # UNSAT Scenario: Impossible budget ceiling (e.g. max budget $10 when minimum possible is $180)
    policy_unsat = PolicyConfiguration(max_monthly_budget=Decimal("10.00"))
    engine_unsat = ConstraintEngine(policy=policy_unsat)

    status_unsat, diag_unsat = engine_unsat.verify_satisfiability_with_z3(
        candidates=[cand1],
        baseline_cost=Decimal("200.00"),
    )
    assert status_unsat in ("Z3_CONSTRAINTS_UNSAT", "Z3_VERIFIED_UNSAT")


def test_preference_profile_cannot_override_hard_constraint():
    """Verify that an infeasible candidate remains strictly rejected regardless of preference."""
    policy = PolicyConfiguration(disallow_public_databases=True)
    engine = ConstraintEngine(policy=policy)

    unsafe_change = ProposedChange(
        resource_id="db_sec_group",
        resource_type="aws_security_group_rule",
        attribute_path="cidr_blocks",
        current_value=["10.0.0.0/16"],
        proposed_value=["0.0.0.0/0"],
        change_metadata={"from_port": 5432, "to_port": 5432},
    )
    # Even if savings are $1000/mo, constraint MUST reject it
    cand = make_candidate("cand-high-saving-unsafe", [unsafe_change], cost_after="10.00", savings="1000.00")

    is_feasible, results, reasons = engine.evaluate(cand)
    assert not is_feasible
    assert len(reasons) > 0

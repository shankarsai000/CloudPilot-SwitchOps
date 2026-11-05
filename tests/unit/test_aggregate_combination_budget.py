"""
CloudPilot SwitchOps — Phase 3.2 Unit Tests: Aggregate Combination Budget Verification

Verifies:
1. Combined candidate cost is calculated using Decimal arithmetic without floating point drift.
2. Aggregate post-change monthly cost is checked against the budget ceiling.
3. Individual candidate feasibility CANNOT imply combined feasibility:
   - Candidate A alone satisfies budget ($80 <= $100).
   - Candidate B alone satisfies budget ($70 <= $100).
   - Combined Plan (A + B = $150) STRICTLY EXCEEDS budget ceiling ($100) and is marked infeasible.
4. Baseline resource costs are not double-counted when multiple candidates touch the same resource.
5. Cost increases (negative savings) and cost reductions (positive savings) aggregate properly.
6. Missing, invalid, or unknown pricing fails-closed (returns UNKNOWN/blocking) and cannot
   silently produce an apparently safe budget result in either Rule Engine or Z3 solver.
"""

from decimal import Decimal
import pytest

from app.domain.candidates import (
    ApplicabilityStatus,
    Candidate,
    CandidateType,
    ImpactLevel,
    OperationalComplexity,
    ProposedChange,
)
from app.domain.constraints import ConstraintSeverity, ConstraintStatus
from app.domain.policies import PolicyConfiguration
from app.services.decision.combination_optimizer import CombinationOptimizer
from app.services.decision.constraint_engine import ConstraintEngine, Z3_AVAILABLE


def make_cost_candidate(
    cid: str,
    res_id: str,
    cost_before: str,
    cost_after: str,
    savings: str,
    applicability: ApplicabilityStatus = ApplicabilityStatus.APPLICABLE,
    has_unknown_pricing: bool = False,
) -> Candidate:
    cand = Candidate(
        candidate_id=cid,
        title=f"Cost Candidate {cid}",
        description="Testing aggregate combination budget constraints",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=[res_id],
        target_resource_ids=[res_id],
        proposed_changes=[
            ProposedChange(
                resource_id=res_id,
                resource_type="aws_instance",
                attribute_path=f"instance_type_{cid}",
                current_value="m5.xlarge",
                proposed_value="t3.medium",
            )
        ],
        estimated_monthly_cost_before=Decimal(cost_before),
        estimated_monthly_cost_after=Decimal(cost_after),
        estimated_monthly_savings=Decimal(savings),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
        applicability=applicability,
        evidence={"has_unknown_pricing": has_unknown_pricing} if has_unknown_pricing else {},
    )
    return cand


def test_individual_feasible_but_combined_exceeds_budget():
    """
    Core Gate: Individual candidate feasibility must not imply combined feasibility.
    Baseline budget ceiling is $100/mo.
    Candidate 1: $80/mo (passes alone: $80 <= $100).
    Candidate 2: $70/mo (passes alone: $70 <= $100).
    Composite Plan (1 + 2): $150/mo (fails: $150 > $100).
    """
    policy = PolicyConfiguration(monthly_budget_ceiling="100.00")
    engine = ConstraintEngine(policy=policy)
    optimizer = CombinationOptimizer()

    # Resource 1: before $100, saves $20 -> after $80
    c1 = make_cost_candidate("c1", "vm-alpha", cost_before="100.00", cost_after="80.00", savings="20.00")
    # Resource 2: before $100, saves $30 -> after $70
    c2 = make_cost_candidate("c2", "vm-beta", cost_before="100.00", cost_after="70.00", savings="30.00")

    # 1. Verify individual feasibility
    is_f1, results1, reasons1 = engine.evaluate(c1)
    is_f2, results2, reasons2 = engine.evaluate(c2)
    assert is_f1 is True, f"c1 should pass budget check alone: {reasons1}"
    assert is_f2 is True, f"c2 should pass budget check alone: {reasons2}"

    # 2. Synthesize composite candidate
    composite = optimizer._synthesize_composite_candidate([c1, c2])

    # Combined before: $100 + $100 = $200
    # Combined savings: $20 + $30 = $50
    # Combined after: $200 - $50 = $150
    assert Decimal(composite.estimated_monthly_cost_before) == Decimal("200.00")
    assert Decimal(composite.estimated_monthly_savings) == Decimal("50.00")
    assert Decimal(composite.estimated_monthly_cost_after) == Decimal("150.00")

    # 3. Evaluate composite plan against budget ceiling ($100)
    is_fc, resultsc, reasonsc = engine.evaluate(composite)
    assert is_fc is False, "Composite plan must be rejected because $150 > $100 ceiling"
    fin_res = [r for r in resultsc if r.constraint_id == "CONST-FIN-01"][0]
    assert fin_res.status == ConstraintStatus.FAIL
    assert fin_res.is_blocking is True
    assert "$150.00" in fin_res.reason
    assert "$100.0" in fin_res.reason or "$100" in fin_res.reason


def test_baseline_resource_not_double_counted():
    """
    When two candidates modify the SAME resource on different attributes,
    the baseline cost of that resource must NOT be double-counted.
    Resource: baseline $100.00.
    c1 modifies disk (saves $15.00).
    c2 modifies instance type (saves $25.00).
    Total baseline cost should remain $100.00 (not $200.00).
    Total savings: $40.00.
    Post-change cost: $60.00.
    """
    optimizer = CombinationOptimizer()

    c1 = Candidate(
        candidate_id="c1-disk",
        title="Reduce disk size",
        description="Reduce disk size description",
        candidate_type=CandidateType.DOWNGRADE_STORAGE,
        affected_resource_ids=["srv-db-01"],
        target_resource_ids=["srv-db-01"],
        proposed_changes=[
            ProposedChange(
                resource_id="srv-db-01",
                resource_type="aws_instance",
                attribute_path="root_block_device.volume_size",
                current_value=100,
                proposed_value=50,
            )
        ],
        estimated_monthly_cost_before=Decimal("100.00"),
        estimated_monthly_cost_after=Decimal("85.00"),
        estimated_monthly_savings=Decimal("15.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    c2 = Candidate(
        candidate_id="c2-type",
        title="Rightsize CPU",
        description="Rightsize CPU description",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=["srv-db-01"],
        target_resource_ids=["srv-db-01"],
        proposed_changes=[
            ProposedChange(
                resource_id="srv-db-01",
                resource_type="aws_instance",
                attribute_path="instance_type",
                current_value="m5.xlarge",
                proposed_value="m5.large",
            )
        ],
        estimated_monthly_cost_before=Decimal("100.00"),
        estimated_monthly_cost_after=Decimal("75.00"),
        estimated_monthly_savings=Decimal("25.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    composite = optimizer._synthesize_composite_candidate([c1, c2])

    # Verify baseline cost is $100.00, NOT $200.00
    assert Decimal(composite.estimated_monthly_cost_before) == Decimal("100.00")
    assert Decimal(composite.estimated_monthly_savings) == Decimal("40.00")
    assert Decimal(composite.estimated_monthly_cost_after) == Decimal("60.00")


def test_cost_increases_and_savings_aggregate_with_decimal_precision():
    """
    Verifies that cost increases (negative savings) and savings aggregate accurately
    using Decimal arithmetic with 2 decimal places precision.
    """
    optimizer = CombinationOptimizer()

    # Candidate 1: Savings of $45.55
    c1 = make_cost_candidate("c1", "res-1", cost_before="100.00", cost_after="54.45", savings="45.55")
    # Candidate 2: Cost increase of $15.25 (negative savings)
    c2 = make_cost_candidate("c2", "res-2", cost_before="50.00", cost_after="65.25", savings="-15.25")

    composite = optimizer._synthesize_composite_candidate([c1, c2])

    assert Decimal(composite.estimated_monthly_cost_before) == Decimal("150.00")
    assert Decimal(composite.estimated_monthly_savings) == Decimal("30.30")
    assert Decimal(composite.estimated_monthly_cost_after) == Decimal("119.70")


def test_missing_or_unknown_pricing_fails_closed_in_rule_engine():
    """
    Missing, corrupted, or unknown pricing cannot silently produce a safe budget result.
    Must return ConstraintStatus.UNKNOWN with is_blocking=True.
    """
    policy = PolicyConfiguration(monthly_budget_ceiling="500.00")
    engine = ConstraintEngine(policy=policy)

    # 1. Candidate with explicit unknown pricing flag
    cand_unknown = make_cost_candidate(
        "c-unk", "res-x", cost_before="100.00", cost_after="50.00", savings="50.00", has_unknown_pricing=True
    )
    is_f, results, reasons = engine.evaluate(cand_unknown)
    assert is_f is False
    fin = [r for r in results if r.constraint_id == "CONST-FIN-01"][0]
    assert fin.status == ConstraintStatus.UNKNOWN
    assert fin.is_blocking is True

    # 2. Candidate with unparseable cost_after string
    cand_bad_num = Candidate(
        candidate_id="c-bad",
        title="Bad number candidate",
        description="Corrupted cost string",
        candidate_type=CandidateType.CUSTOM,
        affected_resource_ids=["res-x"],
        target_resource_ids=["res-x"],
        proposed_changes=[],
        estimated_monthly_cost_before="INVALID_DECIMAL",
        estimated_monthly_cost_after="NOT_A_NUMBER",
        estimated_monthly_savings="N/A",
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )
    is_f2, results2, _ = engine.evaluate(cand_bad_num)
    assert is_f2 is False
    fin2 = [r for r in results2 if r.constraint_id == "CONST-FIN-01"][0]
    assert fin2.status == ConstraintStatus.UNKNOWN
    assert fin2.is_blocking is True


@pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 solver required for SMT budget test")
def test_z3_solver_rejects_composite_plan_exceeding_budget_ceiling():
    """
    Verifies that Z3 SMT solver strictly encodes the budget ceiling and returns
    UNSAT if forced to select a composite candidate whose cost exceeds ceiling.
    """
    policy = PolicyConfiguration(monthly_budget_ceiling="100.00")
    engine = ConstraintEngine(policy=policy)
    optimizer = CombinationOptimizer()

    c1 = make_cost_candidate("c1", "res-1", cost_before="100.00", cost_after="80.00", savings="20.00")
    c2 = make_cost_candidate("c2", "res-2", cost_before="100.00", cost_after="70.00", savings="30.00")
    composite = optimizer._synthesize_composite_candidate([c1, c2])  # cost_after = $150.00

    # Running Z3 with ONLY the composite candidate: must be UNSAT because $150 > $100
    status, diag = engine.verify_satisfiability_with_z3(
        candidates=[composite],
        baseline_cost=Decimal("200.00"),
        enforce_at_least_one=True,
    )
    assert status == "Z3_CONSTRAINTS_UNSAT"
    assert diag["solver_result"] == "unsat"
    assert diag["rejected_by_invariant_count"] >= 1


@pytest.mark.skipif(not Z3_AVAILABLE, reason="Z3 solver required for SMT budget test")
def test_z3_solver_fails_closed_on_unknown_pricing():
    """
    Verifies that Z3 solver rejects candidates with unknown or unparseable pricing
    rather than treating them as $0.00.
    """
    policy = PolicyConfiguration(monthly_budget_ceiling="100.00")
    engine = ConstraintEngine(policy=policy)

    cand_unknown = make_cost_candidate(
        "c-unk", "res-x", cost_before="100.00", cost_after="50.00", savings="50.00", has_unknown_pricing=True
    )

    status, diag = engine.verify_satisfiability_with_z3(
        candidates=[cand_unknown],
        baseline_cost=Decimal("100.00"),
        enforce_at_least_one=True,
    )
    assert status == "Z3_CONSTRAINTS_UNSAT"
    assert diag["rejected_by_invariant_count"] >= 1

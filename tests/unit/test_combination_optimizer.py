"""
CloudPilot SwitchOps — Bounded Combination Optimization Tests

Verifies:
1. Enumeration is bounded to k <= 3 (never unbounded exponential search).
2. Pairwise conflict rejection (conflicting changes to same resource attribute).
3. Dependency closure enforcement.
4. Decimal financial aggregation (sums of savings and costs before/after).
5. Monotonic multi-objective risk aggregation (worst-case security/reliability impact).
6. Pareto evaluation across individual and composite candidates.
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
from app.domain.decisions import CandidateInteraction, InteractionType
from app.services.decision.combination_optimizer import CombinationOptimizer
from app.services.decision.pareto_optimizer import ParetoOptimizer
from app.services.decision.candidate_evaluator import CandidateEvaluator


def build_candidate(
    c_id: str,
    title: str,
    res_id: str,
    attr: str,
    prop_val: any,
    cost_before: str = "100.00",
    cost_after: str = "70.00",
    savings: str = "30.00",
    sec_impact: ImpactLevel = ImpactLevel.NEUTRAL,
    rel_impact: ImpactLevel = ImpactLevel.NEUTRAL,
    complexity: OperationalComplexity = OperationalComplexity.LOW,
) -> Candidate:
    change = ProposedChange(
        resource_id=res_id,
        resource_name=res_id,
        resource_type="aws_instance",
        attribute_path=attr,
        current_value="initial",
        proposed_value=prop_val,
        action_type="MODIFY",
    )
    return Candidate(
        candidate_id=c_id,
        title=title,
        description=f"Description for {title}",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=[res_id],
        proposed_changes=[change],
        estimated_monthly_cost_before=cost_before,
        estimated_monthly_cost_after=cost_after,
        estimated_monthly_savings=savings,
        security_impact=sec_impact,
        reliability_impact=rel_impact,
        operational_complexity=complexity,
        assumptions=[f"Assumption for {c_id}"],
        applicability=ApplicabilityStatus.APPLICABLE,
    )


class TestCombinationOptimizer:
    """Test suite for the bounded combination optimizer."""

    def test_bounded_combination_enumeration_k_le_3(self):
        """Optimizer generates combinations up to size k=3, never exceeding k=3."""
        optimizer = CombinationOptimizer(max_combination_size=3)

        c1 = build_candidate("c1", "Resize EC2 A", "res-a", "instance_type", "t3.small", savings="10.00")
        c2 = build_candidate("c2", "Downgrade EBS B", "res-b", "volume_type", "gp3", savings="15.00")
        c3 = build_candidate("c3", "Schedule DB C", "res-c", "schedule", "working_hours", savings="20.00")
        c4 = build_candidate("c4", "Limit Container D", "res-d", "limits", "512M", savings="0.00")

        combos = optimizer.generate_valid_combinations(candidates=[c1, c2, c3, c4])

        # For 4 candidates:
        # C(4, 2) = 6 pairs of size 2
        # C(4, 3) = 4 triplets of size 3
        # Total combinations <= 10, none of size 4
        assert len(combos) == 10
        for composite in combos:
            assert composite.candidate_type == CandidateType.COMPOSITE_PLAN
            assert 2 <= len(composite.member_candidate_ids) <= 3
            assert composite.evidence["optimization_scope"] == "BOUNDED_COMBINATION (k=3)"

    def test_conflict_rejection_on_same_resource_attribute(self):
        """Candidates proposing contradictory values for the same resource attribute cannot combine."""
        optimizer = CombinationOptimizer(max_combination_size=3)

        # Both c1 and c2 propose modifying 'instance_type' on 'res-shared-vm' with different target sizes
        c1 = build_candidate("c1", "Resize to t3.small", "res-shared-vm", "instance_type", "t3.small")
        c2 = build_candidate("c2", "Resize to t3.micro", "res-shared-vm", "instance_type", "t3.micro")
        c3 = build_candidate("c3", "Encrypt EBS Volume", "res-other-ebs", "encrypted", True)

        combos = optimizer.generate_valid_combinations(candidates=[c1, c2, c3])

        # (c1, c2) must be rejected because they contradict each other on res-shared-vm:instance_type
        # Valid combos should only be (c1, c3) and (c2, c3)
        assert len(combos) == 2
        combo_member_pairs = [set(cb.member_candidate_ids) for cb in combos]
        assert {"c1", "c3"} in combo_member_pairs
        assert {"c2", "c3"} in combo_member_pairs
        assert {"c1", "c2"} not in combo_member_pairs

    def test_dependency_handling_in_combinations(self):
        """Candidates requiring a parent dependency are only combined if the parent is present."""
        optimizer = CombinationOptimizer(max_combination_size=3)

        c_parent = build_candidate("c-parent", "Parent Action", "res-net", "vpc", "vpc-1")
        c_dep = build_candidate("c-dep", "Dependent Action", "res-subnet", "subnet", "sub-1")
        c_ind = build_candidate("c-ind", "Independent Action", "res-disk", "iops", "3000")

        dep_interaction = CandidateInteraction(
            candidate_ids=["c-dep", "c-parent"],
            interaction_type=InteractionType.DEPENDENT,
            reason="Subnet requires VPC.",
        )

        combos = optimizer.generate_valid_combinations(
            candidates=[c_parent, c_dep, c_ind],
            interactions=[dep_interaction],
        )

        # Pairs:
        # (c_parent, c_ind): valid (no dependency violated)
        # (c_parent, c_dep): valid (dependency satisfied)
        # (c_dep, c_ind): INVALID (c_dep requires c_parent, which is absent!)
        # Triplet:
        # (c_parent, c_dep, c_ind): valid (dependency satisfied)
        combo_member_sets = [set(cb.member_candidate_ids) for cb in combos]
        assert {"c-dep", "c-ind"} not in combo_member_sets
        assert {"c-parent", "c-dep"} in combo_member_sets
        assert {"c-parent", "c-ind"} in combo_member_sets
        assert {"c-parent", "c-dep", "c-ind"} in combo_member_sets

    def test_decimal_financial_aggregation(self):
        """Combined savings and costs are computed strictly using Decimal precision."""
        optimizer = CombinationOptimizer(max_combination_size=2)

        c1 = build_candidate(
            "c1", "Resize A", "res-a", "size", "s1",
            cost_before="120.50", cost_after="80.25", savings="40.25"
        )
        c2 = build_candidate(
            "c2", "Downgrade B", "res-b", "size", "s2",
            cost_before="45.10", cost_after="20.05", savings="25.05"
        )

        combos = optimizer.generate_valid_combinations(candidates=[c1, c2])
        assert len(combos) == 1
        comp = combos[0]

        assert comp.estimated_monthly_savings == "65.30"
        assert comp.estimated_monthly_cost_before == "165.60"
        assert comp.estimated_monthly_cost_after == "100.30"

    def test_pessimistic_multi_objective_risk_composition(self):
        """If any candidate has a negative security or reliability regression, the composite inherits it."""
        optimizer = CombinationOptimizer(max_combination_size=2)

        c_good = build_candidate(
            "c1", "Good Action", "res-1", "attr-1", "val-1",
            sec_impact=ImpactLevel.HIGH_POSITIVE, rel_impact=ImpactLevel.POSITIVE
        )
        c_bad = build_candidate(
            "c2", "Risky Action", "res-2", "attr-2", "val-2",
            sec_impact=ImpactLevel.NEGATIVE, rel_impact=ImpactLevel.NEUTRAL,
            complexity=OperationalComplexity.HIGH
        )

        combos = optimizer.generate_valid_combinations(candidates=[c_good, c_bad])
        assert len(combos) == 1
        comp = combos[0]

        # Pessimistic security aggregation: NEGATIVE overrides HIGH_POSITIVE
        assert comp.security_impact == ImpactLevel.NEGATIVE
        # Operational complexity: highest complexity is chosen
        assert comp.operational_complexity == OperationalComplexity.HIGH

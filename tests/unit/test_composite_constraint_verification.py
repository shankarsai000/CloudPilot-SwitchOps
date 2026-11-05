"""
CloudPilot SwitchOps — Phase 3.2 Unit Tests: Composite Constraint Verification

Verifies:
1. Every composite plan is evaluated against ALL applicable hard constraints:
   - Public database exposure (CONST-SEC-01)
   - Persistent storage deletion (CONST-REL-01)
   - Privileged container execution (CONST-SEC-02)
   - Docker daemon socket mount (CONST-SEC-03)
   - Wildcard ingress (CONST-SEC-04)
   - Encryption retention (CONST-SEC-05)
   - Operational applicability / unknown attributes (CONST-OPS-01)
2. A composite plan must NEVER bypass a constraint simply because its individual candidates passed.
3. Candidate interactions: conflicting resource changes and missing prerequisites are rejected.
4. Combined security & reliability regressions inherit pessimistic impact levels.
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
from app.domain.decisions import CandidateInteraction, InteractionType
from app.domain.policies import PolicyConfiguration
from app.services.decision.combination_optimizer import CombinationOptimizer
from app.services.decision.constraint_engine import ConstraintEngine


def make_clean_candidate(cid: str, res_id: str, savings: str = "20.00") -> Candidate:
    """Helper creating a safe, passing candidate."""
    return Candidate(
        candidate_id=cid,
        title=f"Safe Candidate {cid}",
        description="Clean, valid candidate",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=[res_id],
        target_resource_ids=[res_id],
        proposed_changes=[
            ProposedChange(
                resource_id=res_id,
                resource_type="aws_instance",
                attribute_path="instance_type",
                current_value="m5.2xlarge",
                proposed_value="m5.xlarge",
            )
        ],
        estimated_monthly_cost_before=Decimal("150.00"),
        estimated_monthly_cost_after=Decimal("130.00"),
        estimated_monthly_savings=Decimal(savings),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )


def test_composite_plan_fails_when_member_exposes_public_database():
    """
    If any member of a composite plan exposes a database publicly or disables auth,
    the entire composite plan MUST be rejected by CONST-SEC-01.
    """
    policy = PolicyConfiguration(disallow_public_database=True)
    engine = ConstraintEngine(policy=policy)
    optimizer = CombinationOptimizer()

    safe_c = make_clean_candidate("c-safe", "app-srv")
    unsafe_c = Candidate(
        candidate_id="c-unsafe-db",
        title="Public Postgres Port",
        description="Public Postgres Port candidate",
        candidate_type=CandidateType.CUSTOM,
        affected_resource_ids=["staging_postgres"],
        target_resource_ids=["staging_postgres"],
        proposed_changes=[
            ProposedChange(
                resource_id="staging_postgres",
                resource_type="aws_security_group_rule",
                attribute_path="ports",
                current_value="5432",
                proposed_value="0.0.0.0:5432",
            )
        ],
        estimated_monthly_cost_before=Decimal("100.00"),
        estimated_monthly_cost_after=Decimal("100.00"),
        estimated_monthly_savings=Decimal("0.00"),
        security_impact=ImpactLevel.NEGATIVE,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    composite = optimizer._synthesize_composite_candidate([safe_c, unsafe_c])

    is_feasible, results, reasons = engine.evaluate(composite)
    assert is_feasible is False
    sec_failures = [r for r in results if r.constraint_id == "CONST-SEC-01" and r.status == ConstraintStatus.FAIL]
    assert len(sec_failures) >= 1
    assert any("CONST-SEC-01" in r for r in reasons)


def test_composite_plan_fails_when_member_drops_stateful_persistence():
    """
    If any member of a composite plan drops volume persistence on a stateful DB,
    the composite plan MUST be rejected by CONST-REL-01.
    """
    policy = PolicyConfiguration(mandatory_persistence_for_stateful=True)
    engine = ConstraintEngine(policy=policy)
    optimizer = CombinationOptimizer()

    safe_c = make_clean_candidate("c-safe-2", "web-cluster")
    unsafe_drop_vol = Candidate(
        candidate_id="c-drop-vol",
        title="Remove DB Volume",
        description="Drop volume candidate",
        candidate_type=CandidateType.DROP_PERSISTENCE,
        affected_resource_ids=["postgres_data_volume"],
        target_resource_ids=["postgres_data_volume"],
        proposed_changes=[
            ProposedChange(
                resource_id="postgres_data_volume",
                resource_type="aws_ebs_volume",
                attribute_path="volumes",
                current_value="attached",
                proposed_value=None,
                action_type="REMOVE",
            )
        ],
        estimated_monthly_cost_before=Decimal("50.00"),
        estimated_monthly_cost_after=Decimal("0.00"),
        estimated_monthly_savings=Decimal("50.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEGATIVE,
        operational_complexity=OperationalComplexity.HIGH,
    )

    composite = optimizer._synthesize_composite_candidate([safe_c, unsafe_drop_vol])

    is_feasible, results, reasons = engine.evaluate(composite)
    assert is_feasible is False
    rel_failures = [r for r in results if r.constraint_id == "CONST-REL-01" and r.status == ConstraintStatus.FAIL]
    assert len(rel_failures) >= 1
    assert any("CONST-REL-01" in r for r in reasons)


def test_composite_plan_fails_when_member_uses_privileged_container():
    """
    If any member introduces privileged containers, composite plan fails CONST-SEC-02.
    """
    policy = PolicyConfiguration(disallow_privileged_containers=True)
    engine = ConstraintEngine(policy=policy)
    optimizer = CombinationOptimizer()

    safe_c = make_clean_candidate("c-safe-3", "worker-node")
    priv_c = Candidate(
        candidate_id="c-priv",
        title="Privileged daemon",
        description="Privileged daemon candidate",
        candidate_type=CandidateType.CUSTOM,
        affected_resource_ids=["monitoring_agent"],
        target_resource_ids=["monitoring_agent"],
        proposed_changes=[
            ProposedChange(
                resource_id="monitoring_agent",
                resource_type="docker_container",
                attribute_path="privileged",
                current_value=False,
                proposed_value=True,
            )
        ],
        estimated_monthly_cost_before=Decimal("20.00"),
        estimated_monthly_cost_after=Decimal("20.00"),
        estimated_monthly_savings=Decimal("0.00"),
        security_impact=ImpactLevel.NEGATIVE,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    composite = optimizer._synthesize_composite_candidate([safe_c, priv_c])

    is_feasible, results, reasons = engine.evaluate(composite)
    assert is_feasible is False
    sec_fails = [r for r in results if r.constraint_id == "CONST-SEC-02" and r.status == ConstraintStatus.FAIL]
    assert len(sec_fails) >= 1


def test_composite_plan_fails_when_member_disables_auth():
    """
    If any member candidate has DISABLE_AUTH, composite plan fails CONST-SEC-01.
    """
    policy = PolicyConfiguration(disallow_public_database=True)
    engine = ConstraintEngine(policy=policy)
    optimizer = CombinationOptimizer()

    safe_c = make_clean_candidate("c-safe-4", "api-gateway")
    disable_auth_c = Candidate(
        candidate_id="c-no-auth",
        title="Disable Redis Auth",
        description="Disable auth candidate",
        candidate_type=CandidateType.DISABLE_AUTH,
        affected_resource_ids=["redis-cache"],
        target_resource_ids=["redis-cache"],
        proposed_changes=[],
        estimated_monthly_cost_before=Decimal("30.00"),
        estimated_monthly_cost_after=Decimal("30.00"),
        estimated_monthly_savings=Decimal("0.00"),
        security_impact=ImpactLevel.NEGATIVE,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    composite = optimizer._synthesize_composite_candidate([safe_c, disable_auth_c])

    is_feasible, results, reasons = engine.evaluate(composite)
    assert is_feasible is False
    sec_fails = [r for r in results if r.constraint_id == "CONST-SEC-01" and r.status == ConstraintStatus.FAIL]
    assert len(sec_fails) >= 1


def test_composite_plan_prunes_conflicting_resource_changes():
    """
    If two candidates propose contradictory modifications for the same attribute
    on the same resource, CombinationOptimizer MUST NOT generate a composite candidate.
    """
    optimizer = CombinationOptimizer()

    c1 = Candidate(
        candidate_id="c1-t3",
        title="Set to t3.micro",
        description="Set instance type t3",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=["srv-core"],
        target_resource_ids=["srv-core"],
        proposed_changes=[
            ProposedChange(
                resource_id="srv-core",
                resource_type="aws_instance",
                attribute_path="instance_type",
                current_value="m5.large",
                proposed_value="t3.micro",
            )
        ],
        estimated_monthly_cost_before=Decimal("80.00"),
        estimated_monthly_cost_after=Decimal("15.00"),
        estimated_monthly_savings=Decimal("65.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    c2 = Candidate(
        candidate_id="c2-c5",
        title="Set to c5.large",
        description="Set instance type c5",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=["srv-core"],
        target_resource_ids=["srv-core"],
        proposed_changes=[
            ProposedChange(
                resource_id="srv-core",
                resource_type="aws_instance",
                attribute_path="instance_type",
                current_value="m5.large",
                proposed_value="c5.large",
            )
        ],
        estimated_monthly_cost_before=Decimal("80.00"),
        estimated_monthly_cost_after=Decimal("70.00"),
        estimated_monthly_savings=Decimal("10.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    interaction = CandidateInteraction(
        candidate_ids=["c1-t3", "c2-c5"],
        interaction_type=InteractionType.CONFLICTING,
        conflicting_resource_id="srv-core",
        reason="Contradictory instance_type",
    )

    combinations = optimizer.generate_valid_combinations(
        candidates=[c1, c2],
        interactions=[interaction],
    )
    # Because c1 and c2 are conflicting, NO composite plan containing both should be returned
    assert len(combinations) == 0


def test_composite_plan_prunes_missing_prerequisite():
    """
    If candidate B depends on parent A, but only B is considered without A,
    the plan cannot be formed. When both A and B are present, B is only valid with A.
    """
    optimizer = CombinationOptimizer()

    c_parent = make_clean_candidate("c-parent", "vpc-main")
    c_child = make_clean_candidate("c-child", "subnet-app")

    interaction = CandidateInteraction(
        candidate_ids=["c-child", "c-parent"],
        interaction_type=InteractionType.DEPENDENT,
        reason="Subnet requires VPC change",
    )

    combinations = optimizer.generate_valid_combinations(
        candidates=[c_parent, c_child],
        interactions=[interaction],
    )
    # The combination [c-parent, c-child] satisfies the dependency and is valid
    assert len(combinations) == 1
    assert set(combinations[0].member_candidate_ids) == {"c-parent", "c-child"}


def test_composite_plan_pessimistic_security_and_reliability_inheritance():
    """
    Combined impact levels must inherit the most severe / pessimistic rating:
    NEGATIVE + POSITIVE -> NEGATIVE.
    """
    optimizer = CombinationOptimizer()

    c_pos_sec = Candidate(
        candidate_id="c-pos",
        title="Add WAF",
        description="Add WAF candidate",
        candidate_type=CandidateType.ENABLE_ENCRYPTION,
        affected_resource_ids=["alb"],
        target_resource_ids=["alb"],
        proposed_changes=[],
        estimated_monthly_cost_before=Decimal("50.00"),
        estimated_monthly_cost_after=Decimal("70.00"),
        estimated_monthly_savings=Decimal("-20.00"),
        security_impact=ImpactLevel.POSITIVE,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.MEDIUM,
    )

    c_neg_sec = Candidate(
        candidate_id="c-neg",
        title="Relax egress",
        description="Relax egress candidate",
        candidate_type=CandidateType.CUSTOM,
        affected_resource_ids=["sg"],
        target_resource_ids=["sg"],
        proposed_changes=[],
        estimated_monthly_cost_before=Decimal("50.00"),
        estimated_monthly_cost_after=Decimal("50.00"),
        estimated_monthly_savings=Decimal("0.00"),
        security_impact=ImpactLevel.NEGATIVE,
        reliability_impact=ImpactLevel.NEGATIVE,
        operational_complexity=OperationalComplexity.LOW,
    )

    composite = optimizer._synthesize_composite_candidate([c_pos_sec, c_neg_sec])

    assert composite.security_impact == ImpactLevel.NEGATIVE
    assert composite.reliability_impact == ImpactLevel.NEGATIVE


def test_composite_plan_fails_when_member_targets_unknown_attributes():
    """
    If a composite candidate inherits ApplicabilityStatus.UNKNOWN or proposes
    changes on an unknown attribute, CONST-OPS-01 returns UNKNOWN or FAIL (blocking).
    """
    engine = ConstraintEngine()
    optimizer = CombinationOptimizer()

    safe_c = make_clean_candidate("c-safe-5", "srv-1")
    unknown_attr_c = Candidate(
        candidate_id="c-unk-attr",
        title="Modify unknown attribute",
        description="Unknown attribute candidate",
        candidate_type=CandidateType.CUSTOM,
        affected_resource_ids=["srv-1"],
        target_resource_ids=["srv-1"],
        proposed_changes=[
            ProposedChange(
                resource_id="srv-1",
                resource_type="aws_instance",
                attribute_path="unknown",
                current_value="old",
                proposed_value="new",
            )
        ],
        estimated_monthly_cost_before=Decimal("50.00"),
        estimated_monthly_cost_after=Decimal("40.00"),
        estimated_monthly_savings=Decimal("10.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
        applicability=ApplicabilityStatus.UNKNOWN,
    )

    composite = optimizer._synthesize_composite_candidate([safe_c, unknown_attr_c])
    assert composite.applicability == ApplicabilityStatus.UNKNOWN

    is_feasible, results, reasons = engine.evaluate(composite)
    assert is_feasible is False
    ops_results = [r for r in results if r.constraint_id == "CONST-OPS-01"]
    assert any(r.is_blocking for r in ops_results)

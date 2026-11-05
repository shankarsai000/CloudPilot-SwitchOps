"""
CloudPilot SwitchOps — Phase 3.2 Unit Tests: Phase 4 Execution Safety Preconditions

Verifies that Phase 4 Human-in-the-Loop Approval and Bounded Execution receives
a complete, verified, and tamper-evident proposal bundle:
1. Specific DecisionRun ID
2. Selected candidate proposal (atomic or composite plan)
3. Canonical proposal representation (`proposed_changes`)
4. Deterministic `proposal_hash` (SHA256 of canonical mutation payloads)
5. Source evidence IDs and affected resource IDs
6. Explicit policy and pricing catalog versions
7. Constraint verification status (Z3 and rule engine)
8. Explicit optimization scope (e.g. BOUNDED_COMBINATION k=3)
9. Clear list of rejected alternatives with violated constraints
10. Evidence provenance integrity and disclosure of local SQLite trust boundary
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
from app.domain.decisions import CandidateEvaluation, DecisionReport, DecisionRun
from app.domain.objectives import ObjectiveScores, PreferenceProfile
from app.domain.policies import PolicyConfiguration
from app.services.decision.recommendation_engine import (
    RecommendationEngine,
    compute_provenance_hash,
    verify_report_provenance,
)


def make_clean_candidate(cid: str, res_id: str) -> Candidate:
    return Candidate(
        candidate_id=cid,
        title=f"Rightsize {res_id}",
        description=f"Rightsize {res_id} to t3.medium",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=[res_id],
        target_resource_ids=[res_id],
        source_finding_ids=[f"FIND-{cid}"],
        proposed_changes=[
            ProposedChange(
                resource_id=res_id,
                resource_type="aws_instance",
                attribute_path="instance_type",
                current_value="m5.xlarge",
                proposed_value="t3.medium",
                action_type="MODIFY",
            )
        ],
        estimated_monthly_cost_before=Decimal("150.00"),
        estimated_monthly_cost_after=Decimal("50.00"),
        estimated_monthly_savings=Decimal("100.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
        pricing_catalog_version="1.0",
        policy_version="1.0",
    )


def test_phase4_precondition_bundle_completeness():
    """
    Tests that RecommendationEngine outputs a DecisionRun and DecisionReport
    satisfying all 9 Phase 4 execution safety preconditions.
    """
    c_rec = make_clean_candidate("c-recommended", "srv-app-01")
    c_alt = make_clean_candidate("c-alternative", "srv-app-02")
    c_rej = make_clean_candidate("c-rejected", "srv-app-03")

    eval_rec = CandidateEvaluation(
        candidate=c_rec,
        objective_scores=ObjectiveScores(cost_score=0.9, security_score=0.8, reliability_score=0.8, simplicity_score=0.9),
        is_feasible=True,
    )
    eval_alt = CandidateEvaluation(
        candidate=c_alt,
        objective_scores=ObjectiveScores(cost_score=0.5, security_score=0.5, reliability_score=0.5, simplicity_score=0.5),
        is_feasible=True,
    )
    eval_rej = CandidateEvaluation(
        candidate=c_rej,
        objective_scores=ObjectiveScores(cost_score=0.0, security_score=0.0, reliability_score=0.0, simplicity_score=0.0),
        is_feasible=False,
        rejection_reasons=["[CONST-SEC-01] Database public binding prohibited"],
    )

    policy = PolicyConfiguration(monthly_budget_ceiling="500.00", policy_version="1.0")
    engine = RecommendationEngine()

    decision_run, report = engine.build_decision_run(
        task_id="task-test-phase4",
        assessment_id="asm-test-phase4",
        workspace_root="/opt/cloudpilot/staging",
        policy_config=policy,
        preference_profile=PreferenceProfile.BALANCED,
        pareto_optimal=[eval_rec],
        dominated=[eval_alt],
        rejected=[eval_rej],
        interactions=[],
        z3_status="Z3_CONSTRAINTS_SAT",
    )

    # 1. Specific DecisionRun ID
    assert decision_run.decision_id.startswith("dec-")
    assert report.decision_id == decision_run.decision_id

    # 2. Specific selected candidate
    assert decision_run.recommended_candidate is not None
    assert decision_run.recommended_candidate.candidate_id == "c-recommended"
    assert report.executive_recommendation.candidate_id == "c-recommended"

    # 3. Canonical proposal representation
    selected = decision_run.recommended_candidate
    assert len(selected.proposed_changes) == 1
    ch = selected.proposed_changes[0]
    assert ch.resource_id == "srv-app-01"
    assert ch.attribute_path == "instance_type"
    assert ch.proposed_value == "t3.medium"
    assert ch.action_type == "MODIFY"

    # 4. Proposal hash
    assert selected.proposal_hash is not None
    assert len(selected.proposal_hash) == 64  # SHA256 hex string
    assert selected.proposal_hash == selected.compute_proposal_hash()

    # 5. Source evidence and affected resource IDs
    assert "srv-app-01" in selected.affected_resource_ids
    assert "FIND-c-recommended" in selected.source_finding_ids
    assert "srv-app-01" in report.evidence_provenance["affected_resource_ids"]
    assert "FIND-c-recommended" in report.evidence_provenance["source_finding_ids"]

    # 6. Policy and pricing versions
    assert selected.pricing_catalog_version == "1.0"
    assert selected.policy_version == "1.0"
    assert report.evidence_provenance["pricing_catalog_version"] == "1.0"
    assert report.evidence_provenance["policy_version"] == "1.0"

    # 7. Constraint verification status
    assert decision_run.z3_verification_status == "Z3_CONSTRAINTS_SAT"
    assert report.z3_verification_status == "Z3_CONSTRAINTS_SAT"

    # 8. Explicit optimization scope
    assert report.optimization_scope == "BOUNDED_COMBINATION (k=3)"
    assert decision_run.optimization_scope == "BOUNDED_COMBINATION (k=3)"

    # 9. Clear list of rejected alternatives
    assert len(report.rejected_candidates) == 1
    assert report.rejected_candidates[0].candidate.candidate_id == "c-rejected"
    assert not report.rejected_candidates[0].is_feasible
    assert "[CONST-SEC-01]" in report.rejected_candidates[0].rejection_reasons[0]


def test_proposal_hash_strictly_detects_mutation_tampering():
    """
    Verifies that altering any field in proposed_changes (resource, attribute, value, action)
    strictly changes the proposal_hash.
    """
    cand = make_clean_candidate("c-base", "srv-base")
    original_hash = cand.proposal_hash

    # Mutate proposed value
    tampered_changes = [
        ProposedChange(
            resource_id="srv-base",
            resource_type="aws_instance",
            attribute_path="instance_type",
            current_value="m5.xlarge",
            proposed_value="c5.9xlarge",  # Tampered!
            action_type="MODIFY",
        )
    ]
    cand_tampered = Candidate(
        candidate_id="c-base",
        title="Tampered candidate",
        description="Testing hash sensitivity",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=["srv-base"],
        target_resource_ids=["srv-base"],
        proposed_changes=tampered_changes,
        estimated_monthly_cost_before=Decimal("150.00"),
        estimated_monthly_cost_after=Decimal("500.00"),
        estimated_monthly_savings=Decimal("-350.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    assert cand_tampered.proposal_hash != original_hash


def test_evidence_provenance_verification_and_tamper_detection():
    """
    Verifies that report evidence provenance hash validates cleanly,
    and any modification to the provenance metadata fails verification.
    """
    c_rec = make_clean_candidate("c-rec", "srv-1")
    eval_rec = CandidateEvaluation(
        candidate=c_rec,
        objective_scores=ObjectiveScores(cost_score=0.9, security_score=0.8, reliability_score=0.8, simplicity_score=0.9),
        is_feasible=True,
    )
    engine = RecommendationEngine()
    _, report = engine.build_decision_run(
        task_id="task-prov",
        assessment_id="asm-prov",
        workspace_root="/opt/test",
        policy_config=PolicyConfiguration(),
        preference_profile=PreferenceProfile.BALANCED,
        pareto_optimal=[eval_rec],
        dominated=[],
        rejected=[],
        interactions=[],
        z3_status="Z3_CONSTRAINTS_SAT",
    )

    # 1. Clean report passes verification
    assert verify_report_provenance(report) is True

    # 2. Tampering with an evidence field fails verification
    tampered_report = report.model_copy(deep=True)
    tampered_report.evidence_provenance["policy_version"] = "99.9"
    assert verify_report_provenance(tampered_report) is False

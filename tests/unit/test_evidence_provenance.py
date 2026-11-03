"""
CloudPilot SwitchOps — Phase 3.1 Evidence Provenance Integrity & Tamper Detection Tests

Verifies:
1. Deterministic SHA256 provenance hash generation from canonical decision inputs.
2. Sensitivity & tamper detection: changing any finding, resource, policy, or model version invalidates the hash.
3. verify_report_provenance utility returns True for intact reports and False for tampered reports.
4. Synchronization between evidence_provenance and backward-compatible evidence_lineage.
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
from app.domain.decisions import (
    CandidateEvaluation,
    DecisionReport,
    DecisionRun,
    ParetoStatus,
)
from app.domain.objectives import ObjectiveScores, PreferenceProfile
from app.domain.policies import PolicyConfiguration
from app.services.decision.recommendation_engine import (
    RecommendationEngine,
    compute_provenance_hash,
    verify_report_provenance,
)


def make_dummy_evaluation(cand_id: str, savings: str = "25.00") -> CandidateEvaluation:
    cand = Candidate(
        candidate_id=cand_id,
        title=f"Action {cand_id}",
        description="Action description",
        candidate_type=CandidateType.RESIZE_COMPUTE,
        affected_resource_ids=[f"res-{cand_id}"],
        source_finding_ids=[f"find-{cand_id}"],
        estimated_monthly_cost_before="100.00",
        estimated_monthly_cost_after="75.00",
        estimated_monthly_savings=savings,
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
        applicability=ApplicabilityStatus.APPLICABLE,
    )
    scores = ObjectiveScores(
        cost_score=60.0,
        security_score=50.0,
        reliability_score=50.0,
        simplicity_score=100.0,
        model_version="1.1",
    )
    return CandidateEvaluation(
        candidate=cand,
        objective_scores=scores,
        is_feasible=True,
        pareto_status=ParetoStatus.PARETO_OPTIMAL,
    )


class TestEvidenceProvenance:
    """Test suite verifying cryptographic-grade SHA256 evidence provenance and verification."""

    def test_deterministic_provenance_hash_generation(self):
        """Identical inputs produce identical SHA256 provenance digests."""
        data_a = {
            "task_id": "task-100",
            "assessment_id": "asm-100",
            "workspace_root": "samples/staging",
            "policy_version": "1.0",
            "pricing_catalog_version": "1.0",
            "objective_model_version": "1.1",
        }
        data_b = dict(data_a)

        hash_a = compute_provenance_hash(data_a)
        hash_b = compute_provenance_hash(data_b)

        assert len(hash_a) == 64  # Valid SHA-256 hex string
        assert hash_a == hash_b

    def test_tamper_detection_in_provenance(self):
        """Modifying any finding, resource, policy, or catalog version alters the hash."""
        base_data = {
            "task_id": "task-100",
            "assessment_id": "asm-100",
            "workspace_root": "samples/staging",
            "policy_version": "1.0",
            "pricing_catalog_version": "1.0",
            "objective_model_version": "1.1",
            "source_finding_ids": ["FIN-001", "SEC-001"],
        }
        base_hash = compute_provenance_hash(base_data)

        # 1. Modify finding IDs
        tampered_finding = dict(base_data)
        tampered_finding["source_finding_ids"] = ["FIN-001", "SEC-002"]
        assert compute_provenance_hash(tampered_finding) != base_hash

        # 2. Modify policy version
        tampered_policy = dict(base_data)
        tampered_policy["policy_version"] = "2.0"
        assert compute_provenance_hash(tampered_policy) != base_hash

        # 3. Modify objective model version
        tampered_obj = dict(base_data)
        tampered_obj["objective_model_version"] = "1.0"
        assert compute_provenance_hash(tampered_obj) != base_hash

    def test_verify_report_provenance_valid_and_tampered(self):
        """verify_report_provenance verifies genuine reports and catches post-generation tampering."""
        recommender = RecommendationEngine()
        ev1 = make_dummy_evaluation("c1")
        ev2 = make_dummy_evaluation("c2")

        policy = PolicyConfiguration()
        decision_run, report = recommender.build_decision_run(
            task_id="task-test-prov",
            assessment_id="asm-test-prov",
            workspace_root="samples/staging",
            policy_config=policy,
            preference_profile=PreferenceProfile.BALANCED,
            pareto_optimal=[ev1, ev2],
            dominated=[],
            rejected=[],
            interactions=[],
            z3_status="Z3_CONSTRAINTS_SAT",
        )

        assert report.provenance_hash is not None
        assert len(report.provenance_hash) == 64
        # Verify genuine report
        assert verify_report_provenance(report) is True

        # Tamper with evidence provenance in the report
        tampered_report = report.model_copy(deep=True)
        tampered_report.evidence_provenance["policy_version"] = "99.9"
        assert verify_report_provenance(tampered_report) is False

    def test_evidence_provenance_and_lineage_synchronization(self):
        """DecisionReport keeps evidence_provenance and evidence_lineage synchronized for backward compatibility."""
        data = {
            "decision_id": "dec-1",
            "task_id": "t1",
            "assessment_id": "a1",
            "workspace_root": "samples/staging",
            "preference_profile": PreferenceProfile.BALANCED,
            "policy_config": PolicyConfiguration(),
            "status": "COMPLETED",
            "z3_verification_status": "Z3_CONSTRAINTS_SAT",
            "evidence_provenance": {"key": "value_provenance"},
        }
        report = DecisionReport(**data)
        assert report.evidence_provenance == {"key": "value_provenance"}
        assert report.evidence_lineage == {"key": "value_provenance"}

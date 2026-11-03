"""
CloudPilot SwitchOps — Unit Tests: Candidate Interactions & Conflict Detection

Tests detection of conflicting, redundant, and dependent candidate modifications.
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
from app.domain.decisions import InteractionType
from app.services.decision.candidate_evaluator import CandidateEvaluator


def test_conflicting_changes_detected():
    evaluator = CandidateEvaluator()

    cand1 = Candidate(
        candidate_id="cand-downsize",
        title="Downsize Compute",
        description="Downsize to t3.medium",
        candidate_type=CandidateType.RIGHTSIZE_COMPUTE,
        target_resource_ids=["app_instance"],
        proposed_changes=[
            ProposedChange(
                resource_id="app_instance",
                resource_type="aws_instance",
                attribute_path="instance_type",
                current_value="t3.xlarge",
                proposed_value="t3.medium",
            )
        ],
        estimated_monthly_cost_before=Decimal("150.00"),
        estimated_monthly_cost_after=Decimal("40.00"),
        estimated_monthly_savings=Decimal("110.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    cand2 = Candidate(
        candidate_id="cand-upsize",
        title="Upsize Compute",
        description="Upsize to c5.2xlarge for performance",
        candidate_type=CandidateType.CUSTOM,
        target_resource_ids=["app_instance"],
        proposed_changes=[
            ProposedChange(
                resource_id="app_instance",
                resource_type="aws_instance",
                attribute_path="instance_type",
                current_value="t3.xlarge",
                proposed_value="c5.2xlarge",
            )
        ],
        estimated_monthly_cost_before=Decimal("150.00"),
        estimated_monthly_cost_after=Decimal("250.00"),
        estimated_monthly_savings=Decimal("-100.00"),
        security_impact=ImpactLevel.NEUTRAL,
        reliability_impact=ImpactLevel.POSITIVE,
        operational_complexity=OperationalComplexity.LOW,
    )

    interactions = evaluator.detect_interactions([cand1, cand2])
    assert len(interactions) >= 1
    conflict = next(i for i in interactions if i.interaction_type == InteractionType.CONFLICTING)
    assert conflict.conflicting_resource_id == "app_instance"
    assert "cand-downsize" in conflict.candidate_ids
    assert "cand-upsize" in conflict.candidate_ids


def test_redundant_changes_detected():
    evaluator = CandidateEvaluator()

    cand1 = Candidate(
        candidate_id="cand-a",
        title="Enable Encryption A",
        description="Enable storage encryption",
        candidate_type=CandidateType.ENABLE_STORAGE_ENCRYPTION,
        target_resource_ids=["db_main"],
        proposed_changes=[
            ProposedChange(
                resource_id="db_main",
                resource_type="aws_db_instance",
                attribute_path="storage_encrypted",
                current_value=False,
                proposed_value=True,
            )
        ],
        estimated_monthly_cost_before=Decimal("100.00"),
        estimated_monthly_cost_after=Decimal("100.00"),
        estimated_monthly_savings=Decimal("0.00"),
        security_impact=ImpactLevel.HIGHLY_POSITIVE,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    cand2 = Candidate(
        candidate_id="cand-b",
        title="Enable Encryption B",
        description="Duplicate enable encryption",
        candidate_type=CandidateType.ENABLE_STORAGE_ENCRYPTION,
        target_resource_ids=["db_main"],
        proposed_changes=[
            ProposedChange(
                resource_id="db_main",
                resource_type="aws_db_instance",
                attribute_path="storage_encrypted",
                current_value=False,
                proposed_value=True,
            )
        ],
        estimated_monthly_cost_before=Decimal("100.00"),
        estimated_monthly_cost_after=Decimal("100.00"),
        estimated_monthly_savings=Decimal("0.00"),
        security_impact=ImpactLevel.HIGHLY_POSITIVE,
        reliability_impact=ImpactLevel.NEUTRAL,
        operational_complexity=OperationalComplexity.LOW,
    )

    interactions = evaluator.detect_interactions([cand1, cand2])
    assert any(i.interaction_type == InteractionType.REDUNDANT for i in interactions)

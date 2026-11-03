"""
CloudPilot SwitchOps — Unit Tests: Candidate Generator

Tests deterministic generation of candidate infrastructure modifications
from Phase 2 discovered inventory and findings.
"""

from decimal import Decimal
from pathlib import Path
import pytest

from app.domain.candidates import Candidate, CandidateType, ImpactLevel
from app.domain.policies import PolicyConfiguration
from app.services.decision.candidate_generator import CandidateGenerator
from app.services.discovery.engine import InfrastructureDiscoveryEngine
from app.services.specialists.finops_specialist import FinOpsSpecialist
from app.services.specialists.secops_specialist import SecOpsSpecialist


@pytest.fixture
def staging_discovery_and_findings():
    engine = InfrastructureDiscoveryEngine()
    inventory = engine.discover("samples/staging", task_id="test-task-gen")
    finops = FinOpsSpecialist().analyze(inventory, task_id="test-task-gen")
    secops = SecOpsSpecialist().analyze(inventory, task_id="test-task-gen")
    findings = finops.findings + secops.all_findings
    return inventory, findings


def test_candidate_generation_from_staging(staging_discovery_and_findings):
    inventory, findings = staging_discovery_and_findings
    generator = CandidateGenerator()
    candidates = generator.generate_candidates(
        inventory=inventory,
        findings=findings,
        include_adversarial_test_candidates=True,
    )

    assert len(candidates) > 0

    # Verify key expected candidates exist
    types = [c.candidate_type for c in candidates]
    assert CandidateType.RIGHTSIZE_COMPUTE in types
    assert CandidateType.RESTRICT_SECURITY_GROUP in types
    assert CandidateType.TERMINATE_UNATTACHED_STORAGE in types
    assert CandidateType.ENABLE_STORAGE_ENCRYPTION in types
    assert CandidateType.CONTAINER_SECURITY in types
    assert CandidateType.MULTI_AZ_DEPLOYMENT in types

    # Verify rightsize compute candidate has positive estimated savings
    rightsize = next(c for c in candidates if c.candidate_type == CandidateType.RIGHTSIZE_COMPUTE)
    assert Decimal(rightsize.estimated_monthly_savings) > Decimal("0.00")
    assert Decimal(rightsize.estimated_monthly_cost_after) < Decimal(rightsize.estimated_monthly_cost_before)
    assert rightsize.security_impact in [ImpactLevel.NEUTRAL, ImpactLevel.POSITIVE]

    # Verify adversarial candidate exists
    adversarial = [c for c in candidates if c.candidate_id.startswith("cand-unsafe")]
    assert len(adversarial) >= 2


def test_candidate_generation_determinism_and_idempotence(staging_discovery_and_findings):
    inventory, findings = staging_discovery_and_findings
    generator = CandidateGenerator()

    run1 = generator.generate_candidates(inventory=inventory, findings=findings, include_adversarial_test_candidates=False)
    run2 = generator.generate_candidates(inventory=inventory, findings=findings, include_adversarial_test_candidates=False)

    assert len(run1) == len(run2)
    for c1, c2 in zip(run1, run2):
        assert c1.candidate_id == c2.candidate_id
        assert c1.candidate_type == c2.candidate_type
        assert c1.estimated_monthly_savings == c2.estimated_monthly_savings
        assert c1.security_impact == c2.security_impact
        assert c1.reliability_impact == c2.reliability_impact
        assert len(c1.proposed_changes) == len(c2.proposed_changes)


def test_candidate_generation_with_empty_findings(staging_discovery_and_findings):
    inventory, _ = staging_discovery_and_findings
    generator = CandidateGenerator()

    # When no findings exist, generator should still produce valid base candidates from inventory
    candidates = generator.generate_candidates(
        inventory=inventory,
        findings=[],
        include_adversarial_test_candidates=False,
    )
    assert isinstance(candidates, list)

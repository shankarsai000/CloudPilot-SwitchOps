"""
Tests for Phase 11: Real AWS Read-Only Production Agent.

Verifies:
1. Agent operates strictly in READ_ONLY mode.
2. Direct cloud mutations are unconditionally rejected with ReadOnlyViolationError.
3. Multi-service inventory discovery covers all 8 core services (EC2, EBS, RDS, VPC, ELB, ECS_EKS, S3, IAM).
4. Telemetry and cost normalization into CloudPilot canonical structures.
5. Critical tier-1 resources are protected from any modification.
6. Identifies real cost optimization candidates with declarative GitOps HCL.
7. Security findings (e.g. overpermissive IAM) are detected and reported.
8. Credential vault integration and adapter health verification.
"""

from __future__ import annotations

import pytest

from providers.aws import AWSProductionAdapter
from providers.credentials import CredentialVault
from providers.models import (
    CloudProvider,
    HealthStatus,
    ProviderMode,
    ReadOnlyViolationError,
)
from trueforge.aws_agent import (
    AWSReadOnlyAgent,
    AWSRecommendationReport,
    AWSResource,
    AWSServiceType,
    get_aws_readonly_agent,
)


@pytest.fixture
def credential_vault() -> CredentialVault:
    """Fixture providing credential vault with default credentials."""
    return CredentialVault()


@pytest.fixture
def aws_adapter(credential_vault: CredentialVault) -> AWSProductionAdapter:
    """Fixture providing AWSProductionAdapter in READ_ONLY mode."""
    return AWSProductionAdapter(mode=ProviderMode.READ_ONLY, vault=credential_vault)


@pytest.fixture
def aws_agent(aws_adapter: AWSProductionAdapter, credential_vault: CredentialVault) -> AWSReadOnlyAgent:
    """Fixture providing AWSReadOnlyAgent."""
    return AWSReadOnlyAgent(adapter=aws_adapter, vault=credential_vault, account_id="987654321098")


class TestAWSReadOnlyAgentSafetyInvariants:
    """Tests safety invariants ensuring agent cannot execute direct mutations."""

    def test_agent_is_strictly_read_only(self, aws_agent: AWSReadOnlyAgent) -> None:
        assert aws_agent.is_read_only is True
        assert aws_agent.adapter.mode == ProviderMode.READ_ONLY

    def test_agent_rejects_mutating_adapter(self, credential_vault: CredentialVault) -> None:
        mutating_adapter = AWSProductionAdapter(mode=ProviderMode.READ_WRITE, vault=credential_vault)
        with pytest.raises(ReadOnlyViolationError):
            AWSReadOnlyAgent(adapter=mutating_adapter, vault=credential_vault)

    def test_direct_mutation_raises_read_only_violation(self, aws_agent: AWSReadOnlyAgent) -> None:
        with pytest.raises(ReadOnlyViolationError) as exc_info:
            aws_agent.execute_mutation(
                resource_id="i-01a2b3c4d5e6f001",
                action="terminate_instance",
                parameters={},
            )
        assert "strictly in READ_ONLY mode" in str(exc_info.value)
        assert "Direct mutations" in str(exc_info.value)

    def test_adapter_health_check(self, aws_agent: AWSReadOnlyAgent) -> None:
        report = aws_agent.adapter.health_check()
        assert report.status == HealthStatus.HEALTHY
        assert report.details["is_read_only"] is True


class TestAWSMultiServiceDiscovery:
    """Tests 8-service inventory discovery and normalization."""

    def test_discover_all_8_services(self, aws_agent: AWSReadOnlyAgent) -> None:
        resources = aws_agent.discover_all_services()
        assert len(resources) >= 12

        discovered_services = {r.service for r in resources}
        expected_services = {
            AWSServiceType.EC2,
            AWSServiceType.EBS,
            AWSServiceType.RDS,
            AWSServiceType.VPC,
            AWSServiceType.ELB,
            AWSServiceType.ECS_EKS,
            AWSServiceType.S3,
            AWSServiceType.IAM,
        }
        assert discovered_services == expected_services

    def test_ec2_normalization_and_metrics(self, aws_agent: AWSReadOnlyAgent) -> None:
        resources = aws_agent.discover_all_services()
        ec2_items = [r for r in resources if r.service == AWSServiceType.EC2]
        assert len(ec2_items) >= 3

        for ec2 in ec2_items:
            assert ec2.resource_id.startswith("i-")
            assert ec2.region == "us-east-1"
            assert ec2.monthly_cost_usd > 0
            assert "cpu_avg_pct" in ec2.utilization_metrics

    def test_ebs_orphan_volume_detection(self, aws_agent: AWSReadOnlyAgent) -> None:
        resources = aws_agent.discover_all_services()
        ebs_items = [r for r in resources if r.service == AWSServiceType.EBS]
        orphan_vols = [v for v in ebs_items if v.state == "available" and v.is_idle]
        assert len(orphan_vols) >= 1
        assert orphan_vols[0].monthly_cost_usd > 0

    def test_rds_database_clustering(self, aws_agent: AWSReadOnlyAgent) -> None:
        resources = aws_agent.discover_all_services()
        rds_items = [r for r in resources if r.service == AWSServiceType.RDS]
        assert any(r.resource_id == "rds-pg-auth-cluster" and r.is_critical for r in rds_items)
        assert any(r.resource_id == "rds-mysql-staging-replica" and r.is_oversized for r in rds_items)

    def test_iam_security_findings(self, aws_agent: AWSReadOnlyAgent) -> None:
        resources = aws_agent.discover_all_services()
        iam_items = [r for r in resources if r.service == AWSServiceType.IAM]
        overpermissive = [i for i in iam_items if len(i.security_findings) > 0]
        assert len(overpermissive) >= 1
        assert "Overpermissive" in overpermissive[0].security_findings[0]


class TestAWSRecommendationEngine:
    """Tests cost analysis, critical dependency protection, and GitOps HCL generation."""

    def test_cost_analysis_and_report_generation(self, aws_agent: AWSReadOnlyAgent) -> None:
        report: AWSRecommendationReport = aws_agent.analyze_costs_and_recommendations()

        assert report.agent_mode == "READ_ONLY"
        assert report.total_resources_discovered >= 12
        assert report.total_monthly_spend_usd > 1000.0
        assert report.total_potential_monthly_savings_usd > 200.0
        assert len(report.candidates) >= 4
        assert len(report.protected_critical_resources) >= 4

    def test_critical_tier1_resources_are_protected(self, aws_agent: AWSReadOnlyAgent) -> None:
        report = aws_agent.analyze_costs_and_recommendations()
        candidate_ids = {c.resource_id for c in report.candidates}

        # Verify critical tier-1 resources are NEVER targeted for modification
        assert "rds-pg-auth-cluster" not in candidate_ids
        assert "i-01a2b3c4d5e6f001" not in candidate_ids
        assert "alb-public-ingress" not in candidate_ids
        assert "vpc-0abc1234" not in candidate_ids

    def test_candidates_contain_valid_gitops_hcl(self, aws_agent: AWSReadOnlyAgent) -> None:
        report = aws_agent.analyze_costs_and_recommendations()
        for cand in report.candidates:
            assert cand.estimated_monthly_savings > 0
            assert cand.gitops_remediation_hcl is not None
            assert len(cand.gitops_remediation_hcl) > 10
            # Blast radius score must be safe (< 0.5)
            assert cand.blast_radius_score <= 0.3

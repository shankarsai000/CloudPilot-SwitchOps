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
from fastapi.testclient import TestClient

from main import app
from providers.aws import AWSProductionAdapter
from providers.credentials import CredentialVault, TemporaryTokenBroker
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


class TestAWSLiveAdapterAndCredentials:
    """Tests AWS Boto3 adapter discovery and STS AssumeRole token broker."""

    def test_sts_token_broker_issuance_and_masking(self) -> None:
        token = TemporaryTokenBroker.issue_aws_sts_credentials()
        assert token.provider == CloudProvider.AWS
        assert token.token_type == "AWS_STS_ASSUME_ROLE"
        assert token.access_key_id is not None
        assert token.access_key_id.startswith("ASIA")
        assert token.secret_access_key is not None
        # String representation must mask secrets
        assert str(token.token) == "***MASKED_SECRET***"
        assert str(token.secret_access_key) == "***MASKED_SECRET***"
        assert token.is_expired is False

    def test_vault_boto3_session_creation(self, credential_vault: CredentialVault) -> None:
        session = credential_vault.get_boto3_session(CloudProvider.AWS)
        assert session is not None
        assert session.region_name is not None

    def test_adapter_all_8_service_discovery_methods(self, aws_adapter: AWSProductionAdapter) -> None:
        ec2 = aws_adapter.discover_ec2()
        assert len(ec2) >= 3
        ebs = aws_adapter.discover_ebs()
        assert len(ebs) >= 2
        rds = aws_adapter.discover_rds()
        assert len(rds) >= 2
        vpc = aws_adapter.discover_vpc()
        assert len(vpc) >= 2
        elb = aws_adapter.discover_elb()
        assert len(elb) >= 2
        ecs_eks = aws_adapter.discover_ecs_eks()
        assert len(ecs_eks) >= 2
        s3 = aws_adapter.discover_s3()
        assert len(s3) >= 2
        iam = aws_adapter.discover_iam()
        assert len(iam) >= 2

        all_svcs = aws_adapter.discover_all_services()
        assert set(all_svcs.keys()) == {"EC2", "EBS", "RDS", "VPC", "ELB", "ECS_EKS", "S3", "IAM"}

        flattened = aws_adapter.discover_resources()
        assert len(flattened) >= 17


class TestAWSIAMPolicySimulation:
    """Tests IAM policy simulation for read-only vs mutating actions."""

    def test_simulate_iam_action_read_allowed(self, aws_agent: AWSReadOnlyAgent) -> None:
        result = aws_agent.simulate_iam_action(action_name="ec2:DescribeInstances", resource_arn="*")
        assert result["allowed"] is True
        assert result["eval_decision"] == "allowed"

    def test_simulate_iam_action_write_denied(self, aws_agent: AWSReadOnlyAgent) -> None:
        result = aws_agent.simulate_iam_action(
            action_name="ec2:TerminateInstances",
            resource_arn="arn:aws:ec2:ap-south-1:123456789012:instance/i-01a2b3c4d5e6f001",
        )
        assert result["allowed"] is False
        assert "Deny" in result["eval_decision"]


class TestAWSAgentAPIRoutes:
    """Tests FastAPI REST endpoints for AWS Read-Only Agent under /api/v1/providers/aws/agent."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_api_discover_endpoint(self, client: TestClient) -> None:
        response = client.post("/api/v1/providers/aws/agent/discover", json={"region": "ap-south-1"})
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "aws"
        assert data["mode"] == "READ_ONLY"
        assert data["total_resources"] >= 12
        assert "EC2" in data["service_breakdown"]
        assert "IAM" in data["service_breakdown"]

    def test_api_analyze_endpoint(self, client: TestClient) -> None:
        response = client.post("/api/v1/providers/aws/agent/analyze", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["agent_mode"] == "READ_ONLY"
        assert data["total_monthly_spend_usd"] > 0
        assert data["total_potential_monthly_savings_usd"] > 0
        assert len(data["candidates"]) >= 4

    def test_api_mutation_safety_block_endpoint(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/providers/aws/agent/mutate",
            json={
                "resource_id": "i-01a2b3c4d5e6f001",
                "action": "terminate_instance",
                "parameters": {},
            },
        )
        # MUST return 403 Forbidden with ReadOnlyViolationError
        assert response.status_code == 403
        data = response.json()
        error_content = str(data)
        assert "ReadOnlyViolationError" in error_content
        assert "strictly in READ_ONLY mode" in error_content
        assert "CloudPilot strictly forbids direct AWS mutations" in error_content

    def test_api_simulate_iam_endpoint(self, client: TestClient) -> None:
        # Read action
        resp_read = client.post(
            "/api/v1/providers/aws/agent/simulate-iam",
            json={"action": "ec2:DescribeInstances", "resource_arn": "*"},
        )
        assert resp_read.status_code == 200
        assert resp_read.json()["allowed"] is True

        # Mutating action
        resp_write = client.post(
            "/api/v1/providers/aws/agent/simulate-iam",
            json={"action": "ec2:StopInstances", "resource_arn": "arn:aws:ec2:*:*:instance/*"},
        )
        assert resp_write.status_code == 200
        assert resp_write.json()["allowed"] is False

    def test_api_pipeline_endpoint(self, client: TestClient) -> None:
        response = client.post("/api/v1/providers/aws/agent/pipeline", json={"region": "ap-south-1"})
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "READ_ONLY"
        assert "pipeline_stages" in data
        stages = data["pipeline_stages"]
        assert stages["m1_discovery"]["status"] == "COMPLETED"
        assert stages["m2_cost_analysis"]["status"] == "COMPLETED"
        assert stages["m6_digital_twin_simulation"]["status"] == "COMPLETED"
        assert stages["m9_decision"]["status"] == "GATED_APPROVAL_REQUIRED"


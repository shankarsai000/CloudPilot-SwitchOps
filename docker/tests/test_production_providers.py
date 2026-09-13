"""
Test Suite for Production Multi-Cloud Providers, Capability Discovery,
Resilience, Error Normalization, and GitOps Lifecycle (Phase 8).
"""

import pytest
from fastapi.testclient import TestClient

from main import app
from providers.aws import AWSProductionAdapter
from providers.azure import AzureProductionAdapter
from providers.credentials import (
    CredentialVault,
    LeastPrivilegeValidator,
    SecretString,
    TemporaryTokenBroker,
    get_credential_vault,
)
from providers.gcp import GCPProductionAdapter
from providers.gitops_terraform import (
    GitOpsStage,
    GitOpsTerraformEngine,
    get_gitops_engine,
)
from providers.kubernetes import KubernetesProductionAdapter
from providers.models import (
    Capability,
    CloudProvider,
    HealthStatus,
    ProviderAuthError,
    ProviderError,
    ProviderMode,
    ProviderRateLimitError,
    ProviderResourceNotFoundError,
    ProviderTransientError,
    ReadOnlyViolationError,
    UnsupportedCapabilityError,
)
from providers.registry import (
    ProductionProviderRegistry,
    get_production_provider_registry,
)
from providers.resilience import (
    CircuitBreaker,
    CircuitBreakerState,
    RequestTracer,
    RetryPolicy,
    TokenBucketRateLimiter,
)


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def registry():
    """Provider registry fixture."""
    return get_production_provider_registry()


@pytest.fixture
def vault():
    """Credential vault fixture."""
    return get_credential_vault()


# ============================================================================
# 1. Capability Discovery & Provider Adapters
# ============================================================================

def test_provider_registry_initialization(registry):
    """All 4 initial cloud providers must be registered with stable interfaces."""
    providers = registry.list_providers()
    provider_names = {p.provider for p in providers}
    assert CloudProvider.AWS in provider_names
    assert CloudProvider.GCP in provider_names
    assert CloudProvider.AZURE in provider_names
    assert CloudProvider.KUBERNETES in provider_names


def test_aws_initializes_in_read_only_mode(registry):
    """CRITICAL SAFETY CONSTRAINT: AWS provider must initialize in READ_ONLY mode by default."""
    aws_adapter = registry.get_adapter(CloudProvider.AWS)
    assert aws_adapter.mode == ProviderMode.READ_ONLY
    assert aws_adapter.has_capability(Capability.DISCOVERY_COMPUTE) is True
    # Mutating capabilities must be blocked in READ_ONLY mode
    assert aws_adapter.has_capability(Capability.EXECUTE_SCALE) is False


def test_aws_read_only_blocks_mutating_execution(registry):
    """Attempting mutating operation on read-only AWS raises ReadOnlyViolationError."""
    aws_adapter = registry.get_adapter(CloudProvider.AWS)
    with pytest.raises(ReadOnlyViolationError) as exc_info:
        aws_adapter.execute_action(
            target_id="i-12345",
            action="SCALE_DOWN",
        )
    assert "READ_ONLY mode" in str(exc_info.value)
    assert exc_info.value.capability == Capability.EXECUTE_SCALE


def test_aws_read_only_discovery_succeeds(registry):
    """Discovery on AWS in read-only mode operates smoothly."""
    aws_adapter = registry.get_adapter(CloudProvider.AWS)
    resources = aws_adapter.discover_resources()
    assert len(resources) >= 3
    assert any(r["type"] == "compute:ec2" for r in resources)


def test_capability_discovery_matrix(registry):
    """Each provider exposes only capabilities that are actually supported."""
    gcp_caps = registry.get_capabilities(CloudProvider.GCP)
    k8s_caps = registry.get_capabilities(CloudProvider.KUBERNETES)

    assert Capability.DISCOVERY_COMPUTE in gcp_caps
    assert Capability.DISCOVERY_K8S in gcp_caps
    assert Capability.EXECUTE_SCALE in gcp_caps

    assert Capability.DISCOVERY_K8S in k8s_caps
    assert Capability.EXECUTE_K8S_SCALE in k8s_caps
    assert Capability.DISCOVERY_COMPUTE not in k8s_caps  # K8s adapter does not discover bare compute VMs


def test_agent_unsupported_operation_strictly_blocked(registry):
    """Never allow an agent to execute an unsupported operation."""
    with pytest.raises(UnsupportedCapabilityError) as exc_info:
        # K8s adapter does not support DISCOVERY_DATABASE
        registry.validate_agent_operation(
            provider=CloudProvider.KUBERNETES,
            capability=Capability.DISCOVERY_DATABASE,
        )
    assert exc_info.value.error_code == "UNSUPPORTED_CAPABILITY"


# ============================================================================
# 2. Secure Credential Management & Rotation
# ============================================================================

def test_secret_string_masking():
    """SecretString must never leak plaintext secrets in str or repr."""
    secret = SecretString("SuperSecretCloudKey12345!")
    assert str(secret) == "***MASKED_SECRET***"
    assert repr(secret) == "***MASKED_SECRET***"
    assert secret.get_secret_value() == "SuperSecretCloudKey12345!"


def test_temporary_credentials_issuance(vault):
    """Temporary token brokers generate time-bound credentials with valid TTL."""
    aws_temp = TemporaryTokenBroker.issue_aws_sts_credentials(ttl_seconds=1800)
    assert aws_temp.provider == CloudProvider.AWS
    assert aws_temp.is_expired is False
    assert aws_temp.seconds_until_expiration > 1700
    assert str(aws_temp.token) == "***MASKED_SECRET***"

    k8s_temp = TemporaryTokenBroker.issue_k8s_service_account_token()
    assert k8s_temp.provider == CloudProvider.KUBERNETES
    assert k8s_temp.token_type == "K8S_SERVICE_ACCOUNT_TOKEN"


def test_zero_downtime_credential_rotation(vault):
    """Credential rotation updates vault atomically and records audit fingerprint."""
    new_creds = {
        "auth_type": "STS_ASSUME_ROLE",
        "region": "us-west-2",
        "role_arn": "arn:aws:iam::123456789012:role/CloudPilotRotatedRole",
        "access_key": "AKIAUPDATEDEXAMPLE",
        "secret_key": "UpdatedSecretKey12345",
    }
    success = vault.rotate_credentials(
        provider=CloudProvider.AWS,
        new_credentials=new_creds,
        operator="secops-lead",
    )
    assert success is True

    active = vault.get_credentials(CloudProvider.AWS)
    assert active["region"] == "us-west-2"
    assert str(active["secret_key"]) == "***MASKED_SECRET***"

    history = vault.get_rotation_history(CloudProvider.AWS)
    assert len(history) >= 1
    assert history[-1]["operator"] == "secops-lead"
    assert history[-1]["status"] == "SUCCESS"


def test_least_privilege_validator():
    """Least privilege validator detects destructive actions and read-only violations."""
    compliant_actions = ["ec2:DescribeInstances", "s3:ListBucket", "cloudwatch:GetMetricData"]
    is_ok, violations = LeastPrivilegeValidator.validate_permissions(
        provider=CloudProvider.AWS,
        granted_actions=compliant_actions,
        is_read_only=True,
    )
    assert is_ok is True
    assert len(violations) == 0

    wildcard_actions = ["*", "iam:*", "ec2:DeleteVolume"]
    is_ok, violations = LeastPrivilegeValidator.validate_permissions(
        provider=CloudProvider.AWS,
        granted_actions=wildcard_actions,
        is_read_only=True,
    )
    assert is_ok is False
    assert any("Excessive wildcard" in v for v in violations)
    assert any("Write action" in v for v in violations)


# ============================================================================
# 3. Resilience Engine: Rate Limiter, Circuit Breaker & Retries
# ============================================================================

def test_token_bucket_rate_limiter():
    """Rate limiter allows bursts within capacity and throttles when exhausted."""
    limiter = TokenBucketRateLimiter(
        provider=CloudProvider.AWS,
        capacity=5.0,
        refill_rate=1.0,
    )
    # 5 acquisitions should pass immediately
    for _ in range(5):
        assert limiter.acquire(1.0, wait=False) is True

    # 6th acquisition exceeds capacity and raises ProviderRateLimitError
    with pytest.raises(ProviderRateLimitError) as exc_info:
        limiter.acquire(1.0, wait=False)
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds > 0.0


def test_circuit_breaker_trips_and_recovers():
    """Circuit breaker trips to OPEN on consecutive failures and recovers via HALF_OPEN."""
    cb = CircuitBreaker(
        provider=CloudProvider.GCP,
        failure_threshold=3,
        recovery_timeout=0.2,  # 200ms recovery for snappy test
        half_open_success_threshold=2,
    )
    assert cb.state == CircuitBreakerState.CLOSED

    # Record 3 failures to trip breaker
    for _ in range(3):
        cb.record_failure(is_transient=True)

    assert cb.state == CircuitBreakerState.OPEN
    assert cb.can_execute() is False

    # Immediate call fast-fails
    with pytest.raises(ProviderTransientError) as exc_info:
        cb.execute(lambda: "never_called")
    assert "Circuit breaker for gcp is OPEN" in str(exc_info.value)

    # Wait for recovery timeout to transition to HALF_OPEN
    import time
    time.sleep(0.25)
    assert cb.can_execute() is True
    assert cb.state == CircuitBreakerState.HALF_OPEN

    # Two successful probes close the circuit
    cb.record_success()
    cb.record_success()
    assert cb.state == CircuitBreakerState.CLOSED


def test_retry_policy_with_exponential_backoff():
    """Retry policy retries transient errors and succeeds upon recovery."""
    policy = RetryPolicy(max_retries=3, base_delay=0.01)
    call_count = 0

    def flaky_service():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ProviderTransientError(CloudProvider.AZURE, "Transient connection reset")
        return "SUCCESS_AFTER_RETRIES"

    result = policy.execute(flaky_service)
    assert result == "SUCCESS_AFTER_RETRIES"
    assert call_count == 3


def test_retry_policy_fast_fails_non_retryable_errors():
    """Retry policy does not retry non-retryable authentication or authorization errors."""
    policy = RetryPolicy(max_retries=3, base_delay=0.01)
    call_count = 0

    def fatal_auth_service():
        nonlocal call_count
        call_count += 1
        raise ProviderAuthError(CloudProvider.AWS, "Invalid credentials")

    with pytest.raises(ProviderAuthError):
        policy.execute(fatal_auth_service)
    assert call_count == 1  # Fast fail without retry


# ============================================================================
# 4. Provider Error Normalization
# ============================================================================

def test_aws_error_normalization(registry):
    """Boto3 style exceptions normalize to standard platform exceptions."""
    aws_adapter = registry.get_adapter(CloudProvider.AWS)

    class MockClientError(Exception):
        response = {"Error": {"Code": "AuthFailure", "Message": "AWS was unable to validate the provided credentials"}}

    normalized = aws_adapter.normalize_exception(MockClientError())
    assert isinstance(normalized, ProviderAuthError)
    assert normalized.retryable is False

    class MockThrottlingError(Exception):
        response = {"Error": {"Code": "RequestLimitExceeded", "Message": "Rate exceeded"}}

    normalized = aws_adapter.normalize_exception(MockThrottlingError())
    assert isinstance(normalized, ProviderRateLimitError)
    assert normalized.retryable is True


def test_k8s_error_normalization(registry):
    """Kubernetes client ApiException normalizes to standard platform exceptions."""
    k8s_adapter = registry.get_adapter(CloudProvider.KUBERNETES)

    class MockK8s404(Exception):
        status = 404
        def __str__(self):
            return "Deployment not found in namespace default"

    normalized = k8s_adapter.normalize_exception(MockK8s404())
    assert isinstance(normalized, ProviderResourceNotFoundError)


# ============================================================================
# 5. Terraform / GitOps Lifecycle with Safety Inheritance
# ============================================================================

def test_gitops_lifecycle_end_to_end():
    """
    Test full 6-stage lifecycle:
    Plan -> Review -> Approval -> Apply -> Verify -> Rollback
    """
    engine = get_gitops_engine()

    # 1. PLAN
    plan_record = engine.stage_plan(
        workspace="prod-us-central1",
        provider=CloudProvider.GCP,
        target_resource="gce-analytics-worker-01",
        action="SCALE_DOWN",
        estimated_cost_delta=-45.0,
    )
    plan_id = plan_record.plan.plan_id
    assert plan_record.current_stage == GitOpsStage.PLAN

    # 2. REVIEW
    review_record = engine.stage_review(plan_id)
    assert review_record.current_stage == GitOpsStage.REVIEW
    assert review_record.stage_history[-1]["status"] == "PASSED"

    # 3. APPROVAL (Evaluate & Force Approve for automated test run)
    approval_record = engine.stage_approval(plan_id, operator="eng-lead", force_auto=True)
    assert approval_record.current_stage == GitOpsStage.APPROVAL
    assert approval_record.approval_status == "APPROVED"

    # 4. APPLY
    apply_record = engine.stage_apply(plan_id, operator="eng-lead")
    assert apply_record.current_stage == GitOpsStage.APPLY
    assert apply_record.apply_result["status"] == "SUCCESS"

    # 5. VERIFY
    verify_record = engine.stage_verify(plan_id)
    assert verify_record.current_stage == GitOpsStage.VERIFY
    assert verify_record.verification_report["overall_status"] == "VERIFIED_SUCCESS"

    # 6. ROLLBACK
    rollback_record = engine.stage_rollback(plan_id, reason="Drift restoration")
    assert rollback_record.current_stage == GitOpsStage.ROLLBACK
    assert rollback_record.rollback_record["status"] == "SUCCESS"


def test_gitops_apply_blocked_on_aws_read_only():
    """GitOps Apply must be strictly blocked on AWS due to read-only safety mode."""
    engine = get_gitops_engine()

    record = engine.stage_plan(
        workspace="aws-prod",
        provider=CloudProvider.AWS,
        target_resource="payment-service-primary",
        action="MODIFY_INSTANCE_TYPE",
    )
    plan_id = record.plan.plan_id
    engine.stage_review(plan_id)
    engine.stage_approval(plan_id, operator="lead", force_auto=True)

    with pytest.raises(ReadOnlyViolationError) as exc_info:
        engine.stage_apply(plan_id)
    assert "READ_ONLY mode" in str(exc_info.value)


# ============================================================================
# 6. REST API Endpoints
# ============================================================================

def test_api_list_providers(client):
    """GET /api/v1/providers returns all registered multi-cloud providers."""
    resp = client.get("/api/v1/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 4
    providers = {p["provider"]: p for p in data}
    assert providers["aws"]["is_read_only"] is True


def test_api_provider_capabilities(client):
    """GET /api/v1/providers/{provider}/capabilities returns explicit capability list."""
    resp = client.get("/api/v1/providers/gcp/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert "discovery:compute" in data["supported_capabilities"]
    assert data["mode"] == "read_write"


def test_api_provider_health(client):
    """GET /api/v1/providers/{provider}/health returns deep connectivity health."""
    resp = client.get("/api/v1/providers/kubernetes/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["credentials_valid"] is True


def test_api_credential_rotation(client):
    """POST /api/v1/providers/{provider}/credentials/rotate updates credentials safely."""
    payload = {
        "operator": "devops-engineer",
        "new_credentials": {
            "auth_type": "WORKLOAD_IDENTITY",
            "project_id": "cloudpilot-gcp-updated",
            "client_email": "cloudpilot-new@project.iam.gserviceaccount.com",
            "private_key": "MOCK-ROTATED-KEY",
        },
    }
    resp = client.post("/api/v1/providers/gcp/credentials/rotate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"


def test_api_gitops_pipeline(client):
    """POST /api/v1/providers/gitops/pipeline executes plan creation."""
    payload = {
        "stage": "plan",
        "workspace": "prod-k8s",
        "provider": "kubernetes",
        "target_resource": "k8s://production/namespaces/default/deployments/frontend-web",
        "action": "SCALE_DEPLOYMENT",
        "estimated_cost_delta": -20.0,
    }
    resp = client.post("/api/v1/providers/gitops/pipeline", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_stage"] == "plan"
    assert data["plan"]["provider"] == "kubernetes"


def test_api_resilience_metrics(client):
    """GET /api/v1/providers/resilience/metrics returns rate limiter & circuit breaker status."""
    resp = client.get("/api/v1/providers/resilience/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "aws" in data
    assert "rate_limiter" in data["aws"]
    assert "circuit_breaker" in data["aws"]
    assert data["aws"]["circuit_breaker"]["state"] == "CLOSED"

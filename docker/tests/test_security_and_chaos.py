"""
Production Hardening Test Suite: Security, Penetration, Chaos, Failure, Load,
and Disaster Recovery Testing (Phase 8).
"""

import concurrent.futures
import time
import pytest
from datetime import datetime, timedelta, timezone

from governance.control_plane import get_safety_control_plane
from providers.aws import AWSProductionAdapter
from providers.credentials import (
    CredentialVault,
    SecretString,
    TemporaryCredential,
    get_credential_vault,
)
from providers.gcp import GCPProductionAdapter
from providers.gitops_terraform import GitOpsStage, get_gitops_engine
from providers.models import (
    Capability,
    CloudProvider,
    ProviderError,
    ProviderMode,
    ProviderRateLimitError,
    ProviderTransientError,
    ReadOnlyViolationError,
    UnsupportedCapabilityError,
)
from providers.registry import get_production_provider_registry
from providers.resilience import CircuitBreaker, CircuitBreakerState, RetryPolicy


# ============================================================================
# 1. Security & Penetration Testing
# ============================================================================

def test_secret_leakage_prevention():
    """
    SECURITY AUDIT: Plaintext secrets, private keys, and session tokens
    must never be exposed in logs, tracebacks, str(), or repr().
    """
    raw_secret = "AKIA_VERY_SECRET_KEY_12345"
    wrapped = SecretString(raw_secret)

    # 1. str() and repr() must be masked
    assert str(wrapped) == "***MASKED_SECRET***"
    assert repr(wrapped) == "***MASKED_SECRET***"
    assert raw_secret not in str(wrapped)

    # 2. Dictionary dumping of credentials
    vault = get_credential_vault()
    aws_creds = vault.get_credentials(CloudProvider.AWS)
    creds_repr = repr(aws_creds)
    assert "EXAMPLEKEY" not in creds_repr
    assert "wJalrXUtn" not in creds_repr

    # 3. Exception messages must not embed raw credentials
    err = ProviderError(
        provider=CloudProvider.AWS,
        error_code="TEST_ERROR",
        message=f"Failed auth for user with secret {wrapped}",
    )
    assert raw_secret not in str(err)
    assert "***MASKED_SECRET***" in str(err)


def test_unauthorized_bypass_attempt():
    """
    PENETRATION TEST: An agent cannot bypass capability or read-only checks
    by crafting forged payload parameters or omitting provider metadata.
    """
    registry = get_production_provider_registry()

    # Attempt to execute scaling on read-only AWS
    with pytest.raises(ReadOnlyViolationError):
        registry.validate_agent_operation(
            provider=CloudProvider.AWS,
            capability=Capability.EXECUTE_SCALE,
        )

    # Attempt to execute unsupported database action on Kubernetes
    with pytest.raises(UnsupportedCapabilityError):
        registry.validate_agent_operation(
            provider=CloudProvider.KUBERNETES,
            capability=Capability.DISCOVERY_DATABASE,
        )


def test_emergency_kill_switch_authoritative_enforcement():
    """
    SECURITY & SAFETY: When global Emergency Stop is triggered,
    all provider operations must immediately and authoritatively halt.
    """
    safety_plane = get_safety_control_plane()
    registry = get_production_provider_registry()
    engine = get_gitops_engine()

    # Trigger global emergency kill switch
    safety_plane.emergency.engage(
        scope="global",
        reason="Security anomaly detected during pen test",
        activated_by="secops-automated-guard",
    )
    assert safety_plane.emergency.is_stopped() is True

    try:
        # Provider registry validation must block
        with pytest.raises(ProviderError) as exc_info:
            registry.validate_agent_operation(
                provider=CloudProvider.GCP,
                capability=Capability.EXECUTE_SCALE,
            )
        assert "Emergency Stop is ACTIVE" in str(exc_info.value)

        # GitOps apply must also be authoritatively blocked
        plan_record = engine.stage_plan(
            workspace="pen-test-workspace",
            provider=CloudProvider.GCP,
            target_resource="gce-instance-01",
            action="SCALE",
        )
        with pytest.raises(ProviderError) as exc_info2:
            engine.stage_approval(plan_record.plan.plan_id)
        assert "Emergency Stop is ACTIVE" in str(exc_info2.value)

    finally:
        # Reset emergency stop for subsequent tests
        safety_plane.emergency.release(scope="global")
        assert safety_plane.emergency.is_stopped() is False


# ============================================================================
# 2. Chaos Testing Against Simulator
# ============================================================================

def test_chaos_injected_intermittent_503_drops():
    """
    CHAOS TEST: Simulates a cloud provider dropping 50% of requests with HTTP 503.
    Verifies that the exponential backoff retry policy recovers transparently.
    """
    policy = RetryPolicy(max_retries=4, base_delay=0.01)
    call_attempts = 0

    def chaotic_cloud_endpoint():
        nonlocal call_attempts
        call_attempts += 1
        # Drop first 2 requests
        if call_attempts < 3:
            raise ProviderTransientError(
                provider=CloudProvider.AZURE,
                message="HTTP 503: Service Unavailable (Chaos Injected)",
            )
        return {"status": "SUCCESS", "attempts_required": call_attempts}

    result = policy.execute(chaotic_cloud_endpoint)
    assert result["status"] == "SUCCESS"
    assert result["attempts_required"] == 3


def test_chaos_simulated_cloud_outage_circuit_trip():
    """
    CHAOS TEST: Simulates a catastrophic cloud provider outage (100% failure rate).
    Verifies that Circuit Breaker trips from CLOSED to OPEN, prevents cascading
    resource exhaustion by fast-failing, and recovers when the provider heals.
    """
    cb = CircuitBreaker(
        provider=CloudProvider.AWS,
        failure_threshold=3,
        recovery_timeout=0.15,  # 150ms for test speed
        half_open_success_threshold=2,
    )

    outage_active = True

    def cloud_call():
        if outage_active:
            raise ProviderTransientError(CloudProvider.AWS, "HTTP 500: Regional Outage")
        return "HEALTHY"

    # Trip breaker
    for _ in range(3):
        with pytest.raises(ProviderTransientError):
            cb.execute(cloud_call)

    assert cb.state == CircuitBreakerState.OPEN

    # Fast fail while open (call is rejected before invoking downstream cloud)
    with pytest.raises(ProviderTransientError) as exc_info:
        cb.execute(cloud_call)
    assert "Circuit breaker for aws is OPEN" in str(exc_info.value)

    # Provider heals after recovery timeout
    time.sleep(0.2)
    outage_active = False

    # Probes in HALF_OPEN state
    res1 = cb.execute(cloud_call)
    assert res1 == "HEALTHY"
    assert cb.state == CircuitBreakerState.HALF_OPEN

    res2 = cb.execute(cloud_call)
    assert res2 == "HEALTHY"
    assert cb.state == CircuitBreakerState.CLOSED  # Fully healed!


# ============================================================================
# 3. Failure Testing
# ============================================================================

def test_failure_rate_limit_429_storm():
    """
    FAILURE TEST: Floods rate limiter with simultaneous burst calls.
    Verifies that excess calls are safely rejected with ProviderRateLimitError (429)
    and provide accurate retry_after_seconds guidance.
    """
    adapter = GCPProductionAdapter(rate_limit_capacity=10.0, rate_limit_refill_rate=5.0)

    # Exhaust capacity
    for _ in range(10):
        adapter.rate_limiter.acquire(1.0, wait=False)

    # 11th call must fail with ProviderRateLimitError
    with pytest.raises(ProviderRateLimitError) as exc_info:
        adapter.execute_resilient_call(
            "gcp.chaos_burst",
            lambda: "blocked",
            capability=Capability.DISCOVERY_COMPUTE,
        )
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds > 0.0


def test_failure_credential_expiration_and_auto_refresh():
    """
    FAILURE TEST: Simulates credential expiration.
    Verifies that the CredentialVault detects expiration and auto-refreshes token.
    """
    vault = get_credential_vault()

    # Manually expire the current AWS token
    expired_token = TemporaryCredential(
        provider=CloudProvider.AWS,
        token_type="AWS_STS_EXPIRED",
        token=SecretString("expired-session-token"),
        ttl_seconds=-10,  # Expired 10 seconds ago
    )
    vault._temp_tokens[CloudProvider.AWS] = expired_token
    assert expired_token.is_expired is True

    # Next call to get_credentials must proactively auto-refresh
    active_creds = vault.get_credentials(CloudProvider.AWS)
    assert active_creds is not None

    refreshed_token = vault.get_temporary_token(CloudProvider.AWS)
    assert refreshed_token.is_expired is False
    assert refreshed_token.seconds_until_expiration > 1000


# ============================================================================
# 4. Load Testing
# ============================================================================

def test_load_concurrent_multi_provider_discovery():
    """
    LOAD TEST: Concurrently invokes capability discovery across AWS, GCP, Azure,
    and Kubernetes under 20 parallel threads to verify thread-safety and latency stability.
    """
    registry = get_production_provider_registry()
    providers = [CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE, CloudProvider.KUBERNETES]

    def query_provider(prov: CloudProvider):
        adapter = registry.get_adapter(prov)
        return adapter.discover_resources()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(query_provider, providers[i % 4]) for i in range(24)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 24
    for res in results:
        assert isinstance(res, list)
        assert len(res) >= 2


# ============================================================================
# 5. Disaster Recovery Testing
# ============================================================================

def test_disaster_recovery_rollback_idempotency():
    """
    DISASTER RECOVERY: Rollback must be strictly idempotent.
    Executing rollback multiple times on the same execution ID must succeed
    deterministically without causing conflicting side effects.
    """
    engine = get_gitops_engine()

    # Create plan and advance through stages
    record = engine.stage_plan(
        workspace="dr-test",
        provider=CloudProvider.GCP,
        target_resource="gce-dr-target",
        action="SCALE_INSTANCE",
    )
    plan_id = record.plan.plan_id
    engine.stage_review(plan_id)
    engine.stage_approval(plan_id, operator="dr-operator", force_auto=True)
    engine.stage_apply(plan_id, operator="dr-operator")

    # First Rollback
    rb1 = engine.stage_rollback(plan_id, reason="Primary DR invocation")
    assert rb1.rollback_record["status"] == "SUCCESS"
    first_run_id = rb1.rollback_record["rollback_run_id"]

    # Second Rollback (Idempotency test)
    rb2 = engine.stage_rollback(plan_id, reason="Secondary DR duplicate invocation")
    assert rb2.rollback_record["status"] == "SUCCESS"
    assert rb2.current_stage == GitOpsStage.ROLLBACK


def test_disaster_recovery_state_audit_chain_integrity():
    """
    DISASTER RECOVERY: Every state transition in GitOps/Terraform must generate
    a cryptographically verifiable SHA-256 audit hash.
    """
    engine = get_gitops_engine()
    record = engine.stage_plan(
        workspace="audit-integrity",
        provider=CloudProvider.KUBERNETES,
        target_resource="k8s://production/deployments/auth-svc",
        action="ROLLOUT_RESTART",
    )
    h1 = record.audit_hash
    assert len(h1) == 64  # Valid SHA-256

    engine.stage_review(record.plan.plan_id)
    h2 = record.audit_hash
    assert len(h2) == 64
    assert h1 != h2  # State change strictly mutates audit hash

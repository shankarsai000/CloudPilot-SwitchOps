"""
Base Production Provider Adapter Interface and Resilient Execution Harness.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, TypeVar

from providers.credentials import CredentialVault, get_credential_vault
from providers.models import (
    Capability,
    CloudProvider,
    HealthCheckResult,
    HealthStatus,
    ProviderError,
    ProviderMode,
    ProviderTransientError,
    ReadOnlyViolationError,
    UnsupportedCapabilityError,
    is_mutating_capability,
)
from providers.resilience import (
    CircuitBreaker,
    RequestTracer,
    RetryPolicy,
    TokenBucketRateLimiter,
)

logger = logging.getLogger("cloudpilot.providers.base")

T = TypeVar("T")


class BaseProductionProviderAdapter(ABC):
    """
    Abstract production provider adapter with built-in:
    - Strict capability enforcement
    - Read-only protection guard (AWS default)
    - Token-bucket rate limiting
    - Three-state circuit breaker
    - Exponential backoff with jitter
    - Tracing & correlation propagation
    - Provider error normalization
    """

    def __init__(
        self,
        provider: CloudProvider,
        mode: ProviderMode = ProviderMode.READ_WRITE,
        vault: Optional[CredentialVault] = None,
        rate_limit_capacity: float = 60.0,
        rate_limit_refill_rate: float = 20.0,
        circuit_failure_threshold: int = 3,
        circuit_recovery_timeout: float = 5.0,
        max_retries: int = 3,
    ) -> None:
        self.provider = provider
        self.mode = mode
        self.vault = vault or get_credential_vault()

        # Resilience harness
        self.rate_limiter = TokenBucketRateLimiter(
            provider=provider,
            capacity=rate_limit_capacity,
            refill_rate=rate_limit_refill_rate,
        )
        self.circuit_breaker = CircuitBreaker(
            provider=provider,
            failure_threshold=circuit_failure_threshold,
            recovery_timeout=circuit_recovery_timeout,
        )
        self.retry_policy = RetryPolicy(
            max_retries=max_retries,
            base_delay=0.05,
            max_delay=1.0,
        )

    @property
    @abstractmethod
    def supported_capabilities(self) -> set[Capability]:
        """Return the exact set of capabilities physically supported by this adapter."""
        pass

    def has_capability(self, capability: Capability) -> bool:
        """Return True if capability is supported and permitted by current mode."""
        if capability not in self.supported_capabilities:
            return False
        if self.mode == ProviderMode.READ_ONLY and is_mutating_capability(capability):
            return False
        return True

    def assert_capability(self, capability: Capability, trace_id: Optional[str] = None) -> None:
        """
        Assert that requested capability is supported and not blocked by read-only mode.
        Raises UnsupportedCapabilityError or ReadOnlyViolationError if violated.
        """
        if capability not in self.supported_capabilities:
            raise UnsupportedCapabilityError(
                provider=self.provider,
                capability=capability,
                trace_id=trace_id,
            )

        if self.mode == ProviderMode.READ_ONLY and is_mutating_capability(capability):
            raise ReadOnlyViolationError(
                provider=self.provider,
                capability=capability,
                trace_id=trace_id,
            )

    @abstractmethod
    def normalize_exception(self, exc: Exception, trace_id: Optional[str] = None) -> ProviderError:
        """Translate raw provider SDK errors (boto3, google, azure, k8s) into normalized ProviderError."""
        pass

    def execute_resilient_call(
        self,
        operation_name: str,
        func: Callable[..., T],
        *args: Any,
        capability: Optional[Capability] = None,
        trace_id: Optional[str] = None,
        tokens_cost: float = 1.0,
        **kwargs: Any,
    ) -> T:
        """
        Execute provider call through rate limiter, circuit breaker, retries, and error normalizer.
        """
        tid = trace_id or RequestTracer.generate_trace_id()

        # Step 1: Capability & Read-Only validation
        if capability:
            self.assert_capability(capability, trace_id=tid)

        # Step 2: Rate limiting check
        self.rate_limiter.acquire(tokens=tokens_cost, wait=False)

        # Step 3: Call with Circuit Breaker and Retries
        def _invoke() -> T:
            try:
                return self.circuit_breaker.execute(func, *args, **kwargs)
            except ProviderError:
                raise
            except Exception as raw_exc:
                normalized = self.normalize_exception(raw_exc, trace_id=tid)
                raise normalized from raw_exc

        return self.retry_policy.execute(_invoke)

    @abstractmethod
    def health_check(self, trace_id: Optional[str] = None) -> HealthCheckResult:
        """Execute deep health check against provider credentials and API."""
        pass

    @abstractmethod
    def discover_resources(self, trace_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Discover live cloud resources from provider."""
        pass

    @abstractmethod
    def execute_action(
        self,
        target_id: str,
        action: str,
        parameters: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute mutating action against provider infrastructure."""
        pass

    @abstractmethod
    def rollback_action(
        self,
        execution_id: str,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Rollback previous action on provider."""
        pass

    def get_status_summary(self) -> dict[str, Any]:
        """Return consolidated summary of adapter health, mode, and resilience metrics."""
        return {
            "provider": self.provider.value,
            "mode": self.mode.value,
            "is_read_only": self.mode == ProviderMode.READ_ONLY,
            "capabilities": [c.value for c in self.supported_capabilities],
            "rate_limiter": self.rate_limiter.get_metrics(),
            "circuit_breaker": self.circuit_breaker.get_metrics(),
        }

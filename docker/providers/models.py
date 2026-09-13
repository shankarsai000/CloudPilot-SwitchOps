"""
Production Cloud Provider Data Models, Enums, and Normalized Exceptions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class CloudProvider(str, Enum):
    """Supported cloud and platform infrastructure providers."""
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    KUBERNETES = "kubernetes"


class ProviderMode(str, Enum):
    """Operational mode for provider adapter."""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class Capability(str, Enum):
    """Discrete capabilities that can be exposed by provider adapters."""
    # Discovery Capabilities
    DISCOVERY_COMPUTE = "discovery:compute"
    DISCOVERY_STORAGE = "discovery:storage"
    DISCOVERY_DATABASE = "discovery:database"
    DISCOVERY_NETWORK = "discovery:network"
    DISCOVERY_K8S = "discovery:k8s"

    # Billing & Cost Capabilities
    BILLING_INGESTION = "billing:ingestion"
    COST_FORECAST = "cost:forecast"

    # Mutating Execution Capabilities
    EXECUTE_SCALE = "execute:scale"
    EXECUTE_RESTART = "execute:restart"
    EXECUTE_TERMINATE = "execute:terminate"
    EXECUTE_K8S_SCALE = "execute:k8s:scale"
    EXECUTE_K8S_ROLLOUT = "execute:k8s:rollout"
    EXECUTE_TERRAFORM = "execute:terraform"

    # Rollback Capabilities
    ROLLBACK_ACTION = "rollback:action"
    ROLLBACK_TERRAFORM = "rollback:terraform"
    ROLLBACK_K8S = "rollback:k8s"


MUTATING_CAPABILITIES: set[Capability] = {
    Capability.EXECUTE_SCALE,
    Capability.EXECUTE_RESTART,
    Capability.EXECUTE_TERMINATE,
    Capability.EXECUTE_K8S_SCALE,
    Capability.EXECUTE_K8S_ROLLOUT,
    Capability.EXECUTE_TERRAFORM,
    Capability.ROLLBACK_ACTION,
    Capability.ROLLBACK_TERRAFORM,
    Capability.ROLLBACK_K8S,
}


def is_mutating_capability(capability: Capability) -> bool:
    """Return True if capability modifies infrastructure state."""
    return capability in MUTATING_CAPABILITIES


# ============================================================================
# Normalized Exception Hierarchy
# ============================================================================

class ProviderError(Exception):
    """Base exception for all normalized provider errors."""

    def __init__(
        self,
        provider: CloudProvider,
        error_code: str,
        message: str,
        retryable: bool = False,
        trace_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(f"[{provider.value.upper()}:{error_code}] {message}")
        self.provider = provider
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        self.trace_id = trace_id
        self.details = details or {}


class ProviderAuthError(ProviderError):
    """Raised when authentication fails or credentials are invalid/expired."""

    def __init__(
        self,
        provider: CloudProvider,
        message: str = "Invalid or expired provider credentials",
        trace_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            provider=provider,
            error_code="AUTH_FAILED",
            message=message,
            retryable=False,
            trace_id=trace_id,
            details=details,
        )


class ProviderRateLimitError(ProviderError):
    """Raised when the provider API throttles requests (HTTP 429 / RateExceeded)."""

    def __init__(
        self,
        provider: CloudProvider,
        message: str = "API rate limit exceeded",
        retry_after_seconds: float = 1.0,
        trace_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        merged_details = details or {}
        merged_details["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            provider=provider,
            error_code="RATE_LIMIT_EXCEEDED",
            message=message,
            retryable=True,
            trace_id=trace_id,
            details=merged_details,
        )
        self.retry_after_seconds = retry_after_seconds


class ProviderQuotaExceededError(ProviderError):
    """Raised when cloud account quotas or regional limits are exceeded."""

    def __init__(
        self,
        provider: CloudProvider,
        message: str = "Provider quota or resource limit exceeded",
        trace_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            provider=provider,
            error_code="QUOTA_EXCEEDED",
            message=message,
            retryable=False,
            trace_id=trace_id,
            details=details,
        )


class ProviderResourceNotFoundError(ProviderError):
    """Raised when a requested resource does not exist on the provider."""

    def __init__(
        self,
        provider: CloudProvider,
        resource_id: str,
        message: Optional[str] = None,
        trace_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        msg = message or f"Resource '{resource_id}' not found on provider"
        super().__init__(
            provider=provider,
            error_code="RESOURCE_NOT_FOUND",
            message=msg,
            retryable=False,
            trace_id=trace_id,
            details=details,
        )
        self.resource_id = resource_id


class ProviderPermissionDeniedError(ProviderError):
    """Raised when IAM or RBAC explicitly denies an action."""

    def __init__(
        self,
        provider: CloudProvider,
        message: str = "Permission denied by provider IAM/RBAC policy",
        trace_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            provider=provider,
            error_code="PERMISSION_DENIED",
            message=message,
            retryable=False,
            trace_id=trace_id,
            details=details,
        )


class ProviderTransientError(ProviderError):
    """Raised on transient network faults, 500/502/503/504 errors, or timeouts."""

    def __init__(
        self,
        provider: CloudProvider,
        message: str = "Transient provider failure or connection timeout",
        trace_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            provider=provider,
            error_code="TRANSIENT_ERROR",
            message=message,
            retryable=True,
            trace_id=trace_id,
            details=details,
        )


class UnsupportedCapabilityError(ProviderError):
    """Raised when an agent requests an operation not supported by the provider."""

    def __init__(
        self,
        provider: CloudProvider,
        capability: Capability,
        message: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        msg = message or f"Provider '{provider.value}' does not support capability '{capability.value}'"
        super().__init__(
            provider=provider,
            error_code="UNSUPPORTED_CAPABILITY",
            message=msg,
            retryable=False,
            trace_id=trace_id,
            details={"requested_capability": capability.value},
        )
        self.capability = capability


class ReadOnlyViolationError(ProviderError):
    """Raised when attempting a mutating execution on a read-only provider (e.g. AWS)."""

    def __init__(
        self,
        provider: CloudProvider,
        capability: Capability,
        message: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        msg = message or (
            f"Provider '{provider.value}' is running in READ_ONLY mode. "
            f"Execution of mutating capability '{capability.value}' is blocked by safety policy."
        )
        super().__init__(
            provider=provider,
            error_code="READ_ONLY_VIOLATION",
            message=msg,
            retryable=False,
            trace_id=trace_id,
            details={"requested_capability": capability.value, "mode": "read_only"},
        )
        self.capability = capability


# ============================================================================
# Request & Health Models
# ============================================================================

class HealthStatus(str, Enum):
    """Health check evaluation outcome."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheckResult(BaseModel):
    """Detailed health check outcome for a provider."""
    provider: CloudProvider
    status: HealthStatus
    latency_ms: float = Field(ge=0.0)
    mode: ProviderMode
    capabilities_available: list[Capability]
    credentials_valid: bool
    details: dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProviderRequestContext(BaseModel):
    """Correlation and tracing context for provider calls."""
    trace_id: str
    provider: CloudProvider
    operation: str
    target_resource: Optional[str] = None
    operator: str = "cloudpilot-system"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProviderSummary(BaseModel):
    """Consolidated provider status for capability discovery."""
    provider: CloudProvider
    name: str
    mode: ProviderMode
    status: HealthStatus
    supported_capabilities: list[Capability]
    is_read_only: bool
    credential_type: str
    latency_ms: float

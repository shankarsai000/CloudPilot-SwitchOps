"""
CloudPilot Production Cloud Providers Package.
Supports AWS (read-only by default), GCP, Azure, and Kubernetes with
capability discovery, secure credentials, resilience, error normalization,
and GitOps/Terraform lifecycle integration.
"""

from providers.models import (
    Capability,
    CloudProvider,
    HealthCheckResult,
    HealthStatus,
    ProviderAuthError,
    ProviderError,
    ProviderMode,
    ProviderPermissionDeniedError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderResourceNotFoundError,
    ProviderSummary,
    ProviderTransientError,
    ReadOnlyViolationError,
    UnsupportedCapabilityError,
)
from providers.credentials import (
    CredentialVault,
    LeastPrivilegeValidator,
    SecretString,
    TemporaryCredential,
    TemporaryTokenBroker,
    get_credential_vault,
)
from providers.resilience import (
    CircuitBreaker,
    CircuitBreakerState,
    RequestTracer,
    RetryPolicy,
    TokenBucketRateLimiter,
)
from providers.base import BaseProductionProviderAdapter
from providers.aws import AWSProductionAdapter
from providers.gcp import GCPProductionAdapter
from providers.azure import AzureProductionAdapter
from providers.kubernetes import KubernetesProductionAdapter
from providers.gitops_terraform import (
    GitOpsExecutionRecord,
    GitOpsPlan,
    GitOpsStage,
    GitOpsTerraformEngine,
    get_gitops_engine,
)
from providers.registry import (
    ProductionProviderRegistry,
    get_production_provider_registry,
)

__all__ = [
    "Capability",
    "CloudProvider",
    "HealthCheckResult",
    "HealthStatus",
    "ProviderAuthError",
    "ProviderError",
    "ProviderMode",
    "ProviderPermissionDeniedError",
    "ProviderQuotaExceededError",
    "ProviderRateLimitError",
    "ProviderResourceNotFoundError",
    "ProviderSummary",
    "ProviderTransientError",
    "ReadOnlyViolationError",
    "UnsupportedCapabilityError",
    "CredentialVault",
    "LeastPrivilegeValidator",
    "SecretString",
    "TemporaryCredential",
    "TemporaryTokenBroker",
    "get_credential_vault",
    "CircuitBreaker",
    "CircuitBreakerState",
    "RequestTracer",
    "RetryPolicy",
    "TokenBucketRateLimiter",
    "BaseProductionProviderAdapter",
    "AWSProductionAdapter",
    "GCPProductionAdapter",
    "AzureProductionAdapter",
    "KubernetesProductionAdapter",
    "GitOpsExecutionRecord",
    "GitOpsPlan",
    "GitOpsStage",
    "GitOpsTerraformEngine",
    "get_gitops_engine",
    "ProductionProviderRegistry",
    "get_production_provider_registry",
]

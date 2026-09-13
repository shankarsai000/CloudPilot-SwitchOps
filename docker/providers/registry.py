"""
Production Provider Adapter Registry & Dynamic Capability Discovery Manager.
"""

from __future__ import annotations

import logging
from typing import Optional

from governance.control_plane import get_safety_control_plane
from providers.aws import AWSProductionAdapter
from providers.azure import AzureProductionAdapter
from providers.base import BaseProductionProviderAdapter
from providers.credentials import get_credential_vault
from providers.gcp import GCPProductionAdapter
from providers.kubernetes import KubernetesProductionAdapter
from providers.models import (
    Capability,
    CloudProvider,
    HealthStatus,
    ProviderError,
    ProviderMode,
    ProviderSummary,
    ReadOnlyViolationError,
    UnsupportedCapabilityError,
    is_mutating_capability,
)

logger = logging.getLogger("cloudpilot.providers.registry")


class ProductionProviderRegistry:
    """
    Central registry for production multi-cloud adapters.
    Guarantees strict capability discovery and pre-execution safety validation.
    """

    def __init__(self) -> None:
        self._adapters: dict[CloudProvider, BaseProductionProviderAdapter] = {}
        self.vault = get_credential_vault()
        self.safety_plane = get_safety_control_plane()
        self._init_default_adapters()

    def _init_default_adapters(self) -> None:
        """Register initial providers: AWS, GCP, Azure, Kubernetes."""
        # AWS starts in READ_ONLY mode by default
        self._adapters[CloudProvider.AWS] = AWSProductionAdapter(
            mode=ProviderMode.READ_ONLY,
            vault=self.vault,
        )
        self._adapters[CloudProvider.GCP] = GCPProductionAdapter(
            mode=ProviderMode.READ_WRITE,
            vault=self.vault,
        )
        self._adapters[CloudProvider.AZURE] = AzureProductionAdapter(
            mode=ProviderMode.READ_WRITE,
            vault=self.vault,
        )
        self._adapters[CloudProvider.KUBERNETES] = KubernetesProductionAdapter(
            mode=ProviderMode.READ_WRITE,
            vault=self.vault,
        )

    def get_adapter(self, provider: CloudProvider) -> BaseProductionProviderAdapter:
        """Retrieve registered adapter for provider."""
        if provider not in self._adapters:
            raise ProviderError(
                provider=provider,
                error_code="UNREGISTERED_PROVIDER",
                message=f"Provider '{provider.value}' is not registered in platform registry",
            )
        return self._adapters[provider]

    def register_adapter(self, provider: CloudProvider, adapter: BaseProductionProviderAdapter) -> None:
        """Register or override a provider adapter instance."""
        self._adapters[provider] = adapter
        logger.info("Registered production adapter for %s (mode=%s)", provider.value, adapter.mode.value)

    def list_providers(self) -> list[ProviderSummary]:
        """Return discovery summary of all registered providers and capability matrices."""
        summaries: list[ProviderSummary] = []
        for provider, adapter in self._adapters.items():
            health = adapter.health_check()
            summaries.append(
                ProviderSummary(
                    provider=provider,
                    name=provider.value.upper(),
                    mode=adapter.mode,
                    status=health.status,
                    supported_capabilities=list(adapter.supported_capabilities),
                    is_read_only=adapter.mode == ProviderMode.READ_ONLY,
                    credential_type=adapter.vault.get_credentials(provider).get("auth_type", "UNKNOWN"),
                    latency_ms=health.latency_ms,
                )
            )
        return summaries

    def get_capabilities(self, provider: CloudProvider) -> list[Capability]:
        """Return list of capabilities physically supported by provider."""
        adapter = self.get_adapter(provider)
        return list(adapter.supported_capabilities)

    def has_capability(self, provider: CloudProvider, capability: Capability) -> bool:
        """Check if provider supports capability under its active operational mode."""
        adapter = self.get_adapter(provider)
        return adapter.has_capability(capability)

    def validate_agent_operation(
        self,
        provider: CloudProvider,
        capability: Capability,
        trace_id: Optional[str] = None,
    ) -> None:
        """
        Pre-execution security assertion:
        1. Checks emergency stop.
        2. Asserts provider physically supports capability.
        3. Asserts provider mode permits operation (blocks mutating on read-only AWS).
        Never allows an agent to execute an unsupported operation.
        """
        # Step 1: Emergency stop verification
        if self.safety_plane.emergency.is_stopped():
            raise ProviderError(
                provider=provider,
                error_code="EMERGENCY_STOP_ACTIVE",
                message="Operation blocked: Global Emergency Stop is ACTIVE",
                trace_id=trace_id,
            )

        adapter = self.get_adapter(provider)

        # Step 2: Capability check
        if capability not in adapter.supported_capabilities:
            logger.error(
                "Agent attempted unsupported capability '%s' on provider '%s'",
                capability.value,
                provider.value,
            )
            raise UnsupportedCapabilityError(
                provider=provider,
                capability=capability,
                trace_id=trace_id,
            )

        # Step 3: Mode check
        if adapter.mode == ProviderMode.READ_ONLY and is_mutating_capability(capability):
            logger.error(
                "Agent attempted mutating capability '%s' on READ_ONLY provider '%s'",
                capability.value,
                provider.value,
            )
            raise ReadOnlyViolationError(
                provider=provider,
                capability=capability,
                trace_id=trace_id,
            )


# Global registry singleton
_provider_registry = ProductionProviderRegistry()


def get_production_provider_registry() -> ProductionProviderRegistry:
    """Return the platform production provider registry singleton."""
    return _provider_registry

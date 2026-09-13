"""
Cloud, Billing, and Execution Provider Adapter Interfaces and Registry.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type


class BaseCloudAdapter(ABC):
    """Abstract interface for multi-cloud infrastructure discovery (M1)."""

    @abstractmethod
    def discover(self) -> Tuple[List[Any], List[Any]]:
        """
        Discover cloud resources and dependency edges.
        
        Returns:
            Tuple of (resources, dependency_edges)
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify API credentials and connectivity."""
        pass


class BaseBillingAdapter(ABC):
    """Abstract interface for cloud billing ingestion (M2)."""

    @abstractmethod
    def fetch_billing_data(self, start_date: datetime, end_date: datetime) -> List[Any]:
        """Fetch cost and usage line items for date range."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify billing API credentials and connectivity."""
        pass


class BaseExecutorAdapter(ABC):
    """Abstract interface for cloud infrastructure execution (M10)."""

    @abstractmethod
    def execute_action(self, target_id: str, action: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute an action against target infrastructure."""
        pass

    @abstractmethod
    def rollback_action(self, execution_id: str) -> bool:
        """Roll back an executed action."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify execution access and permissions."""
        pass


class ProviderAdapterRegistry:
    """Registry and factory for provider adapters."""

    def __init__(self) -> None:
        self._cloud_adapters: Dict[str, Type[BaseCloudAdapter]] = {}
        self._billing_adapters: Dict[str, Type[BaseBillingAdapter]] = {}
        self._executor_adapters: Dict[str, Type[BaseExecutorAdapter]] = {}

    def register_cloud_adapter(self, provider: str, adapter_cls: Type[BaseCloudAdapter]) -> None:
        """Register a cloud discovery adapter."""
        self._cloud_adapters[provider.lower()] = adapter_cls

    def get_cloud_adapter(self, provider: str) -> Optional[Type[BaseCloudAdapter]]:
        """Retrieve a registered cloud adapter class."""
        return self._cloud_adapters.get(provider.lower())

    def register_billing_adapter(self, provider: str, adapter_cls: Type[BaseBillingAdapter]) -> None:
        """Register a billing adapter."""
        self._billing_adapters[provider.lower()] = adapter_cls

    def get_billing_adapter(self, provider: str) -> Optional[Type[BaseBillingAdapter]]:
        """Retrieve a registered billing adapter class."""
        return self._billing_adapters.get(provider.lower())

    def register_executor_adapter(self, provider: str, adapter_cls: Type[BaseExecutorAdapter]) -> None:
        """Register an execution adapter."""
        self._executor_adapters[provider.lower()] = adapter_cls

    def get_executor_adapter(self, provider: str) -> Optional[Type[BaseExecutorAdapter]]:
        """Retrieve a registered executor adapter class."""
        return self._executor_adapters.get(provider.lower())


_adapter_registry = ProviderAdapterRegistry()


def get_adapter_registry() -> ProviderAdapterRegistry:
    """Return the platform adapter registry singleton."""
    return _adapter_registry

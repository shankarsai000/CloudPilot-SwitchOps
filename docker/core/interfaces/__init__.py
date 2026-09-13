"""
Standard abstract base interfaces for agents and provider adapters.
"""

from core.interfaces.agent import (
    AgentExecutionResult,
    AgentMetadata,
    AgentStatus,
    BaseAgent,
)
from core.interfaces.adapters import (
    BaseBillingAdapter,
    BaseCloudAdapter,
    BaseExecutorAdapter,
    ProviderAdapterRegistry,
    get_adapter_registry,
)

__all__ = [
    "AgentExecutionResult",
    "AgentMetadata",
    "AgentStatus",
    "BaseAgent",
    "BaseBillingAdapter",
    "BaseCloudAdapter",
    "BaseExecutorAdapter",
    "ProviderAdapterRegistry",
    "get_adapter_registry",
]

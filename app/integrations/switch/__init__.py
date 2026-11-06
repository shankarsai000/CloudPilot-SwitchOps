"""CloudPilot SwitchOps Switch integration package."""

from app.integrations.switch.adapter import create_switch_integration
from app.integrations.switch.client import (
    SwitchAdapterInterface,
    SwitchWireClient,
)
from app.integrations.switch.config import SwitchConnectionConfig
from app.integrations.switch.connection_manager import SwitchConnectionManager
from app.integrations.switch.event_handler import SwitchEventHandler
from app.integrations.switch.exceptions import (
    SwitchAuthError,
    SwitchConnectionError,
    SwitchIntegrationError,
    SwitchProtocolError,
    SwitchPublishError,
    SwitchSessionError,
    SwitchTimeoutError,
    SwitchUnverifiedLiveError,
)
from app.integrations.switch.health import (
    SwitchConnectionHealth,
    SwitchConnectionState,
    SwitchProtocolCapabilities,
)
from app.integrations.switch.message_mapper import (
    SwitchCollaborationEvent,
    SwitchMessageMapper,
    WorkflowEventType,
)
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge

__all__ = [
    "EmulatedSwitchBridge",
    "SwitchAdapterInterface",
    "SwitchAuthError",
    "SwitchCollaborationEvent",
    "SwitchConnectionConfig",
    "SwitchConnectionError",
    "SwitchConnectionHealth",
    "SwitchConnectionManager",
    "SwitchConnectionState",
    "SwitchEventHandler",
    "SwitchIntegrationError",
    "SwitchMessageMapper",
    "SwitchProtocolCapabilities",
    "SwitchProtocolError",
    "SwitchPublishError",
    "SwitchSessionError",
    "SwitchTimeoutError",
    "SwitchUnverifiedLiveError",
    "SwitchWireClient",
    "WorkflowEventType",
    "create_switch_integration",
]

"""CloudPilot SwitchOps Switch integration package."""

from app.integrations.switch.client import (
    SwitchAdapterInterface,
    SwitchWireClient,
)
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge

__all__ = [
    "EmulatedSwitchBridge",
    "SwitchAdapterInterface",
    "SwitchWireClient",
]

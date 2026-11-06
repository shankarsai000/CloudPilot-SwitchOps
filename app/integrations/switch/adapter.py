"""
CloudPilot SwitchOps — Unified Switch Adapter & Factory (Phase 4.2)

Provides factory construction and unified access to SwitchWireClient, EmulatedSwitchBridge,
SwitchConnectionManager, SwitchConnectionHealth, and SwitchEventHandler.
Preserves full backward compatibility with Phase 1–4.1 interfaces while enforcing
truthful integration state reporting.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.core.config import Settings, get_settings
from app.integrations.switch.client import SwitchAdapterInterface, SwitchWireClient
from app.integrations.switch.config import SwitchConnectionConfig
from app.integrations.switch.connection_manager import SwitchConnectionManager
from app.integrations.switch.event_handler import SwitchEventHandler
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge


def create_switch_integration(
    settings: Optional[Settings] = None,
    config: Optional[SwitchConnectionConfig] = None,
    force_mode: Optional[str] = None,
) -> Tuple[SwitchAdapterInterface, SwitchConnectionManager]:
    """
    Constructs the appropriate Switch adapter and connection manager based on configuration.
    Never silently disguises EmulatedSwitchBridge as a live connection.
    """
    app_settings = settings or get_settings()
    conn_config = config or SwitchConnectionConfig.from_env_and_settings(app_settings)
    effective_mode = (force_mode or conn_config.mode).lower()

    if effective_mode == "live":
        adapter: SwitchAdapterInterface = SwitchWireClient(
            bridge_url=conn_config.endpoint,
            agent_id=conn_config.agent_id,
            agent_api_key=conn_config.api_key.get_secret_value() if conn_config.api_key else None,
            timeout_seconds=conn_config.connection_timeout,
        )
        conn_config.mode = "live"
    elif effective_mode in ("emulated", "mock"):
        adapter = EmulatedSwitchBridge()
        conn_config.mode = effective_mode
    else:
        # 'auto' mode: use live client if live credentials are provided, otherwise emulated bridge
        if conn_config.has_live_credentials() and not app_settings.is_testing:
            adapter = SwitchWireClient(
                bridge_url=conn_config.endpoint,
                agent_id=conn_config.agent_id,
                agent_api_key=conn_config.api_key.get_secret_value() if conn_config.api_key else None,
                timeout_seconds=conn_config.connection_timeout,
            )
            conn_config.mode = "live"
        else:
            adapter = EmulatedSwitchBridge()
            conn_config.mode = "emulated"

    manager = SwitchConnectionManager(adapter=adapter, config=conn_config)
    return adapter, manager


__all__ = [
    "EmulatedSwitchBridge",
    "SwitchAdapterInterface",
    "SwitchConnectionConfig",
    "SwitchConnectionManager",
    "SwitchEventHandler",
    "SwitchWireClient",
    "create_switch_integration",
]


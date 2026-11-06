"""
CloudPilot SwitchOps — Switch Connection Configuration (Phase 4.2)

Resolves Switch connection parameters from environment variables or application Settings.
Supports both CLOUDPILOT_SWITCH_* and SWITCH_* environment conventions while redacting secrets.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from pydantic import BaseModel, Field, SecretStr

from app.core.config import Settings, get_settings


def is_placeholder_credential(value: Optional[str]) -> bool:
    """Return True if the value is empty or an obvious placeholder template token."""
    if not value:
        return True
    val = value.strip()
    if not val:
        return True
    val_lower = val.lower()
    if val_lower.startswith("<") and val_lower.endswith(">"):
        return True
    placeholder_patterns = (
        "placeholder",
        "your-",
        "<your",
        "dummy",
        "fake",
        "demo-key",
        "swak_placeholder",
        "switch_reg_placeholder",
        "unverified",
    )
    if any(p in val_lower for p in placeholder_patterns):
        return True
    if val_lower in ("test", "xxx", "todo", "none", "null", "undefined", "changeme"):
        return True
    return False


class SwitchConnectionConfig(BaseModel):
    """
    Strongly typed Switch connection configuration with bounded retry parameters.
    Never logs or serializes raw credentials.
    """

    enabled: bool = Field(default=True, description="Whether Switch integration is enabled")
    mode: str = Field(
        default="auto",
        description="Integration mode: 'live', 'emulated', 'mock', or 'auto'",
    )
    endpoint: str = Field(
        default="http://localhost:8080",
        description="Switch Agent Bridge base URL",
    )
    room_id: str = Field(
        default="cloudpilot-ops",
        description="Target Switch collaboration room ID",
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="Registered Switch Agent ID",
    )
    agent_name: str = Field(
        default="cloudpilot-ops-agent",
        description="Registered Switch Agent name",
    )
    api_key: Optional[SecretStr] = Field(
        default=None,
        description="Switch Agent API key (swak-*)",
    )
    registration_key: Optional[SecretStr] = Field(
        default=None,
        description="Out-of-band registration key for POST /agents",
    )
    connection_timeout: float = Field(
        default=15.0,
        ge=1.0,
        le=120.0,
        description="HTTP/WebSocket connection timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Bounded maximum reconnection/publication retries",
    )
    retry_base_delay: float = Field(
        default=1.0,
        ge=0.01,
        le=30.0,
        description="Base delay in seconds for exponential backoff",
    )

    @classmethod
    def from_env_and_settings(cls, settings: Optional[Settings] = None) -> "SwitchConnectionConfig":
        """Load configuration from environment variables and fallback to Settings."""
        app_settings = settings or get_settings()

        enabled_raw = os.environ.get("SWITCH_ENABLED", os.environ.get("CLOUDPILOT_SWITCH_ENABLED", "true"))
        enabled = str(enabled_raw).strip().lower() in ("true", "1", "yes", "on")

        mode_raw = os.environ.get("SWITCH_MODE", os.environ.get("CLOUDPILOT_SWITCH_MODE", "")).strip().lower()
        if not mode_raw:
            if app_settings.is_testing:
                mode_raw = "emulated"
            else:
                mode_raw = "auto"

        endpoint = (
            os.environ.get("SWITCH_BRIDGE_URL")
            or os.environ.get("SWITCH_ENDPOINT")
            or os.environ.get("CLOUDPILOT_SWITCH_BRIDGE_URL")
            or app_settings.switch_bridge_url
            or "http://localhost:8080"
        )
        room_id = (
            os.environ.get("SWITCH_ROOM_ID")
            or os.environ.get("CLOUDPILOT_SWITCH_ROOM_ID")
            or app_settings.switch_room_id
            or "cloudpilot-ops"
        )
        agent_id = (
            os.environ.get("SWITCH_AGENT_ID")
            or os.environ.get("CLOUDPILOT_SWITCH_AGENT_ID")
            or app_settings.switch_agent_id
        )
        agent_name = (
            os.environ.get("SWITCH_AGENT_NAME")
            or os.environ.get("CLOUDPILOT_SWITCH_AGENT_NAME")
            or app_settings.switch_agent_name
            or "cloudpilot-ops-agent"
        )

        # Ignore placeholder template values
        if is_placeholder_credential(agent_id):
            agent_id = None

        raw_api_key = (
            os.environ.get("SWITCH_AGENT_API_KEY")
            or os.environ.get("SWITCH_API_KEY")
            or os.environ.get("CLOUDPILOT_SWITCH_AGENT_API_KEY")
        )
        if not raw_api_key and app_settings.switch_agent_api_key:
            raw_api_key = app_settings.switch_agent_api_key.get_secret_value()
        if is_placeholder_credential(raw_api_key):
            raw_api_key = None

        raw_reg_key = (
            os.environ.get("SWITCH_REGISTRATION_KEY")
            or os.environ.get("CLOUDPILOT_SWITCH_REGISTRATION_KEY")
        )
        if not raw_reg_key and app_settings.switch_registration_key:
            raw_reg_key = app_settings.switch_registration_key.get_secret_value()
        if is_placeholder_credential(raw_reg_key):
            raw_reg_key = None

        timeout_val = float(os.environ.get("SWITCH_CONNECTION_TIMEOUT", "15.0"))
        max_retries_val = int(os.environ.get("SWITCH_MAX_RETRIES", "3"))
        base_delay_val = float(os.environ.get("SWITCH_RETRY_BASE_DELAY", "1.0"))

        return cls(
            enabled=enabled,
            mode=mode_raw,
            endpoint=endpoint.rstrip("/"),
            room_id=room_id,
            agent_id=agent_id,
            agent_name=agent_name,
            api_key=SecretStr(raw_api_key) if raw_api_key else None,
            registration_key=SecretStr(raw_reg_key) if raw_reg_key else None,
            connection_timeout=timeout_val,
            max_retries=max_retries_val,
            retry_base_delay=base_delay_val,
        )

    def has_live_credentials(self) -> bool:
        """Return True only if non-placeholder live credentials are configured."""
        has_agent_creds = bool(
            self.agent_id
            and not is_placeholder_credential(self.agent_id)
            and self.api_key
            and not is_placeholder_credential(self.api_key.get_secret_value())
        )
        has_reg_creds = bool(
            self.registration_key
            and not is_placeholder_credential(self.registration_key.get_secret_value())
        )
        return bool(self.endpoint and (has_agent_creds or has_reg_creds))

    def safe_summary(self) -> dict[str, Any]:
        """Return credential-redacted summary for diagnostics and reports."""
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "endpoint": self.endpoint,
            "room_id": self.room_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "has_api_key": bool(self.api_key),
            "has_registration_key": bool(self.registration_key),
            "has_live_credentials": self.has_live_credentials(),
            "connection_timeout": self.connection_timeout,
            "max_retries": self.max_retries,
            "retry_base_delay": self.retry_base_delay,
        }


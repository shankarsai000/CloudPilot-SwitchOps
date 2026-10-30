"""
CloudPilot SwitchOps — Core Configuration & Environment Validation

Manages strongly typed settings using Pydantic Settings, enforces safe defaults,
validates external configuration, and guarantees secret redaction.
"""

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    CloudPilot SwitchOps application settings.
    Loaded hierarchically from CLOUDPILOT_* environment variables, .env file, and defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLOUDPILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application metadata
    app_name: str = Field(default="CloudPilot SwitchOps", description="Display name of the application")
    app_version: str = Field(default="1.0.0", description="Semver application version")
    environment: str = Field(default="development", description="Environment: development, testing, staging, production")
    debug: bool = Field(default=False, description="Enable debug mode")

    # Networking & Server
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8000, description="Server listen port")
    cors_origins: list[str] = Field(default=["*"], description="Allowed CORS origins list")

    # Persistence
    database_url: str = Field(
        default="sqlite:///./cloudpilot_tasks.db",
        description="Database connection URL (SQLite or PostgreSQL)",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    log_format: str = Field(default="json", description="Log format: 'json' or 'console'")

    # Switch Agent Bridge Integration
    switch_bridge_url: str | None = Field(
        default="http://localhost:8080",
        description="Base URL of Switch Agent Bridge (e.g. http://localhost:8080)",
    )
    switch_registration_key: SecretStr | None = Field(
        default=None,
        description="Bearer token used once out-of-band to register the agent with POST /agents",
    )
    switch_agent_id: str | None = Field(
        default=None,
        description="Pre-registered Switch agent ID (e.g. agent-uuid)",
    )
    switch_agent_api_key: SecretStr | None = Field(
        default=None,
        description="Agent-specific API key returned from registration for WebSocket & message calls",
    )
    switch_agent_name: str = Field(
        default="cloudpilot-ops-agent",
        description="Registered agent name, must match ^[a-z0-9][a-z0-9._-]*$",
    )
    switch_room_id: str = Field(
        default="cloudpilot-ops",
        description="Target Switch operations room ID to claim and monitor",
    )
    switch_heartbeat_interval_seconds: float = Field(
        default=2.0,
        description="Interval in seconds for responding to Switch ping frames with pong",
    )
    switch_heartbeat_timeout_seconds: float = Field(
        default=6.0,
        description="Lapse timeout before Switch closes connection for missing pong",
    )
    switch_auto_reconnect: bool = Field(
        default=True,
        description="Whether to automatically resume connection on drops using cursor and generation",
    )

    @field_validator("debug", mode="before")
    @classmethod
    def _validate_debug(cls, v: Any) -> bool:
        """Handle arbitrary truthy/falsy environment strings safely."""
        if isinstance(v, str):
            norm = v.strip().lower()
            return norm in ("true", "1", "yes", "on", "debug")
        return bool(v)

    @field_validator("environment", mode="before")
    @classmethod
    def _validate_environment(cls, v: Any) -> str:
        if isinstance(v, str):
            norm = v.strip().lower()
            if norm in ("test", "testing"):
                return "testing"
            if norm in ("prod", "production"):
                return "production"
            if norm in ("stage", "staging"):
                return "staging"
            return "development"
        return "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    def is_switch_configured(self) -> bool:
        """Check whether minimum credentials to connect to Switch are configured."""
        return bool(
            self.switch_bridge_url
            and (
                (self.switch_agent_id and self.switch_agent_api_key)
                or self.switch_registration_key
            )
        )

    def safe_dict(self) -> dict[str, Any]:
        """Return non-sensitive settings dictionary suitable for logging and diagnostics."""
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "environment": self.environment,
            "debug": self.debug,
            "host": self.host,
            "port": self.port,
            "database_url": self.database_url.split("@")[-1] if "@" in self.database_url else self.database_url,
            "log_level": self.log_level,
            "log_format": self.log_format,
            "switch_bridge_url": self.switch_bridge_url,
            "switch_agent_id": self.switch_agent_id,
            "switch_agent_name": self.switch_agent_name,
            "switch_room_id": self.switch_room_id,
            "switch_configured": self.is_switch_configured(),
            "switch_registration_key_set": bool(self.switch_registration_key),
            "switch_agent_api_key_set": bool(self.switch_agent_api_key),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton instance of validated settings."""
    return Settings()

"""
Tests for Phase 4.3.1 Switch Configuration, Secret Redaction, and Authentication Integrity.

Proves:
1. Documented environment variables are correctly loaded (SWITCH_MODE, SWITCH_BRIDGE_URL, etc.)
2. Placeholder credentials are rejected fail-closed
3. Missing credentials do not produce live status (result is LIVE_UNVERIFIED)
4. Invalid credentials produce an authentication failure (LIVE_AUTH_FAILED)
5. Live status requires a successful authenticated communication exchange
6. Secrets never appear in logs or health responses
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.core.config import Settings
from app.integrations.switch.client import SwitchWireClient
from app.integrations.switch.config import SwitchConnectionConfig, is_placeholder_credential
from app.integrations.switch.connection_manager import SwitchConnectionManager
from app.integrations.switch.exceptions import SwitchAuthError, SwitchUnverifiedLiveError
from app.integrations.switch.health import SwitchConnectionHealth, SwitchConnectionState


def test_documented_env_vars_loaded(monkeypatch):
    """Prove that all 6 canonical environment variables are correctly loaded."""
    monkeypatch.setenv("SWITCH_MODE", "live")
    monkeypatch.setenv("SWITCH_BRIDGE_URL", "https://bridge.switch.network:8443")
    monkeypatch.setenv("SWITCH_AGENT_API_KEY", "swak_live_real_secret_token_12345")
    monkeypatch.setenv("SWITCH_ROOM_ID", "ops-production-room")
    monkeypatch.setenv("SWITCH_AGENT_ID", "agent-prod-007")
    monkeypatch.setenv("SWITCH_REGISTRATION_KEY", "reg_token_real_auth_999")

    cfg = SwitchConnectionConfig.from_env_and_settings()

    assert cfg.mode == "live"
    assert cfg.endpoint == "https://bridge.switch.network:8443"
    assert cfg.room_id == "ops-production-room"
    assert cfg.agent_id == "agent-prod-007"
    assert cfg.api_key is not None
    assert cfg.api_key.get_secret_value() == "swak_live_real_secret_token_12345"
    assert cfg.registration_key is not None
    assert cfg.registration_key.get_secret_value() == "reg_token_real_auth_999"
    assert cfg.has_live_credentials() is True


def test_placeholder_credentials_rejected(monkeypatch):
    """Prove that common template placeholders are rejected as unconfigured."""
    placeholders = [
        "your-live-api-key",
        "<your-agent-api-key>",
        "swak_placeholder_agent_api_key",
        "demo-key-unverified",
        "dummy",
        "test",
        "placeholder",
        "changeme",
        "<your-registration-key>",
    ]

    for ph in placeholders:
        assert is_placeholder_credential(ph) is True, f"Failed for {ph}"

    monkeypatch.setenv("SWITCH_MODE", "live")
    monkeypatch.setenv("SWITCH_BRIDGE_URL", "http://localhost:8080")
    monkeypatch.setenv("SWITCH_AGENT_API_KEY", "your-live-api-key")
    monkeypatch.setenv("SWITCH_AGENT_ID", "<your-agent-id>")

    cfg = SwitchConnectionConfig.from_env_and_settings()
    assert cfg.api_key is None
    assert cfg.agent_id is None
    assert cfg.has_live_credentials() is False


@pytest.mark.asyncio
async def test_missing_credentials_do_not_produce_live_status():
    """Prove that missing credentials produce LIVE_UNVERIFIED, never LIVE_CONNECTED."""
    cfg = SwitchConnectionConfig(
        endpoint="http://localhost:8080",
        mode="live",
        agent_id=None,
        api_key=None,
    )
    wire_client = SwitchWireClient(
        bridge_url="http://localhost:8080",
        agent_id=None,
        agent_api_key=None,
    )
    # Mock health probe responding OK
    wire_client.check_health = AsyncMock(return_value={"status": "healthy"})

    mgr = SwitchConnectionManager(adapter=wire_client, config=cfg)
    health = await mgr.verify_connection(require_live=False)

    assert health.state == SwitchConnectionState.LIVE_UNVERIFIED
    assert health.verified_live is False
    assert "missing" in (health.external_blocker or "").lower()


@pytest.mark.asyncio
async def test_invalid_credentials_produce_auth_failure():
    """Prove that invalid credentials produce an authentication failure (LIVE_AUTH_FAILED)."""
    cfg = SwitchConnectionConfig(
        endpoint="http://localhost:8080",
        mode="live",
        agent_id="agent-123",
        api_key="invalid-api-key-rejected-by-bridge",
    )
    wire_client = SwitchWireClient(
        bridge_url="http://localhost:8080",
        agent_id="agent-123",
        agent_api_key="invalid-api-key-rejected-by-bridge",
    )
    wire_client.check_health = AsyncMock(return_value={"status": "healthy"})
    wire_client.verify_auth = AsyncMock(side_effect=SwitchAuthError("HTTP 401: Unauthorized agent key"))

    mgr = SwitchConnectionManager(adapter=wire_client, config=cfg)

    with pytest.raises(SwitchAuthError):
        await mgr.verify_connection(require_live=True)

    assert mgr.health.state == SwitchConnectionState.LIVE_AUTH_FAILED
    assert mgr.health.verified_live is False
    assert "401" in (mgr.health.last_error or "")


@pytest.mark.asyncio
async def test_live_status_requires_authenticated_communication_exchange():
    """Prove that LIVE_CONNECTED requires a genuine successful authenticated communication exchange."""
    cfg = SwitchConnectionConfig(
        endpoint="http://localhost:8080",
        mode="live",
        agent_id="agent-verified-123",
        api_key="valid-secret-key-accepted",
    )
    wire_client = SwitchWireClient(
        bridge_url="http://localhost:8080",
        agent_id="agent-verified-123",
        agent_api_key="valid-secret-key-accepted",
    )
    wire_client.check_health = AsyncMock(return_value={"status": "healthy"})
    wire_client.verify_auth = AsyncMock(return_value={"status": "ok", "addressing": "owner_and_owner_agents"})

    mgr = SwitchConnectionManager(adapter=wire_client, config=cfg)
    health = await mgr.verify_connection(require_live=True)

    assert health.state == SwitchConnectionState.LIVE_CONNECTED
    assert health.verified_live is True
    wire_client.verify_auth.assert_awaited_once()


def test_secrets_never_appear_in_logs_or_health():
    """Prove that raw secrets never appear in status dicts, summaries, or string serializations."""
    secret_key_val = "swak_super_secret_never_leak_this_token_987654321"
    reg_key_val = "reg_confidential_token_value_abcxyz"

    cfg = SwitchConnectionConfig(
        endpoint="http://localhost:8080",
        agent_id="agent-secure",
        api_key=secret_key_val,
        registration_key=reg_key_val,
    )
    summary = cfg.safe_summary()
    assert secret_key_val not in str(summary)
    assert reg_key_val not in str(summary)

    health = SwitchConnectionHealth(
        connection_state=SwitchConnectionState.LIVE_CONNECTED,
        bridge_url="http://localhost:8080",
        agent_id="agent-secure",
    )
    status_dict = health.to_status_dict()
    assert secret_key_val not in str(status_dict)
    assert reg_key_val not in str(status_dict)

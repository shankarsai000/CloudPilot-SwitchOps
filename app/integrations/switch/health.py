"""
CloudPilot SwitchOps — Switch Connection Health & Truthful Integration Status (Phase 4.2)

Enforces truthful integration status reporting across API responses, logs, UI, and reports.
Never reports LIVE_CONNECTED merely because credentials exist or because an emulated bridge responded.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SwitchConnectionState(str, Enum):
    """
    Canonical Switch connection and integration states (Section 1.3).
    """

    LIVE_CONNECTED = "LIVE_CONNECTED"
    LIVE_DISCONNECTED = "LIVE_DISCONNECTED"
    LIVE_AUTH_FAILED = "LIVE_AUTH_FAILED"
    LIVE_PROTOCOL_ERROR = "LIVE_PROTOCOL_ERROR"
    LIVE_UNVERIFIED = "LIVE_UNVERIFIED"
    MOCK_MODE = "MOCK_MODE"
    EMULATED_MODE = "EMULATED_MODE"


class SwitchProtocolCapabilities(BaseModel):
    """Verified capabilities of the Switch Agent Bridge wire protocol."""

    protocol_version: str = Field(default="switch-wire-v1", description="Switch Agent Bridge wire protocol version")
    transport: str = Field(
        default="websocket_in_http_out",
        description="Events over WebSocket in (GET /agents/{id}/connection/ws), operations over HTTP out",
    )
    supports_health_probe: bool = True
    supports_agent_registration: bool = True
    supports_room_message_post: bool = True
    supports_websocket_streaming: bool = True
    supports_heartbeat_cursor_fencing: bool = True
    supports_native_approval_buttons: bool = Field(
        default=False,
        description="Switch room wire protocol supports markdown messages; structured approval buttons are not a native wire primitive.",
    )
    approval_mechanism: str = Field(
        default="correlated_command_and_authenticated_rest_api",
        description="Correlated room command + server-side authenticated principal & HMAC token verification",
    )


class SwitchConnectionHealth(BaseModel):
    """
    Truth-preserving connection health snapshot for Switch integration (Workstream A3).
    """

    connection_state: SwitchConnectionState = Field(
        default=SwitchConnectionState.LIVE_UNVERIFIED,
        description="Current truthful integration state",
    )
    integration_mode: str = Field(
        default="LIVE_UNVERIFIED",
        description="Configured mode: LIVE, EMULATED, or MOCK",
    )
    verified_live: bool = Field(
        default=False,
        description="True ONLY when a real external Switch Bridge has completed authenticated communication",
    )
    bridge_url: Optional[str] = None
    room_id: str = "cloudpilot-ops"
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    generation: Optional[str] = None
    cursor: int = 0
    last_successful_communication: Optional[datetime] = None
    last_error: Optional[str] = None
    external_blocker: Optional[str] = None
    retry_count: int = 0
    latency_ms: Optional[float] = None
    messages_published_count: int = 0
    events_received_count: int = 0
    protocol_capabilities: SwitchProtocolCapabilities = Field(
        default_factory=SwitchProtocolCapabilities
    )

    @property
    def state(self) -> SwitchConnectionState:
        return self.connection_state

    def is_operational(self) -> bool:
        return self.connection_state in (
            SwitchConnectionState.LIVE_CONNECTED,
            SwitchConnectionState.EMULATED_MODE,
            SwitchConnectionState.MOCK_MODE,
        )

    def mark_live_connected(
        self,
        latency_ms: Optional[float] = None,
        session_id: Optional[str] = None,
        generation: Optional[str] = None,
        cursor: Optional[int] = None,
    ) -> None:
        """Record verified live communication with a real Switch Agent Bridge."""
        self.connection_state = SwitchConnectionState.LIVE_CONNECTED
        self.integration_mode = "LIVE"
        self.verified_live = True
        self.last_successful_communication = datetime.now(timezone.utc)
        self.last_error = None
        self.external_blocker = None
        if latency_ms is not None:
            self.latency_ms = round(latency_ms, 2)
        if session_id is not None:
            self.session_id = session_id
        if generation is not None:
            self.generation = generation
        if cursor is not None:
            self.cursor = cursor

    def mark_live_auth_failed(self, error: str) -> None:
        self.connection_state = SwitchConnectionState.LIVE_AUTH_FAILED
        self.integration_mode = "LIVE"
        self.verified_live = False
        self.last_error = error

    def mark_live_protocol_error(self, error: str) -> None:
        self.connection_state = SwitchConnectionState.LIVE_PROTOCOL_ERROR
        self.integration_mode = "LIVE"
        self.verified_live = False
        self.last_error = error

    def mark_live_disconnected(self, error: str, blocker: Optional[str] = None) -> None:
        self.connection_state = SwitchConnectionState.LIVE_DISCONNECTED
        self.integration_mode = "LIVE"
        self.verified_live = False
        self.last_error = error
        if blocker:
            self.external_blocker = blocker

    def mark_live_unverified(self, reason: str, blocker: Optional[str] = None) -> None:
        self.connection_state = SwitchConnectionState.LIVE_UNVERIFIED
        self.integration_mode = "LIVE"
        self.verified_live = False
        self.last_error = reason
        self.external_blocker = blocker or reason

    def mark_emulated_mode(self, session_id: Optional[str] = None) -> None:
        self.connection_state = SwitchConnectionState.EMULATED_MODE
        self.integration_mode = "EMULATED"
        self.verified_live = False
        self.last_successful_communication = datetime.now(timezone.utc)
        if session_id:
            self.session_id = session_id

    def mark_mock_mode(self, session_id: Optional[str] = None) -> None:
        self.connection_state = SwitchConnectionState.MOCK_MODE
        self.integration_mode = "MOCK"
        self.verified_live = False
        self.last_successful_communication = datetime.now(timezone.utc)
        if session_id:
            self.session_id = session_id

    def to_status_dict(self) -> Dict[str, Any]:
        return {
            "state": self.connection_state.value,
            "connection_state": self.connection_state.value,
            "integration_mode": self.integration_mode,
            "verified_live": self.verified_live,
            "bridge_url": self.bridge_url,
            "room_id": self.room_id,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "generation": self.generation,
            "cursor": self.cursor,
            "last_successful_communication": (
                self.last_successful_communication.isoformat()
                if self.last_successful_communication
                else None
            ),
            "last_error": self.last_error,
            "external_blocker": self.external_blocker,
            "retry_count": self.retry_count,
            "latency_ms": self.latency_ms,
            "messages_published_count": self.messages_published_count,
            "events_received_count": self.events_received_count,
            "protocol_capabilities": self.protocol_capabilities.model_dump(),
        }


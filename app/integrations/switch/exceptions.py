"""
CloudPilot SwitchOps — Switch Integration Exceptions (Phase 4.2)

Typed exception hierarchy for Switch Agent Bridge connectivity, authentication,
protocol framing, session lifecycle, and publication failures.
"""

from __future__ import annotations

from app.core.errors import (
    SwitchAuthError,
    SwitchConnectionError,
    SwitchIntegrationError,
)


class SwitchProtocolError(SwitchIntegrationError):
    """Raised when the Switch bridge sends an unrecognized or malformed frame."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message=message, status_code=502, details=details)
        self.code = "SWITCH_PROTOCOL_ERROR"


class SwitchTimeoutError(SwitchConnectionError):
    """Raised when a Switch HTTP or WebSocket operation times out."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message=message, details=details)
        self.code = "SWITCH_TIMEOUT_ERROR"


class SwitchSessionError(SwitchIntegrationError):
    """Raised when room/session creation or claiming fails."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message=message, status_code=502, details=details)
        self.code = "SWITCH_SESSION_ERROR"


class SwitchPublishError(SwitchIntegrationError):
    """Raised when message publication to a Switch room fails after bounded retries."""

    def __init__(self, message: str, status_code: int = 502, details: dict | None = None) -> None:
        super().__init__(message=message, status_code=status_code, details=details)
        self.code = "SWITCH_PUBLISH_ERROR"


class SwitchUnverifiedLiveError(SwitchConnectionError):
    """Raised when live Switch mode is requested but real credentials or bridge reachability cannot be verified."""

    def __init__(self, message: str, blocker: str, details: dict | None = None) -> None:
        merged = dict(details or {})
        merged["external_blocker"] = blocker
        super().__init__(message=message, details=merged)
        self.code = "SWITCH_LIVE_UNVERIFIED"
        self.blocker = blocker


__all__ = [
    "SwitchAuthError",
    "SwitchConnectionError",
    "SwitchIntegrationError",
    "SwitchProtocolError",
    "SwitchPublishError",
    "SwitchSessionError",
    "SwitchTimeoutError",
    "SwitchUnverifiedLiveError",
]


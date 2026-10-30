"""
CloudPilot SwitchOps — Core Exceptions & Domain Errors

Standardized error hierarchy ensuring safe error responses without leaking
internal stack traces, tokens, or credentials.
"""

from typing import Any


class CloudPilotError(Exception):
    """Base exception for all CloudPilot SwitchOps errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize error for client-safe HTTP response."""
        res: dict[str, Any] = {
            "error": self.code,
            "message": self.message,
        }
        if self.details:
            res["details"] = self.details
        return res


class InvalidStateTransitionError(CloudPilotError):
    """Raised when an illegal task lifecycle transition is attempted."""

    def __init__(self, current_status: str, target_status: str, task_id: str) -> None:
        super().__init__(
            message=f"Cannot transition task '{task_id}' from '{current_status}' to '{target_status}'.",
            code="INVALID_STATE_TRANSITION",
            status_code=409,
            details={
                "task_id": task_id,
                "current_status": current_status,
                "target_status": target_status,
            },
        )


class TaskNotFoundError(CloudPilotError):
    """Raised when a requested task does not exist."""

    def __init__(self, task_id: str) -> None:
        super().__init__(
            message=f"Task with ID '{task_id}' was not found.",
            code="TASK_NOT_FOUND",
            status_code=404,
            details={"task_id": task_id},
        )


class TaskConflictError(CloudPilotError):
    """Raised when a task with the given ID already exists."""

    def __init__(self, task_id: str) -> None:
        super().__init__(
            message=f"Task with ID '{task_id}' already exists.",
            code="TASK_ALREADY_EXISTS",
            status_code=409,
            details={"task_id": task_id},
        )


class SwitchIntegrationError(CloudPilotError):
    """Base exception for Switch agent bridge integration failures."""

    def __init__(self, message: str, code: str = "SWITCH_ERROR", status_code: int = 502, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code=code, status_code=status_code, details=details)


class SwitchConnectionError(SwitchIntegrationError):
    """Raised when connection to Switch Agent Bridge fails or is refused."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="SWITCH_CONNECTION_FAILED", status_code=503, details=details)


class SwitchAuthError(SwitchIntegrationError):
    """Raised when Switch Agent Bridge rejects registration or connection credentials."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, code="SWITCH_AUTHENTICATION_FAILED", status_code=401, details=details)


class ConfigurationError(CloudPilotError):
    """Raised when required configuration is missing or invalid."""

    def __init__(self, message: str, missing_key: str | None = None) -> None:
        details = {"missing_key": missing_key} if missing_key else {}
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            status_code=500,
            details=details,
        )


class ValidationError(CloudPilotError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        details = {"field": field} if field else {}
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            details=details,
        )

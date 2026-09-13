"""
Centralized exception handling for CloudPilot AI Platform.

Provides a unified error hierarchy and FastAPI exception handlers
returning standardized error envelopes with correlation IDs.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.logging import get_correlation_id

logger = logging.getLogger("cloudpilot.errors")


class CloudPilotError(Exception):
    """Base exception for all CloudPilot AI domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(CloudPilotError):
    """Raised when a requested resource, entity, or object does not exist."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="RESOURCE_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ValidationError(CloudPilotError):
    """Raised when domain validation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class AuthenticationError(CloudPilotError):
    """Raised when authentication fails or credentials are missing/invalid."""

    def __init__(self, message: str = "Authentication required", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class AuthorizationError(CloudPilotError):
    """Raised when the user lacks permissions for an operation."""

    def __init__(self, message: str = "Access forbidden: insufficient permissions", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ConflictError(CloudPilotError):
    """Raised on state conflicts, duplicate keys, or concurrent modification."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="RESOURCE_CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ExternalProviderError(CloudPilotError):
    """Raised when upstream cloud or observability provider calls fail."""

    def __init__(self, provider: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        d = {"provider": provider}
        if details:
            d.update(details)
        super().__init__(
            message=f"Provider '{provider}' error: {message}",
            code="EXTERNAL_PROVIDER_FAILURE",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=d,
        )


class DatabaseError(CloudPilotError):
    """Raised on persistence failures or database query errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class ConfigurationError(CloudPilotError):
    """Raised on missing, invalid, or conflicting configuration."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class RateLimitError(CloudPilotError):
    """Raised when request rate limits are exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


def build_error_response(
    code: str,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Construct standard JSON error envelope."""
    payload = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": get_correlation_id(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    return JSONResponse(status_code=status_code, content=payload)


async def cloudpilot_error_handler(request: Request, exc: CloudPilotError) -> JSONResponse:
    """Handle domain-specific CloudPilotError exceptions."""
    logger.warning(
        "Handled CloudPilotError [%s]: %s (path: %s)",
        exc.code,
        exc.message,
        request.url.path,
        extra={"extra_data": exc.details},
    )
    return build_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI / Pydantic request validation errors."""
    errors = exc.errors()
    clean_details = [
        {
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "type": err.get("type"),
        }
        for err in errors
    ]
    logger.info("Validation failure on %s: %s", request.url.path, clean_details)
    return build_error_response(
        code="REQUEST_VALIDATION_ERROR",
        message="Request payload or parameters failed validation",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"validation_errors": clean_details},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard Starlette / FastAPI HTTPExceptions."""
    code = "HTTP_ERROR"
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        code = "NOT_FOUND"
    elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = "UNAUTHORIZED"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = "FORBIDDEN"

    return build_error_response(
        code=code,
        message=str(exc.detail),
        status_code=exc.status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all uncaught exceptions without leaking internals to clients."""
    logger.exception("Unhandled server exception on %s: %s", request.url.path, exc)
    return build_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal error occurred. Please contact system support.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all centralized error handlers with the FastAPI application."""
    app.add_exception_handler(CloudPilotError, cloudpilot_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

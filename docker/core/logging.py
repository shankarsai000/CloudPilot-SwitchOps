"""
Structured logging and request correlation tracking for CloudPilot AI.

Outputs structured JSON in production for log ingestion systems (Datadog, CloudWatch,
ELK) and clean readable console output during local development.
Propagates correlation ID and user ID across async tasks using contextvars.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Context variables for distributed tracing
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


def get_correlation_id() -> str:
    """Retrieve current correlation ID or generate a new fallback."""
    val = correlation_id_ctx.get()
    return val if val else f"req-{uuid.uuid4().hex[:12]}"


def set_correlation_id(corr_id: str) -> None:
    """Set current correlation ID in context."""
    correlation_id_ctx.set(corr_id)


def get_current_user_id() -> Optional[str]:
    """Retrieve user ID from context if authenticated."""
    return user_id_ctx.get()


class JSONLogFormatter(logging.Formatter):
    """Formats log records as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        corr_id = correlation_id_ctx.get()
        if corr_id:
            log_payload["correlation_id"] = corr_id

        usr_id = user_id_ctx.get()
        if usr_id:
            log_payload["user_id"] = usr_id

        # Attach exception details if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Attach extra dictionary attributes
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_payload.update(record.extra_data)

        return json.dumps(log_payload, default=str)


class ConsoleFormatter(logging.Formatter):
    """Formats log records for local human-readable terminal output."""

    def format(self, record: logging.LogRecord) -> str:
        corr_id = correlation_id_ctx.get()
        corr_prefix = f" [{corr_id}]" if corr_id else ""
        time_str = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        msg = record.getMessage()

        formatted = f"{time_str} | {record.levelname:<7} | {record.name}{corr_prefix} - {msg}"
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        return formatted


def configure_logging(level: str = "INFO", log_format: str = "json") -> None:
    """
    Initialize root logging configuration.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: 'json' or 'console'
    """
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(numeric_level)

    if log_format.lower() == "json":
        stream_handler.setFormatter(JSONLogFormatter())
    else:
        stream_handler.setFormatter(ConsoleFormatter())

    root_logger.addHandler(stream_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger by name."""
    return logging.getLogger(name)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    HTTP middleware extracting or assigning an X-Request-ID correlation header
    and populating the async context for logging and downstream processing.
    """

    HEADER_NAME = "X-Request-ID"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        corr_id = request.headers.get(self.HEADER_NAME)
        if not corr_id:
            corr_id = f"req-{uuid.uuid4().hex[:12]}"

        correlation_id_ctx.set(corr_id)

        response = await call_next(request)
        response.headers[self.HEADER_NAME] = corr_id
        return response

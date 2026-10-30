"""
CloudPilot SwitchOps — Structured Logging & Observability

Provides JSON-formatted structured logging, ContextVar correlation ID and task ID
propagation, and automatic sensitive data / token redaction.
"""

import json
import logging
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Context variables for request and task correlation
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)
task_id_ctx: ContextVar[str | None] = ContextVar("task_id", default=None)

# Patterns for sensitive tokens and authorization headers
SECRET_PATTERNS = [
    (re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"api[_-]?key[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-\.]{8,})[\"']?", re.IGNORECASE), "api_key=[REDACTED]"),
    (re.compile(r"switch_registration_key[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-\.]{8,})[\"']?", re.IGNORECASE), "switch_registration_key=[REDACTED]"),
    (re.compile(r"switch_agent_api_key[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-\.]{8,})[\"']?", re.IGNORECASE), "switch_agent_api_key=[REDACTED]"),
    (re.compile(r"password[\"']?\s*[:=]\s*[\"']?([^\s,\"']+)[\"']?", re.IGNORECASE), "password=[REDACTED]"),
]


def redact_secrets(text: str) -> str:
    """Mask known secret patterns in log strings."""
    if not isinstance(text, str):
        return text
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def get_correlation_id() -> str | None:
    """Retrieve current correlation ID from context."""
    return correlation_id_ctx.get()


def set_correlation_id(correlation_id: str | None) -> None:
    """Set current correlation ID in context."""
    correlation_id_ctx.set(correlation_id)


def get_task_id() -> str | None:
    """Retrieve current task ID from context."""
    return task_id_ctx.get()


def set_task_id(task_id: str | None) -> None:
    """Set current task ID in context."""
    task_id_ctx.set(task_id)


class StructuredJSONFormatter(logging.Formatter):
    """Formats log records as structured JSON with correlation context and secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        raw_message = record.getMessage()
        sanitized_message = redact_secrets(raw_message)

        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitized_message,
            "module": record.module,
            "func_name": record.funcName,
            "line_no": record.lineno,
        }

        # Include contextual IDs if present
        cid = getattr(record, "correlation_id", None) or get_correlation_id()
        if cid:
            log_data["correlation_id"] = cid

        tid = getattr(record, "task_id", None) or get_task_id()
        if tid:
            log_data["task_id"] = tid

        # Include extra payload if present
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_data["data"] = record.extra_data

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def configure_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Configure root logger with either structured JSON or human-readable console formatter."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    if log_format.lower() == "json":
        handler.setFormatter(StructuredJSONFormatter())
    else:
        fmt = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
        handler.setFormatter(logging.Formatter(fmt))

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)

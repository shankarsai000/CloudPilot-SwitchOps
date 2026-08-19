"""
Execution Logger Component

Generates and stores audit trails, status logs, and streaming events for all execution runs.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from models_execution import ExecutionEvent, ExecutionRecord

logger = logging.getLogger(__name__)


class ExecutionLogger:
    """Manages event logging and historical trail building for execution runs."""

    def __init__(self) -> None:
        """Initialize Execution Logger."""
        self._events: list[ExecutionEvent] = []

    def log_event(
        self,
        execution_id: str,
        message: str,
        level: str = "INFO",
        details: dict[str, Any] = None,
    ) -> ExecutionEvent:
        """Record and log a runtime execution event.

        Args:
            execution_id: ID of the execution run
            message: Log message text
            level: Log level (INFO, WARNING, ERROR, CRITICAL)
            details: Extra metadata

        Returns:
            Created ExecutionEvent
        """
        event = ExecutionEvent(
            event_id=f"evt-exec-{uuid.uuid4().hex[:8]}",
            execution_id=execution_id,
            timestamp=datetime.utcnow(),
            level=level,
            message=message,
            details=details or {},
        )
        self._events.append(event)

        # Output structured python log
        log_msg = f"[{execution_id}] {level}: {message}"
        if level == "WARNING":
            logger.warning(log_msg)
        elif level in ("ERROR", "CRITICAL"):
            logger.error(log_msg)
        else:
            logger.info(log_msg)

        return event

    def append_audit_entry(self, record: ExecutionRecord, action: str, details: str) -> None:
        """Append an entry directly into the record's audit trail list.

        Args:
            record: Target ExecutionRecord
            action: Action performed (e.g. VALIDATION_PASSED, ROLLOUT_STEP)
            details: Context details
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "details": details,
        }
        record.audit_trail.append(entry)
        self.log_event(record.execution_id, f"Audit Entry: {action} - {details}")

    def get_events_for_execution(self, execution_id: str) -> list[ExecutionEvent]:
        """Retrieve all events registered for an execution.

        Args:
            execution_id: Target execution identifier

        Returns:
            List of matching ExecutionEvent logs
        """
        return [e for e in self._events if e.execution_id == execution_id]

    def get_all_events(self) -> list[ExecutionEvent]:
        """Get all events logged.

        Returns:
            List of all ExecutionEvent logs
        """
        return list(self._events)

    def count_events(self) -> int:
        """Return total event log count."""
        return len(self._events)

    def clear(self) -> None:
        """Clear event list."""
        self._events.clear()

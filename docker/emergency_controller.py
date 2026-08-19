"""
Emergency Controller Component

Provides human operators with lifecycle override controls over running executions:
Pause, Resume, Cancel, and Emergency Stop.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from models_execution import ExecutionRecord, ExecutionState

logger = logging.getLogger(__name__)


class EmergencyController:
    """Manages manual emergency lifecycle actions for executions."""

    def __init__(self) -> None:
        """Initialize Emergency Controller."""
        pass

    def pause(self, record: ExecutionRecord, reason: str = "") -> ExecutionRecord:
        """Pause a running execution process."""
        if record.state not in (ExecutionState.RUNNING, ExecutionState.MONITORING):
            raise ValueError(f"Cannot pause execution in state: {record.state.value}")

        record.state = ExecutionState.PAUSED
        record.audit_trail.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "PAUSE",
            "reason": reason,
        })
        logger.warning("Execution %s PAUSED manually. Reason: %s", record.execution_id, reason)
        return record

    def resume(self, record: ExecutionRecord, reason: str = "") -> ExecutionRecord:
        """Resume a paused execution process."""
        if record.state != ExecutionState.PAUSED:
            raise ValueError("Execution is not currently paused.")

        record.state = ExecutionState.RUNNING
        record.audit_trail.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "RESUME",
            "reason": reason,
        })
        logger.info("Execution %s RESUMED manually.", record.execution_id)
        return record

    def cancel(self, record: ExecutionRecord, reason: str = "") -> ExecutionRecord:
        """Cancel a pending or ready execution process."""
        if record.state in (ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.ROLLED_BACK):
            raise ValueError("Cannot cancel a completed execution.")

        record.state = ExecutionState.CANCELLED
        record.completed_at = datetime.utcnow()
        record.audit_trail.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "CANCEL",
            "reason": reason,
        })
        logger.warning("Execution %s CANCELLED. Reason: %s", record.execution_id, reason)
        return record

    def emergency_stop(self, record: ExecutionRecord, reason: str = "") -> ExecutionRecord:
        """Immediately abort a running execution process."""
        if record.state in (ExecutionState.COMPLETED, ExecutionState.ROLLED_BACK):
            raise ValueError("Execution already finished.")

        record.state = ExecutionState.EMERGENCY_STOP
        record.completed_at = datetime.utcnow()
        record.audit_trail.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "EMERGENCY_STOP",
            "reason": reason,
        })
        logger.critical("EMERGENCY STOP triggered for execution %s: %s", record.execution_id, reason)
        return record

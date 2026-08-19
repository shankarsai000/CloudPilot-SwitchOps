"""
Audit Logger Component

Creates an immutable audit trail of all decision evaluations, consensus scores,
policy checks, and approval level decisions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from models_decision import DecisionRecord

logger = logging.getLogger(__name__)


class AuditLogger:
    """Handles immutable logging and trail building for decisions."""

    def __init__(self) -> None:
        """Initialize Audit Logger."""
        self._audit_logs: list[dict[str, Any]] = []

    def log_decision(self, decision: DecisionRecord, status: str = "EVALUATED") -> dict[str, Any]:
        """Log a decision and return the audit entry.

        Args:
            decision: The decision record to audit
            status: Status of the decision event

        Returns:
            The created audit log entry dict
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "decision_id": decision.decision_id,
            "target_id": decision.target_id,
            "action": decision.action,
            "state": decision.state.value,
            "status": status,
            "score": decision.score.dict() if decision.score else None,
            "consensus": {
                "consensus_type": decision.consensus.consensus_type,
                "recommended_action": decision.consensus.recommended_action.value,
                "votes": [v.dict() for v in decision.consensus.votes],
            },
            "approval_route": decision.approval_route.dict() if decision.approval_route else None,
            "policy_report": decision.policy_report.dict() if decision.policy_report else None,
            "confidence": decision.decision_confidence,
            "explanation": decision.explanation,
        }
        self._audit_logs.append(entry)
        logger.info(
            "Audit Log created for decision %s. Status: %s. State: %s",
            decision.decision_id, status, decision.state.value
        )
        return entry

    def get_audit_trail_for_decision(self, decision_id: str) -> list[dict[str, Any]]:
        """Get all audit logs associated with a single decision.

        Args:
            decision_id: Decision identifier

        Returns:
            List of matching audit log entries
        """
        return [log for log in self._audit_logs if log["decision_id"] == decision_id]

    def get_all_logs(self) -> list[dict[str, Any]]:
        """Get all audit logs in the logger.

        Returns:
            List of all audit log entries
        """
        return list(self._audit_logs)

    def count_logs(self) -> int:
        """Return total number of audit logs.

        Returns:
            Audit log count
        """
        return len(self._audit_logs)

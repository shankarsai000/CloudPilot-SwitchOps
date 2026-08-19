"""
Audit Builder Component

Builds audit trail logs to trace users, change operations, approvals, and execution outcomes.
"""

from __future__ import annotations

import logging
from datetime import datetime
import uuid

from models_explanation import AuditTrail

logger = logging.getLogger(__name__)


class AuditBuilder:
    """Constructs immutable audit logs for change simulations and decisions."""

    def __init__(self) -> None:
        """Initialize Audit Builder."""
        pass

    def build_audit_entry(
        self,
        decision_id: str,
        action: str,
        requested_by: str = "CloudPilot-System",
        approved_by: str = None,
        outcome: str = "PENDING"
    ) -> AuditTrail:
        """Create a new AuditTrail logging entry.

        Args:
            decision_id: Target decision ID
            action: Action simulated
            requested_by: Requested by user/system
            approved_by: Approving user
            outcome: System outcome

        Returns:
            AuditTrail object
        """
        return AuditTrail(
            audit_id=f"audit-{uuid.uuid4().hex[:12]}",
            decision_id=decision_id,
            requested_by=requested_by,
            approved_by=approved_by,
            executed_by=requested_by if outcome == "SUCCESS" else None,
            action=action,
            timestamp=datetime.utcnow(),
            outcome=outcome
        )

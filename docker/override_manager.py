"""
Override Manager Component

Handles human overrides on decisions: Approve, Reject, Modify, Delay,
or Manual Execution. Every override is tracked and formatted to feed M8 Learning Agent.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from models_decision import (
    DecisionRecord,
    DecisionState,
    OverrideAction,
    OverrideRecord,
)

logger = logging.getLogger(__name__)


class OverrideManager:
    """Manages manual overrides of Decision Engine outputs."""

    def __init__(self) -> None:
        """Initialize Override Manager."""
        self._overrides: list[OverrideRecord] = []

    def apply_override(
        self,
        decision: DecisionRecord,
        action: OverrideAction,
        actor: str,
        reason: str = "",
        modified_properties: Optional[dict[str, Any]] = None,
    ) -> tuple[DecisionRecord, OverrideRecord]:
        """Apply a manual override to a decision record.

        Args:
            decision: The original DecisionRecord
            action: The override action type
            actor: The engineer performing the override
            reason: Text reason for the override
            modified_properties: Optional modifications to the decision content

        Returns:
            Tuple of (updated DecisionRecord, OverrideRecord)
        """
        original_state = decision.state
        new_state = DecisionState.PENDING

        if action == OverrideAction.APPROVE:
            new_state = DecisionState.APPROVED
        elif action == OverrideAction.REJECT:
            new_state = DecisionState.REJECTED
        elif action == OverrideAction.DELAY:
            new_state = DecisionState.PENDING
            decision.explanation += f" [Delayed by human override until {datetime.utcnow() + timedelta(days=1)}]"
        elif action == OverrideAction.MODIFY:
            new_state = DecisionState.CONDITIONAL
            if modified_properties:
                if "action" in modified_properties:
                    decision.action = modified_properties["action"]
                if "target_id" in modified_properties:
                    decision.target_id = modified_properties["target_id"]
        elif action == OverrideAction.MANUAL_EXECUTION:
            new_state = DecisionState.AUTO_APPROVED

        # Update decision state and timestamp
        decision.state = new_state
        decision.decided_at = datetime.utcnow()
        decision.explanation = (
            f"Overridden by human ({actor}) with action: {action.value}. Reason: {reason}. "
            f"Original state was: {original_state.value}."
        )

        override_record = OverrideRecord(
            override_id=f"ovr-{uuid.uuid4().hex[:10]}",
            decision_id=decision.decision_id,
            action=action,
            actor=actor,
            reason=reason,
            original_state=original_state,
            new_state=new_state,
            timestamp=datetime.utcnow(),
        )

        self._overrides.append(override_record)
        logger.info(
            "Applied override %s on decision %s by %s. State transitioned from %s to %s.",
            override_record.override_id, decision.decision_id, actor, original_state.value, new_state.value
        )

        return decision, override_record

    def get_overrides_for_decision(self, decision_id: str) -> list[OverrideRecord]:
        """Get all overrides for a specific decision.

        Args:
            decision_id: Decision identifier

        Returns:
            List of OverrideRecord instances
        """
        return [o for o in self._overrides if o.decision_id == decision_id]

    def get_all_overrides(self) -> list[OverrideRecord]:
        """Get all overrides recorded.

        Returns:
            List of OverrideRecord instances
        """
        return list(self._overrides)

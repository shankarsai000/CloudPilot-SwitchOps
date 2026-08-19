"""
Decision Agent — Main Orchestrator

Exposes interfaces to evaluate recommendations, apply overrides, manage history,
retrieve pending decisions, and format decision outputs.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from models_decision import (
    AgentVote,
    DecisionRecord,
    DecisionState,
    OverrideAction,
    OverrideRecord,
)
from decision_engine_core import DecisionEngineCore
from override_manager import OverrideManager

logger = logging.getLogger(__name__)


class DecisionAgent:
    """Orchestrator for the executive decision intelligence layer."""

    def __init__(
        self,
        core: Optional[DecisionEngineCore] = None,
        override_manager: Optional[OverrideManager] = None,
    ) -> None:
        """Initialize Decision Agent.

        Args:
            core: DecisionEngineCore instance
            override_manager: OverrideManager instance
        """
        self.core = core or DecisionEngineCore()
        self.override_manager = override_manager or OverrideManager()
        self._decisions: dict[str, DecisionRecord] = {}

        logger.info("DecisionAgent orchestrator initialized")

    def evaluate(
        self,
        target_id: str,
        action: str,
        votes: list[AgentVote],
        estimated_savings_usd: float = 0.0,
        risk_category: str = "LOW",
        region: str = "us-east-1",
        is_production: bool = False,
        compliance_frameworks: list[str] = None,
        score_inputs: Optional[dict[str, float]] = None,
    ) -> DecisionRecord:
        """Evaluate a new proposal.

        Args:
            target_id: Target resource or application
            action: Proposed action
            votes: Agent votes from M1-M8
            estimated_savings_usd: Expected savings
            risk_category: Risk category
            region: Target region
            is_production: Production flag
            compliance_frameworks: Framework names
            score_inputs: Manual score component inputs

        Returns:
            Fully evaluated DecisionRecord
        """
        record = self.core.evaluate_proposal(
            target_id=target_id,
            action=action,
            votes=votes,
            estimated_savings_usd=estimated_savings_usd,
            risk_category=risk_category,
            region=region,
            is_production=is_production,
            compliance_frameworks=compliance_frameworks,
            score_inputs=score_inputs,
        )
        self._decisions[record.decision_id] = record
        return record

    def get_decision(self, decision_id: str) -> Optional[DecisionRecord]:
        """Retrieve a decision by ID.

        Args:
            decision_id: Decision identifier

        Returns:
            DecisionRecord or None
        """
        return self._decisions.get(decision_id)

    def get_pending_decisions(self) -> list[DecisionRecord]:
        """Get all decisions currently awaiting approval.

        Returns:
            List of pending DecisionRecord instances
        """
        return [
            d for d in self._decisions.values()
            if d.state in (DecisionState.PENDING, DecisionState.REQUIRES_APPROVAL)
        ]

    def get_decision_history(self) -> list[DecisionRecord]:
        """Get the full list of evaluated decisions.

        Returns:
            List of all DecisionRecord instances
        """
        return list(self._decisions.values())

    def approve(self, decision_id: str, approver: str, reason: str = "") -> DecisionRecord:
        """Approve a pending decision manually.

        Args:
            decision_id: Decision identifier
            approver: Name of the approver
            reason: Reasoning text

        Returns:
            Updated DecisionRecord
        """
        record = self.get_decision(decision_id)
        if not record:
            raise ValueError(f"Decision {decision_id} not found")

        record, _ = self.override_manager.apply_override(
            decision=record,
            action=OverrideAction.APPROVE,
            actor=approver,
            reason=reason,
        )

        # Trigger execution package building if approved
        if not record.execution_package:
            record.execution_package = self.core.execution_builder.build(record)

        return record

    def reject(self, decision_id: str, rejecter: str, reason: str = "") -> DecisionRecord:
        """Reject a pending decision manually.

        Args:
            decision_id: Decision identifier
            rejecter: Name of the rejecter
            reason: Reasoning text

        Returns:
            Updated DecisionRecord
        """
        record = self.get_decision(decision_id)
        if not record:
            raise ValueError(f"Decision {decision_id} not found")

        record, _ = self.override_manager.apply_override(
            decision=record,
            action=OverrideAction.REJECT,
            actor=rejecter,
            reason=reason,
        )
        return record

    def apply_override(
        self,
        decision_id: str,
        action: OverrideAction,
        actor: str,
        reason: str = "",
        modified_properties: Optional[dict[str, Any]] = None,
    ) -> tuple[DecisionRecord, OverrideRecord]:
        """Apply generic manual override (e.g. modify, delay, manual execution).

        Args:
            decision_id: Decision identifier
            action: OverrideAction enum
            actor: Name of the actor
            reason: Reasoning text
            modified_properties: Modifications map

        Returns:
            Tuple of (updated DecisionRecord, OverrideRecord)
        """
        record = self.get_decision(decision_id)
        if not record:
            raise ValueError(f"Decision {decision_id} not found")

        updated_record, override_record = self.override_manager.apply_override(
            decision=record,
            action=action,
            actor=actor,
            reason=reason,
            modified_properties=modified_properties,
        )

        # Build execution package if state transitioned to approved
        if updated_record.state in (DecisionState.APPROVED, DecisionState.AUTO_APPROVED) and not updated_record.execution_package:
            updated_record.execution_package = self.core.execution_builder.build(updated_record)

        return updated_record, override_record

    def get_audit_trail(self) -> list[dict[str, Any]]:
        """Get the full decision audit trail.

        Returns:
            List of audit log entries
        """
        return self.core.audit_logger.get_all_logs()

    def get_override_history(self) -> list[OverrideRecord]:
        """Get the full list of human overrides.

        Returns:
            List of OverrideRecord instances
        """
        return self.override_manager.get_all_overrides()

    def clear(self) -> None:
        """Clear cache (for tests)."""
        self._decisions.clear()
        self.override_manager._overrides.clear()
        self.core.audit_logger._audit_logs.clear()

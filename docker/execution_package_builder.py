"""
Execution Package Builder Component

Assembles the complete execution package for M10: decision, strategy,
rollback plan, simulation summary, risk report, execution steps, and
approval metadata.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from models_decision import (
    ApprovalRoute,
    DecisionRecord,
    DecisionScore,
    ExecutionPackage,
    PolicyComplianceReport,
)

logger = logging.getLogger(__name__)


class ExecutionPackageBuilder:
    """Builds complete execution packages for downstream automation."""

    def __init__(self) -> None:
        """Initialize Execution Package Builder."""
        pass

    def build(
        self,
        decision: DecisionRecord,
        strategy_summary: str = "",
        rollback_plan: dict[str, Any] = None,
        simulation_summary: dict[str, Any] = None,
        risk_summary: dict[str, Any] = None,
        execution_steps: list[dict[str, Any]] = None,
    ) -> ExecutionPackage:
        """Build a complete execution package from a decision record.

        Args:
            decision: Finalized DecisionRecord
            strategy_summary: Summary of the optimization strategy
            rollback_plan: Rollback steps and conditions
            simulation_summary: Digital twin simulation results
            risk_summary: Risk analysis summary
            execution_steps: Ordered list of execution steps

        Returns:
            ExecutionPackage ready for M10
        """
        approval_meta: dict[str, Any] = {}
        if decision.approval_route:
            approval_meta = {
                "level": decision.approval_route.level.value,
                "reason": decision.approval_route.reason,
                "risk_category": decision.approval_route.risk_category,
            }

        package = ExecutionPackage(
            package_id=f"pkg-{uuid.uuid4().hex[:10]}",
            decision_id=decision.decision_id,
            target_id=decision.target_id,
            action=decision.action,
            strategy_summary=strategy_summary,
            rollback_plan=rollback_plan or self._default_rollback(decision),
            simulation_summary=simulation_summary or {},
            risk_summary=risk_summary or {},
            execution_steps=execution_steps or self._default_steps(decision),
            approval_metadata=approval_meta,
            estimated_duration_minutes=self._estimate_duration(decision.action),
            created_at=datetime.utcnow(),
        )

        logger.info(
            "Built execution package %s for decision %s",
            package.package_id, decision.decision_id,
        )
        return package

    def _default_rollback(self, decision: DecisionRecord) -> dict[str, Any]:
        """Generate a default rollback plan.

        Args:
            decision: Decision record

        Returns:
            Rollback plan dict
        """
        return {
            "strategy": "revert-to-previous-state",
            "target_id": decision.target_id,
            "trigger_conditions": ["error_rate > 5%", "latency_p99 > 500ms"],
            "timeout_minutes": 15,
        }

    def _default_steps(self, decision: DecisionRecord) -> list[dict[str, Any]]:
        """Generate default execution steps.

        Args:
            decision: Decision record

        Returns:
            Ordered execution steps
        """
        return [
            {"step": 1, "action": "snapshot_current_state", "target": decision.target_id},
            {"step": 2, "action": "validate_prerequisites", "target": decision.target_id},
            {"step": 3, "action": decision.action, "target": decision.target_id},
            {"step": 4, "action": "verify_health", "target": decision.target_id},
            {"step": 5, "action": "confirm_completion", "target": decision.target_id},
        ]

    def _estimate_duration(self, action: str) -> float:
        """Estimate execution duration based on action type.

        Args:
            action: Action type

        Returns:
            Estimated minutes
        """
        duration_map = {
            "RESIZE": 10.0,
            "TERMINATE": 2.0,
            "SCALE_OUT": 15.0,
            "SCALE_IN": 10.0,
            "MIGRATE": 30.0,
            "UPGRADE": 20.0,
            "DELETE": 2.0,
            "RESTART": 5.0,
        }
        return duration_map.get(action.upper(), 5.0)

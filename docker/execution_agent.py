"""
Execution Agent — Main Orchestrator

Consumes execution packages and exposes interfaces to initiate, pause, resume,
cancel, or manually rollback execution runs.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models_execution import ExecutionRecord, ExecutionState, RolloutStrategy
from execution_orchestrator import ExecutionOrchestrator
from emergency_controller import EmergencyController

logger = logging.getLogger(__name__)


class ExecutionAgent:
    """Orchestrator for the autonomous execution & control layer."""

    def __init__(
        self,
        orchestrator: Optional[ExecutionOrchestrator] = None,
        emergency_controller: Optional[EmergencyController] = None,
    ) -> None:
        """Initialize Execution Agent.

        Args:
            orchestrator: ExecutionOrchestrator instance
            emergency_controller: EmergencyController instance
        """
        self.orchestrator = orchestrator or ExecutionOrchestrator()
        self.emergency_controller = emergency_controller or EmergencyController()
        self._executions: dict[str, ExecutionRecord] = {}

        logger.info("ExecutionAgent orchestrator initialized")

    def start_execution(
        self,
        decision_id: str,
        target_id: str,
        action: str,
        approval_metadata: dict[str, Any],
        rollback_plan: dict[str, Any],
        provider: str = "AWS",
        rollout_strategy: RolloutStrategy = RolloutStrategy.DIRECT,
        has_violations: bool = False,
    ) -> ExecutionRecord:
        """Start a new execution run.

        Args:
            decision_id: ID of the decision
            target_id: Target resource or application
            action: Action type
            approval_metadata: Approval metadata
            rollback_plan: Reversion plans
            provider: Target provider name
            rollout_strategy: Strategy choice
            has_violations: Flag indicating if violations exist

        Returns:
            Completed or active ExecutionRecord
        """
        record = self.orchestrator.process_execution(
            decision_id=decision_id,
            target_id=target_id,
            action=action,
            approval_metadata=approval_metadata,
            rollback_plan=rollback_plan,
            provider=provider,
            rollout_strategy=rollout_strategy,
            has_violations=has_violations,
        )

        self._executions[record.execution_id] = record
        return record

    def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        """Retrieve execution by ID."""
        return self._executions.get(execution_id)

    def get_execution_status(self, execution_id: str) -> Optional[str]:
        """Get status value for an execution."""
        record = self.get_execution(execution_id)
        return record.state.value if record else None

    def get_execution_logs(self, execution_id: str) -> list[dict[str, Any]]:
        """Retrieve log events registered for a specific execution."""
        events = self.orchestrator.logger.get_events_for_execution(execution_id)
        return [e.dict() for e in events]

    def get_execution_history(self) -> list[ExecutionRecord]:
        """Get all past and active execution records."""
        return list(self._executions.values())

    def pause_execution(self, execution_id: str, reason: str = "") -> ExecutionRecord:
        """Pause a running execution."""
        record = self.get_execution(execution_id)
        if not record:
            raise ValueError(f"Execution {execution_id} not found")
        return self.emergency_controller.pause(record, reason)

    def resume_execution(self, execution_id: str, reason: str = "") -> ExecutionRecord:
        """Resume a paused execution."""
        record = self.get_execution(execution_id)
        if not record:
            raise ValueError(f"Execution {execution_id} not found")
        return self.emergency_controller.resume(record, reason)

    def cancel_execution(self, execution_id: str, reason: str = "") -> ExecutionRecord:
        """Cancel a pending/ready execution."""
        record = self.get_execution(execution_id)
        if not record:
            raise ValueError(f"Execution {execution_id} not found")
        return self.emergency_controller.cancel(record, reason)

    def emergency_stop(self, execution_id: str, reason: str = "") -> ExecutionRecord:
        """Trigger an emergency stop."""
        record = self.get_execution(execution_id)
        if not record:
            raise ValueError(f"Execution {execution_id} not found")
        return self.emergency_controller.emergency_stop(record, reason)

    def trigger_manual_rollback(
        self, execution_id: str, trigger_reason: str, rollback_plan: dict[str, Any]
    ) -> ExecutionRecord:
        """Manually trigger a rollback on a completed or failed execution."""
        record = self.get_execution(execution_id)
        if not record:
            raise ValueError(f"Execution {execution_id} not found")

        record.state = ExecutionState.ROLLING_BACK
        self.orchestrator.logger.log_event(execution_id, f"Manual rollback triggered: {trigger_reason}", level="WARNING")

        rollback_rec = self.orchestrator.rollback_engine.execute_rollback(
            execution_id=execution_id,
            target_id=record.target_id,
            action=record.action,
            trigger_reason=trigger_reason,
            rollback_plan=rollback_plan,
        )

        record.rollback_history.append(rollback_rec)
        if rollback_rec.status == "COMPLETED":
            record.state = ExecutionState.ROLLED_BACK
        else:
            record.state = ExecutionState.FAILED

        return record

    def clear(self) -> None:
        """Clear execution states (for tests)."""
        self._executions.clear()
        self.orchestrator.logger.clear()
        self.orchestrator.policy_guard.clear()

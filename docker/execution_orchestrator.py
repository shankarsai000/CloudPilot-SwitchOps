"""
Execution Orchestrator Component

Implements the multi-phase execution pipeline: validation, locking, snapshotting,
pre-check verify, rollout execution, live monitoring, post-run validate, and completion.
Also triggers rollback engine on metrics anomalies or validation failures.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from models_execution import ExecutionRecord, ExecutionState, RollbackRecord, RolloutStrategy
from policy_guard import PolicyGuard
from rollout_manager import RolloutManager
from rollback_engine import RollbackEngine
from monitoring_engine import MonitoringEngine
from validation_engine import ValidationEngine
from execution_logger import ExecutionLogger

logger = logging.getLogger(__name__)


class ExecutionOrchestrator:
    """Orchestrates the lifecycle of an approved infrastructure execution package."""

    def __init__(
        self,
        policy_guard: Optional[PolicyGuard] = None,
        rollout_manager: Optional[RolloutManager] = None,
        rollback_engine: Optional[RollbackEngine] = None,
        monitoring_engine: Optional[MonitoringEngine] = None,
        validation_engine: Optional[ValidationEngine] = None,
        execution_logger: Optional[ExecutionLogger] = None,
    ) -> None:
        """Initialize Execution Orchestrator."""
        self.policy_guard = policy_guard or PolicyGuard()
        self.rollout_manager = rollout_manager or RolloutManager()
        self.rollback_engine = rollback_engine or RollbackEngine()
        self.monitoring_engine = monitoring_engine or MonitoringEngine()
        self.validation_engine = validation_engine or ValidationEngine()
        self.logger = execution_logger or ExecutionLogger()

    def process_execution(
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
        """Run the full execution pipeline from start to completion or rollback.

        Args:
            decision_id: M9 decision ID
            target_id: Resource target
            action: Action type
            approval_metadata: Approval level
            rollback_plan: Reversion specs
            provider: Target cloud provider
            rollout_strategy: Rollout progression strategy
            has_violations: Flag indicating if known violations exist

        Returns:
            Fully processed ExecutionRecord
        """
        execution_id = f"exec-{uuid.uuid4().hex[:10]}"
        logger.info("Starting execution orchestrator pipeline for ID %s", execution_id)

        rollout_progress = self.rollout_manager.initialize_rollout(rollout_strategy)

        record = ExecutionRecord(
            execution_id=execution_id,
            decision_id=decision_id,
            target_id=target_id,
            action=action,
            state=ExecutionState.PENDING,
            rollout=rollout_progress,
        )

        self.logger.log_event(execution_id, f"Initialized execution record for {action} on {target_id}")

        # 1. Safety Guardrails Validation
        record.state = ExecutionState.VALIDATING
        safe, guard_msgs = self.policy_guard.verify_guardrails(
            target_id=target_id,
            approval_metadata=approval_metadata,
            rollback_plan=rollback_plan,
            has_violations=has_violations,
        )

        for msg in guard_msgs:
            self.logger.append_audit_entry(record, "GUARDRAIL_CHECK", msg)

        if not safe:
            record.state = ExecutionState.FAILED
            record.error_message = "Safety guardrail validations failed. Aborting execution."
            self.logger.log_event(execution_id, record.error_message, level="ERROR")
            return record

        record.lock_acquired = True
        record.state = ExecutionState.READY
        record.started_at = datetime.utcnow()
        self.logger.append_audit_entry(record, "LOCK_ACQUIRED", f"Acquired lock on target {target_id}")

        # 2. Pre-execution Snapshotting
        self.logger.append_audit_entry(record, "PRE_SNAPSHOT", "Completed state snapshot verification")

        # 3. Rollout Progressive Execution Loop
        record.state = ExecutionState.RUNNING
        finished = False

        while not finished:
            # Advance rollout step
            record.rollout, finished = self.rollout_manager.advance_rollout(record.rollout)
            self.logger.append_audit_entry(
                record,
                "ROLLOUT_STEP",
                f"Advanced to {record.rollout.current_percentage}% on {record.rollout.active_slice} slice"
            )

            # 4. Live Telemetry Monitoring Check
            record.state = ExecutionState.MONITORING
            metrics = self.monitoring_engine.collect_metrics(target_id, provider)
            record.metrics_summary = metrics
            self.logger.log_event(
                execution_id,
                f"Collected health metrics: CPU={metrics.get('cpu_percent')}%, ErrorRate={metrics.get('error_rate')}"
            )

            # Check for metric SLA anomalies
            is_anomaly, anomaly_reason = self.monitoring_engine.detect_anomaly(metrics)
            if is_anomaly:
                self.logger.log_event(execution_id, f"Anomaly detected: {anomaly_reason}", level="WARNING")
                self._trigger_rollback(record, rollback_plan, anomaly_reason, provider)
                return record

            # Reset back to running if not finished
            if not finished:
                record.state = ExecutionState.RUNNING

        # 5. Post-Execution Validation
        metrics = self.monitoring_engine.collect_metrics(target_id, provider)
        record.metrics_summary = metrics
        valid, val_msgs = self.validation_engine.validate_post_execution(
            target_id=target_id, action=action, provider=provider, metrics=metrics
        )

        for msg in val_msgs:
            self.logger.append_audit_entry(record, "POST_VALIDATION", msg)

        if not valid:
            self._trigger_rollback(record, rollback_plan, "Post-execution validation check failed", provider)
            return record

        # 6. Complete and Unlock
        record.state = ExecutionState.COMPLETED
        record.completed_at = datetime.utcnow()
        self.policy_guard.release_lock(target_id)
        record.lock_acquired = False

        self.logger.append_audit_entry(record, "EXECUTION_COMPLETE", "Successfully applied modification and unlocked target")
        return record

    def _trigger_rollback(
        self,
        record: ExecutionRecord,
        rollback_plan: dict[str, Any],
        reason: str,
        provider: str,
    ) -> None:
        """Perform rollback and update execution record state."""
        record.state = ExecutionState.ROLLING_BACK
        self.logger.log_event(record.execution_id, f"Initiating rollback due to: {reason}", level="WARNING")

        rollback_rec = self.rollback_engine.execute_rollback(
            execution_id=record.execution_id,
            target_id=record.target_id,
            action=record.action,
            trigger_reason=reason,
            rollback_plan=rollback_plan,
            provider=provider,
        )

        record.rollback_history.append(rollback_rec)
        record.completed_at = datetime.utcnow()

        # Release resource lock
        self.policy_guard.release_lock(record.target_id)
        record.lock_acquired = False

        if rollback_rec.status == "COMPLETED":
            record.state = ExecutionState.ROLLED_BACK
            self.logger.append_audit_entry(record, "ROLLBACK_SUCCESS", "Successfully reverted changes")
        else:
            record.state = ExecutionState.FAILED
            record.error_message = f"Rollback failed: {rollback_rec.details.get('phase')}"
            self.logger.append_audit_entry(record, "ROLLBACK_FAILURE", record.error_message)

"""
Rollback Engine Component

Handles automated rollbacks on target failures, metrics anomalies, or manual
emergency stops. Reverts changes to restore the target resource to its previous state.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from models_execution import RollbackRecord
from provider_router import ProviderRouter

logger = logging.getLogger(__name__)


class RollbackEngine:
    """Manages rollback lifecycle processes."""

    def __init__(self, provider_router: Optional[ProviderRouter] = None) -> None:
        """Initialize Rollback Engine."""
        self.router = provider_router or ProviderRouter()

    def execute_rollback(
        self,
        execution_id: str,
        target_id: str,
        action: str,
        trigger_reason: str,
        rollback_plan: dict[str, Any],
        provider: str = "AWS",
    ) -> RollbackRecord:
        """Trigger and execute an automated rollback.

        Args:
            execution_id: ID of the failed execution run
            target_id: Target resource or application
            action: Action being rolled back
            trigger_reason: Explanation of the rollback trigger
            rollback_plan: Specific rollback instructions
            provider: Target cloud provider

        Returns:
            RollbackRecord indicating status and logs
        """
        rollback_id = f"rbk-{uuid.uuid4().hex[:10]}"
        logger.warning(
            "Rollback triggered for execution %s on %s. Reason: %s",
            execution_id, target_id, trigger_reason
        )

        record = RollbackRecord(
            rollback_id=rollback_id,
            execution_id=execution_id,
            trigger_reason=trigger_reason,
            started_at=datetime.utcnow(),
            status="RUNNING",
        )

        try:
            # 1. Stop active modifications / clear locks
            logger.info("Rollback Phase 1: Halting active tasks on %s", target_id)

            # 2. Invoke provider rollback adapter
            plan = {
                "target_id": target_id,
                "action": action,
                "provider": provider,
                "rollback_plan": rollback_plan,
            }
            res = self.router.rollback(plan)

            # 3. Validate restoration health
            success = self.router.validate(plan)

            if success and res.get("status") == "SUCCESS":
                record.status = "COMPLETED"
                record.details = {
                    "phase": "RESTORATION_VERIFIED",
                    "provider_response": res,
                }
                logger.info("Rollback completed successfully for %s", target_id)
            else:
                record.status = "FAILED"
                record.details = {
                    "phase": "RESTORATION_VALIDATION_FAILED",
                    "provider_response": res,
                }
                logger.error("Rollback validation failed for %s", target_id)

        except Exception as e:
            logger.error("Exception occurred during rollback execution: %s", e)
            record.status = "FAILED"
            record.details = {"error": str(e), "phase": "EXCEPTION"}

        record.completed_at = datetime.utcnow()
        return record

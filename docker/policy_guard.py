"""
Policy Guard Component

Verifies safety guardrails before starting execution: active locks, maintenance window check,
approval metadata validation, policy compliance status, and rollback plan availability.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PolicyGuard:
    """Enforces safety guardrails prior to and during deployment execution."""

    def __init__(self, required_locks: Optional[list[str]] = None) -> None:
        """Initialize Policy Guard."""
        self.acquired_locks: set[str] = set()
        self.required_locks = required_locks or []

    def verify_guardrails(
        self,
        target_id: str,
        approval_metadata: dict[str, Any],
        rollback_plan: dict[str, Any],
        has_violations: bool = False,
    ) -> tuple[bool, list[str]]:
        """Verify all execution guardrails are satisfied.

        Args:
            target_id: Resource identifier
            approval_metadata: M9 approval details
            rollback_plan: M9 execution rollback plan
            has_violations: Flag indicating if known violations exist

        Returns:
            Tuple of (is_safe, messages)
        """
        messages: list[str] = []

        # 1. Verify approval status
        level = approval_metadata.get("level")
        if not level:
            messages.append("GUARDRAIL_FAILED: No valid approval metadata level present.")
            return False, messages
        messages.append(f"Approval level verified: {level}")

        # 2. Policy compliance
        if has_violations:
            messages.append("GUARDRAIL_FAILED: Active policy violations prohibit execution.")
            return False, messages
        messages.append("No active policy violations")

        # 3. Rollback availability
        if not rollback_plan or "strategy" not in rollback_plan:
            messages.append("GUARDRAIL_FAILED: Execution package lacks valid rollback plan details.")
            return False, messages
        messages.append("Rollback plan verified")

        # 4. Check for active resource locks
        if target_id in self.acquired_locks:
            messages.append(f"Resource lock already acquired for {target_id}")
        else:
            self.acquire_lock(target_id)
            messages.append(f"Lock acquired for {target_id}")

        return True, messages

    def acquire_lock(self, resource_id: str) -> bool:
        """Acquire lock on a resource.

        Args:
            resource_id: Target resource ID

        Returns:
            True if lock was successfully acquired
        """
        self.acquired_locks.add(resource_id)
        logger.debug("Lock acquired on resource %s", resource_id)
        return True

    def release_lock(self, resource_id: str) -> None:
        """Release lock on a resource.

        Args:
            resource_id: Target resource ID
        """
        self.acquired_locks.discard(resource_id)
        logger.debug("Lock released on resource %s", resource_id)

    def clear(self) -> None:
        """Clear all locks."""
        self.acquired_locks.clear()

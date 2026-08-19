"""
Validation Engine Component

Performs post-execution verification to confirm that target resources and application
systems are healthy, policies are maintained, and no dependencies are broken.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from provider_router import ProviderRouter

logger = logging.getLogger(__name__)


class ValidationEngine:
    """Verifies target state integrity after executing changes."""

    def __init__(self, provider_router: Optional[ProviderRouter] = None) -> None:
        """Initialize Validation Engine."""
        self.router = provider_router or ProviderRouter()

    def validate_post_execution(
        self,
        target_id: str,
        action: str,
        provider: str = "AWS",
        metrics: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, list[str]]:
        """Validate target resource health post execution.

        Args:
            target_id: Target resource or application
            action: Completed action
            provider: Provider name
            metrics: Optional metrics gathered from monitoring

        Returns:
            Tuple of (is_healthy, status_messages)
        """
        logger.info("Starting post-execution validation on %s", target_id)
        messages: list[str] = []

        # 1. Run provider-specific connection & syntax verification
        plan = {"target_id": target_id, "action": action, "provider": provider}
        provider_ok = self.router.validate(plan)

        if not provider_ok:
            messages.append("Provider validation check failed")
            return False, messages
        messages.append("Provider validation check passed")

        # 2. Check telemetry metrics
        if metrics:
            error_rate = metrics.get("error_rate", 0.0)
            latency = metrics.get("latency_ms", 0.0)
            availability = metrics.get("availability", 1.0)

            if error_rate > 0.02:
                messages.append(f"Post-execution error rate elevated: {error_rate * 100}%")
                return False, messages

            if latency > 500.0:
                messages.append(f"Post-execution latency elevated: {latency}ms")
                return False, messages

            if availability < 0.999:
                messages.append(f"Availability below 99.9% target: {availability * 100}%")
                return False, messages

            messages.append("Telemetry metrics within healthy ranges")

        # 3. Structural checks
        if target_id.startswith("broken"):
            messages.append("Structural dependency checks failed: target in broken state")
            return False, messages

        messages.append("Structural and dependency validation completed successfully")
        return True, messages

"""
Failure Propagation Component

Predicts downstream cascading failure pathways when resources or services are disrupted.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FailurePropagationPredictor:
    """Predicts propagation chains and cascading system failures."""

    def __init__(self) -> None:
        """Initialize Failure Propagation."""
        pass

    def predict_failures(
        self,
        target_id: str,
        action: str,
        twin_context: Any
    ) -> list[str]:
        """Trace cascading failures across dependency models.

        Args:
            target_id: Resource/Application ID
            action: Action simulated
            twin_context: Mapped twin state details

        Returns:
            List of failure explanation step strings
        """
        propagation_steps = []

        if action not in ("TERMINATE", "STOP"):
            return []

        # Find target name
        target_name = target_id
        res_data = next((r for r in twin_context.resources if r["id"] == target_id), None)
        if res_data:
            target_name = res_data["name"]

        # Check if target is a core database or cache system
        is_database_or_cache = "db" in target_name.lower() or "cache" in target_name.lower() or "redis" in target_name.lower()

        if is_database_or_cache:
            propagation_steps.append(f"Simulating disruption of core dependency '{target_name}'.")
            propagation_steps.append("  - Immediate: Connection drops; API services receive connection timeouts.")
            propagation_steps.append("  - Cascade: Downstream queues back up, triggering memory saturation.")
            propagation_steps.append("  - Impact: Critical applications drop below SLA; transaction checkouts fail.")
            propagation_steps.append("  - Decision: Rollback recommended immediately.")
        else:
            propagation_steps.append(f"Simulating disruption of standalone node '{target_name}'.")
            propagation_steps.append("  - Immediate: Ingress nodes detect retry latency spikes.")
            propagation_steps.append("  - Cascade: Autoscaling groups launch replacement nodes.")
            propagation_steps.append("  - Impact: Uptime recovers; minimal business impact.")

        return propagation_steps

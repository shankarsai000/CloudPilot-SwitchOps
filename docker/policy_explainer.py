"""
Policy Explainer Component

Explains policy violations and compliance boundaries (e.g. databases, PCI constraints, maintenance windows).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PolicyExplainer:
    """Explains compliance violations and lists backing reasons."""

    def __init__(self) -> None:
        """Initialize Policy Explainer."""
        pass

    def explain_violations(self, violations: list[str]) -> str:
        """Formulate explanations for policy blocks.

        Args:
            violations: List of violations

        Returns:
            Exploratory explanation string
        """
        if not violations:
            return "All organizational policies and compliance controls are satisfied."

        reasons = []
        for violation in violations:
            if "POL-DB" in violation:
                reasons.append("Blocked: Production database modification rule. Terminating primary databases is restricted to SRE command overrides.")
            elif "POL-PAY" in violation:
                reasons.append("High Risk: Payment service resized during peak traffic business hours. Schedule optimization during standard maintenance windows.")
            elif "POL-K8S" in violation:
                reasons.append("Blocked: Kubernetes control plane nodes must be scaled using helm upgrade cycles, direct server restarts are blocked.")
            elif "POL-PCI" in violation:
                reasons.append("Blocked: PCI-DSS compliance locked. Any modify operations require authorized PCI audit sign-offs.")
            else:
                reasons.append(f"Violation details: {violation}")

        return " ".join(reasons)

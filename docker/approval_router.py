"""
Approval Router Component

Routes decisions to the appropriate approval level based on a configurable
risk/savings matrix: Auto Execute, Engineering Lead, SRE Team, Security Team,
Executive Approval.
"""

from __future__ import annotations

import logging
from typing import Any

from models_decision import ApprovalLevel, ApprovalRoute

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS = {
    "auto_max_savings": 500.0,
    "engineering_max_savings": 5000.0,
    "sre_max_savings": 25000.0,
}


class ApprovalRouter:
    """Routes decisions to the correct approval level."""

    def __init__(self, thresholds: dict[str, float] = None) -> None:
        """Initialize Approval Router with configurable thresholds.

        Args:
            thresholds: Savings thresholds for each approval level
        """
        self.thresholds = thresholds or dict(DEFAULT_THRESHOLDS)

    def route(
        self,
        risk_category: str,
        estimated_savings_usd: float,
        has_policy_violations: bool = False,
    ) -> ApprovalRoute:
        """Determine the approval routing for a decision.

        Args:
            risk_category: Risk classification (LOW, MEDIUM, HIGH, CRITICAL)
            estimated_savings_usd: Expected monthly savings
            has_policy_violations: Whether policy violations exist

        Returns:
            ApprovalRoute with level and reasoning
        """
        # Policy violations always require at least SRE approval
        if has_policy_violations:
            return ApprovalRoute(
                level=ApprovalLevel.SECURITY_TEAM,
                reason="Policy violations detected. Security team review required.",
                risk_category=risk_category,
                estimated_savings_usd=estimated_savings_usd,
            )

        # Critical risk always goes to executive
        if risk_category == "CRITICAL":
            return ApprovalRoute(
                level=ApprovalLevel.EXECUTIVE_APPROVAL,
                reason=f"Critical risk level. Executive approval required regardless of savings (${estimated_savings_usd:.2f}).",
                risk_category=risk_category,
                estimated_savings_usd=estimated_savings_usd,
            )

        # Route based on savings thresholds
        auto_max = self.thresholds.get("auto_max_savings", 500.0)
        eng_max = self.thresholds.get("engineering_max_savings", 5000.0)
        sre_max = self.thresholds.get("sre_max_savings", 25000.0)

        if risk_category == "LOW" and estimated_savings_usd <= auto_max:
            return ApprovalRoute(
                level=ApprovalLevel.AUTO_EXECUTE,
                reason=f"Low risk, savings ${estimated_savings_usd:.2f} within auto-execute threshold.",
                risk_category=risk_category,
                estimated_savings_usd=estimated_savings_usd,
            )

        if estimated_savings_usd <= eng_max:
            return ApprovalRoute(
                level=ApprovalLevel.ENGINEERING_LEAD,
                reason=f"Savings ${estimated_savings_usd:.2f} requires engineering lead approval.",
                risk_category=risk_category,
                estimated_savings_usd=estimated_savings_usd,
            )

        if estimated_savings_usd <= sre_max:
            return ApprovalRoute(
                level=ApprovalLevel.SRE_TEAM,
                reason=f"Savings ${estimated_savings_usd:.2f} requires SRE team approval.",
                risk_category=risk_category,
                estimated_savings_usd=estimated_savings_usd,
            )

        return ApprovalRoute(
            level=ApprovalLevel.EXECUTIVE_APPROVAL,
            reason=f"Savings ${estimated_savings_usd:.2f} exceeds SRE threshold. Executive approval required.",
            risk_category=risk_category,
            estimated_savings_usd=estimated_savings_usd,
        )

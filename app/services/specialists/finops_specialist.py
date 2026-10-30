"""
CloudPilot SwitchOps — FinOps Specialist Agent

Specialist agent responsible for infrastructure cost intelligence,
pricing catalog lookups, and financial hygiene enforcement.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.domain.inventory import InfrastructureInventory
from app.services.finops.catalog import PricingCatalog
from app.services.finops.engine import FinOpsAnalysisResult, FinOpsEngine

logger = logging.getLogger("cloudpilot.specialists.finops")


class FinOpsSpecialist:
    """
    Autonomous FinOps Specialist agent executing financial audits and cost breakdowns.
    """

    agent_id: str = "finops-specialist"
    agent_name: str = "CloudPilot FinOps Specialist"

    def __init__(self, catalog: Optional[PricingCatalog] = None, monthly_hours: int = 730) -> None:
        self.engine = FinOpsEngine(catalog=catalog, monthly_hours=monthly_hours)

    def analyze(self, inventory: InfrastructureInventory, task_id: str) -> FinOpsAnalysisResult:
        """Execute FinOps baseline cost and hygiene analysis."""
        logger.info("FinOpsSpecialist evaluating inventory for task '%s'", task_id)
        return self.engine.analyze(inventory=inventory, task_id=task_id)

    def format_switch_message(self, result: FinOpsAnalysisResult) -> str:
        """Format an intermediate Switch room progress update."""
        lines = [
            f"💰 **FinOps Intelligence Report** (`{self.agent_id}`)",
            f"- **Estimated Monthly Baseline**: **${result.total_monthly_cost} {result.currency}**",
            f"- **Billable Components Evaluated**: {len(result.items)}",
            f"- **Financial Hygiene Findings**: {len(result.findings)}",
            "",
            "**Key Cost Drivers & Sizing:**",
        ]

        if not result.items:
            lines.append("  _No billable cloud/container resources identified._")
        else:
            for item in result.items[:6]:  # Show top 6
                lines.append(
                    f"  • `{item.resource_name}` ({item.sku}): **${item.monthly_cost}**/mo ({item.pricing_unit})"
                )

        if result.findings:
            lines.append("")
            lines.append("**Financial Optimization Flags:**")
            for f in result.findings[:4]:
                lines.append(f"  • [{f.rule_id}] **{f.title}** (Severity: {f.severity.value})")

        return "\n".join(lines)

"""
CloudPilot SwitchOps — SecOps and SRE Specialist Agent

Specialist agent responsible for vulnerability analysis, network exposure audits,
and SRE reliability/resilience posture evaluation.
"""

from __future__ import annotations

import logging
from app.domain.inventory import InfrastructureInventory
from app.services.secops.engine import SecOpsAnalysisResult, SecOpsEngine

logger = logging.getLogger("cloudpilot.specialists.secops")


class SecOpsSpecialist:
    """
    Autonomous SecOps Specialist agent executing security and reliability audits.
    """

    agent_id: str = "secops-specialist"
    agent_name: str = "CloudPilot SecOps Specialist"

    def __init__(self) -> None:
        self.engine = SecOpsEngine()

    def analyze(self, inventory: InfrastructureInventory, task_id: str) -> SecOpsAnalysisResult:
        """Execute SecOps vulnerability and reliability inspection."""
        logger.info("SecOpsSpecialist evaluating inventory for task '%s'", task_id)
        return self.engine.analyze(inventory=inventory, task_id=task_id)

    def format_switch_message(self, result: SecOpsAnalysisResult) -> str:
        """Format an intermediate Switch room progress update."""
        lines = [
            f"🛡️ **SecOps & SRE Audit Report** (`{self.agent_id}`)",
            f"- **Security Findings**: {len(result.security_findings)}",
            f"- **Reliability Deficits**: {len(result.reliability_findings)}",
            f"- **Severity Breakdown**: 🚨 {result.critical_count} Critical | ⚠️ {result.high_count} High | ℹ️ {result.medium_count} Med | 📋 {result.low_count} Low",
            "",
            "**Critical & High Priority Findings:**",
        ]

        priority_findings = [f for f in result.all_findings if f.severity.value in ("CRITICAL", "HIGH")]

        if not priority_findings:
            lines.append("  _No critical or high-severity vulnerabilities detected._")
        else:
            for f in priority_findings[:6]:  # Show top 6
                lines.append(
                    f"  • [{f.rule_id}] **{f.title}** ({f.category.value} - `{f.source_file}`)"
                )
                lines.append(f"    ↳ _Remediation_: {f.recommendation}")

        return "\n".join(lines)

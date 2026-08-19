"""
Root Cause Analyzer Component

Computes clear explanation traces for risk decisions, tracing technical dependencies
to business impact outcomes.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from models_resource import CloudResource
from models_application import Application

logger = logging.getLogger(__name__)


class RootCauseAnalyzer:
    """Analyzes and formulates trace explanation paths for risk engine predictions."""

    def __init__(self) -> None:
        """Initialize Root Cause Analyzer."""
        pass

    def generate_explanation(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str,
        downstream_data: dict[str, Any],
        policy_violations: list[str],
        cost_correlation_data: dict[str, Any]
    ) -> list[str]:
        """Generate human-readable explanations of risk assessments.

        Args:
            resource: Evaluated resource
            application: Application context
            action: Action simulated
            downstream_data: Dependency analyzer details
            policy_violations: List of policy violations
            cost_correlation_data: Financial correlation results

        Returns:
            List of text trace explanations
        """
        explanations = []

        # Target classification
        target_name = resource.name if resource else application.name if application else "Unknown Target"
        explanations.append(f"Analyzing simulated action '{action}' on target '{target_name}'.")

        # 1. Policy Violations
        if policy_violations:
            explanations.append("CRITICAL: Actions violate organizational guardrails.")
            for violation in policy_violations:
                explanations.append(f"  - Policy Violation: {violation}")

        # 2. Dependency Cascade Paths
        root_service_name = downstream_data.get("root_service_name")
        affected_services = downstream_data.get("affected_service_ids", [])
        impact_paths = downstream_data.get("impact_paths", [])

        if affected_services and len(affected_services) > 1:
            explanations.append(
                f"HIGH RISK: Cascadable dependency path identified. Disrupting {root_service_name} "
                f"affects {len(affected_services) - 1} dependent services."
            )
            for path in impact_paths[:2]:  # list top 2 paths
                # Path represents IDs, we show a simplified trace
                explanations.append(f"  - Failure Trace: {' -> '.join(path)}")

        # 3. Business Criticality
        if application and application.criticality:
            crit = application.criticality
            explanations.append(
                f"Business Context: Application '{application.name}' has a criticality score of "
                f"{crit.criticality_score}/100 (Availability SLA: {crit.availability_target}%)."
            )

        # 4. Cost vs Risk correlation
        is_idle = cost_correlation_data.get("is_idle", False)
        if is_idle:
            explanations.append("Notice: Cost optimization opportunity. Resource is idle with low risk.")
        
        return explanations

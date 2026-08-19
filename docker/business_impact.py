"""
Business Impact Component

Evaluates business damage, SLA targets, revenue risks, and cost correlation metrics.
Determines whether lower cost changes translate into higher operational risk.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from models_application import Application
from models_impact import BusinessImpactReport
from models_resource import CloudResource

logger = logging.getLogger(__name__)


class BusinessImpactEvaluator:
    """Evaluates business-level consequences and cost-vs-risk correlations."""

    def __init__(self) -> None:
        """Initialize Business Impact Evaluator."""
        pass

    def evaluate_impact(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str,
        cost_correlation_data: dict[str, Any]
    ) -> BusinessImpactReport:
        """Assess operational damage scale against revenue, customers, and SLA compliance metrics.

        Args:
            resource: Resource being assessed
            application: Application context
            action: Action simulated
            cost_correlation_data: Pre-calculated cost metrics

        Returns:
            BusinessImpactReport object
        """
        # Determine active business hours (e.g., 9 AM to 5 PM Monday-Friday)
        now = datetime.utcnow()
        # Default mock business hours check: weekday between 9 AM and 5 PM
        is_bh = now.weekday() < 5 and (9 <= now.hour <= 17)

        # Baseline impact scores
        rev_impact = 1.0
        cust_impact = 1.0
        comp_impact = 0.0
        sla_impact = 1.0
        eng_impact = 2.0

        # Adjust based on Application Tier / Criticality
        if application:
            tier_val = application.tier.value if hasattr(application.tier, "value") else str(application.tier)
            if tier_val == "tier_1":
                rev_impact = 9.0
                cust_impact = 9.0
                sla_impact = 8.5
                eng_impact = 8.0
            elif tier_val == "tier_2":
                rev_impact = 6.0
                cust_impact = 5.0
                sla_impact = 6.0
                eng_impact = 5.0
            elif tier_val == "tier_3":
                rev_impact = 3.0
                cust_impact = 2.0
                sla_impact = 3.0
                eng_impact = 3.0

            # Compliance frameworks increase compliance score
            if application.criticality:
                if application.criticality.compliance_frameworks:
                    comp_impact = min(len(application.criticality.compliance_frameworks) * 3.0, 10.0)

        # Cost vs Risk Correlation Adjustment
        # Terminating high-cost active instances adds to revenue impact and restoration engineering cost
        monthly_cost = cost_correlation_data.get("monthly_cost", 0.0)
        is_idle = cost_correlation_data.get("is_idle", False)

        if monthly_cost > 2000.0 and not is_idle:
            rev_impact = max(rev_impact, 8.0)
            eng_impact = max(eng_impact, 7.0)

        if is_idle and action in ("STOP", "TERMINATE"):
            # Lower risk for stopping idle resources
            rev_impact = max(rev_impact - 4.0, 1.0)
            cust_impact = max(cust_impact - 4.0, 1.0)
            sla_impact = max(sla_impact - 4.0, 1.0)

        return BusinessImpactReport(
            revenue_impact_score=round(rev_impact, 1),
            customer_impact_score=round(cust_impact, 1),
            compliance_impact_score=round(comp_impact, 1),
            sla_impact_score=round(sla_impact, 1),
            engineering_impact_score=round(eng_impact, 1),
            is_business_hours=is_bh
        )

    def correlate_cost_and_risk(
        self,
        resource: Optional[CloudResource],
        application: Optional[Application],
        action: str
    ) -> dict[str, Any]:
        """Correlate resource cost with risk.

        Identify scenarios like stopping idle GPU vs stopping payment service database.

        Args:
            resource: Resource
            application: Application
            action: Action

        Returns:
            Cost vs Risk metrics
        """
        monthly_cost = 0.0
        is_idle = False
        description = "Normal resource cost profile."

        if resource:
            monthly_cost = resource.cost_monthly or 0.0
            # Identify idle resources by tag, CPU utilization, or name conventions
            if (
                "idle" in resource.tags.get("status", "").lower() or
                "idle" in resource.name.lower() or
                resource.metadata.get("cpu_utilization", 10.0) < 5.0
            ):
                is_idle = True

        if is_idle:
            description = f"Resource is idle. Stopping/Terminating saves ${monthly_cost:.2f}/mo with low risk."
        elif monthly_cost > 1000.0:
            description = f"High cost resource (${monthly_cost:.2f}/mo). Disruptions carry high financial and operational exposure."

        return {
            "monthly_cost": monthly_cost,
            "is_idle": is_idle,
            "correlation_summary": description
        }

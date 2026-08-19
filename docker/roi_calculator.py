"""
ROI Calculator Component

Computes ROI metrics: payback period, engineering hours, implementation costs, and investment scores.
"""

from __future__ import annotations

import logging
from models_strategy import ROIMetrics

logger = logging.getLogger(__name__)


class ROICalculator:
    """Calculates payback period and ROI score metrics for optimization proposals."""

    def __init__(self) -> None:
        """Initialize ROI Calculator."""
        pass

    def calculate_roi(
        self,
        savings_monthly: float,
        complexity: str,
        hourly_rate: float = 80.0
    ) -> ROIMetrics:
        """Calculate ROI details based on predicted savings and complexity level.

        Args:
            savings_monthly: Expected monthly savings in USD
            complexity: Complexity label (LOW, MEDIUM, HIGH)
            hourly_rate: Hourly cost of engineering hours

        Returns:
            ROIMetrics object
        """
        # Determine engineering hours based on complexity
        if complexity == "LOW":
            hours = 4.0
        elif complexity == "MEDIUM":
            hours = 12.0
        else:
            hours = 40.0

        implementation_cost = hours * hourly_rate
        
        # Payback period = Implementation Cost / (Expected Savings Monthly / 30)
        daily_savings = (savings_monthly / 30.0) if savings_monthly > 0.0 else 0.1
        payback = implementation_cost / daily_savings

        # ROI Score = (Expected Savings Monthly * 12) / (Implementation Cost + 1.0)
        roi_val = (savings_monthly * 12.0) / (implementation_cost + 1.0)

        return ROIMetrics(
            expected_savings_monthly=round(savings_monthly, 2),
            implementation_cost=round(implementation_cost, 2),
            engineering_hours=hours,
            payback_period_days=round(payback, 1),
            roi_score=round(roi_val, 2)
        )

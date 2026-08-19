"""
What-If Engine Component

Simulates scenario modifications and returns updated plans with revised cost estimates and risk metrics.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import copy

from models_strategy import OptimizationPlan, ScenarioParameter

logger = logging.getLogger(__name__)


class WhatIfEngine:
    """Evaluates business scenarios and adjusts savings forecasts/risks based on multipliers."""

    def __init__(self) -> None:
        """Initialize What-If Engine."""
        pass

    def simulate_scenario(
        self,
        base_plans: list[OptimizationPlan],
        parameter: ScenarioParameter
    ) -> list[OptimizationPlan]:
        """Modify base optimization plans based on scenario criteria parameters.

        Args:
            base_plans: Base generated optimization plans
            parameter: What-if criteria parameters

        Returns:
            Adjusted list of OptimizationPlan objects
        """
        adjusted_plans = []

        for plan in base_plans:
            adjusted = copy.deepcopy(plan)

            # Scenario A: GPU demand doubles
            # Doubles implementation costs & risk on compute plans due to scaling constraints
            if parameter.gpu_demand_multiplier > 1.0:
                is_compute = plan.recommended_strategy.description.lower()
                if "compute" in is_compute or "instance" in is_compute:
                    adjusted.roi_analysis.expected_savings_monthly *= 1.5
                    adjusted.roi_analysis.implementation_cost *= parameter.gpu_demand_multiplier
                    adjusted.expected_savings_monthly *= 1.5
                    # Increase risk score in report
                    score = adjusted.risk_assessment.get("risk_score", 50.0)
                    adjusted.risk_assessment["risk_score"] = min(score + 20.0, 100.0)

            # Scenario B: Traffic drops 40%
            # Boosts potential right-sizing savings because workloads are underutilized
            if parameter.traffic_drop_percentage > 0.0:
                mult = 1.0 + (parameter.traffic_drop_percentage / 100.0)
                adjusted.roi_analysis.expected_savings_monthly *= mult
                adjusted.expected_savings_monthly *= mult
                # Lower operational risk since lower traffic load means safety buffers are wider
                score = adjusted.risk_assessment.get("risk_score", 50.0)
                adjusted.risk_assessment["risk_score"] = max(score - 10.0, 10.0)

            # Scenario C: New region added
            if parameter.add_new_region:
                adjusted.current_state += f" (Scenario: Expanding to region {parameter.add_new_region})"

            # Scenario D: Reserved Instances Purchased
            # Reduces monthly savings since RIs already applied billing optimizations,
            # but lowers payback period risk
            if parameter.purchase_reserved_instances:
                adjusted.roi_analysis.expected_savings_monthly *= 0.7
                adjusted.expected_savings_monthly *= 0.7
                adjusted.roi_analysis.payback_period_days *= 0.5

            adjusted_plans.append(adjusted)

        logger.info("What-if simulation complete: processed %d plans", len(adjusted_plans))
        return adjusted_plans

"""
Cost Predictor Component

Estimates monthly financial shifts, migration costs, and future billing forecasts.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from models_simulation import CostForecast

logger = logging.getLogger(__name__)


class CostPredictor:
    """Predicts billing adjustments and transition expenses for simulated operations."""

    def __init__(self) -> None:
        """Initialize Cost Predictor."""
        pass

    def predict_cost(
        self,
        target_id: str,
        action: str,
        parameters: dict[str, Any],
        twin_context: Any
    ) -> CostForecast:
        """Calculate cost projection details.

        Args:
            target_id: Resource/Application ID
            action: Action simulated
            parameters: Action parameters
            twin_context: Mapped twin state details

        Returns:
            CostForecast object
        """
        # Read baseline monthly bill
        current_bill = twin_context.cost_model.get("total_monthly_bill_estimate", 10000.0)
        if current_bill == 0.0:
            current_bill = 12000.0

        monthly_cost = 100.0

        # Find target in twin resource states
        res_data = next((r for r in twin_context.resources if r["id"] == target_id), None)
        if res_data:
            monthly_cost = res_data.get("cost_monthly", 100.0)

        # Baseline savings models
        immediate_savings = 0.0
        monthly_savings = 0.0
        migration_cost = 50.0  # basic engineering overhead cost

        if action in ("TERMINATE", "STOP"):
            monthly_savings = monthly_cost
            future_bill = max(current_bill - monthly_savings, 0.0)
            
        elif action == "RESIZE":
            monthly_savings = monthly_cost * 0.4
            migration_cost = 100.0
            future_bill = max(current_bill - monthly_savings, 0.0)

        elif action == "RESTART":
            # Restarts save no money, but carry a minor execution cost
            migration_cost = 20.0
            future_bill = current_bill

        else:
            future_bill = current_bill

        return CostForecast(
            immediate_savings_usd=round(immediate_savings, 2),
            monthly_savings_usd=round(monthly_savings, 2),
            migration_cost_usd=round(migration_cost, 2),
            future_bill_monthly_usd=round(future_bill, 2)
        )

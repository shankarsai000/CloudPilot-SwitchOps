"""
Savings Attribution Engine.

Distinguishes 3 distinct tiers of economic impact:
1. Predicted Savings (ex-ante estimate)
2. Verified Savings (ex-post empirically verified billable delta)
3. Annualized Savings (risk-calibrated 12-month run rate)

Calculates realization rates and aggregate portfolio attribution summaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

from verification.models import SavingsAttribution


class PortfolioSavingsSummary(BaseModel):
    """Aggregate portfolio-wide savings attribution across all executed actions."""
    total_actions_evaluated: int = 0
    total_predicted_monthly_usd: float = 0.0
    total_verified_monthly_usd: float = 0.0
    total_annualized_usd: float = 0.0
    average_realization_percentage: float = 0.0
    highest_realized_action_id: Optional[str] = None
    lowest_realized_action_id: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SavingsAttributionEngine:
    """
    Computes, registers, and analyzes 3-way savings attribution.
    """

    def __init__(self) -> None:
        self._attributions: Dict[str, SavingsAttribution] = {}
        self._mutex = threading.Lock()

    def attribute_savings(
        self,
        action_id: str,
        target_resource_id: str,
        predicted_monthly_savings_usd: float,
        verified_monthly_savings_usd: float,
        target_service: str = "unknown",
        confidence_calibration_factor: float = 0.95,
        variance_discount_pct: float = 0.05,
    ) -> SavingsAttribution:
        """
        Compute 3-way savings attribution:
        - Predicted: Ex-ante model estimate
        - Verified: Ex-post measured reduction
        - Annualized: Verified * 12 * confidence_factor * (1 - variance_discount)
        """
        pred = max(0.0, float(predicted_monthly_savings_usd))
        veri = max(0.0, float(verified_monthly_savings_usd))

        realization_pct = (veri / pred * 100.0) if pred > 0 else (100.0 if veri == 0 else 0.0)

        # Risk-discounted annualized run rate
        # Annualized = verified * 12 * confidence_factor * (1 - variance_discount)
        raw_annual = veri * 12.0
        calibrated_annual = raw_annual * confidence_calibration_factor * (1.0 - variance_discount_pct)
        annualized = max(0.0, round(calibrated_annual, 2))

        attr = SavingsAttribution(
            attribution_id=f"att-{uuid.uuid4().hex[:8]}",
            action_id=action_id,
            target_resource_id=target_resource_id,
            target_service=target_service,
            predicted_monthly_savings_usd=round(pred, 2),
            verified_monthly_savings_usd=round(veri, 2),
            annualized_savings_usd=annualized,
            realization_percentage=round(realization_pct, 2),
            confidence_calibration_factor=confidence_calibration_factor,
            variance_discount_pct=variance_discount_pct,
            attributed_at=datetime.now(timezone.utc),
        )

        with self._mutex:
            self._attributions[action_id] = attr
        return attr

    def get_attribution(self, action_id: str) -> Optional[SavingsAttribution]:
        with self._mutex:
            return self._attributions.get(action_id)

    def list_attributions(self) -> List[SavingsAttribution]:
        with self._mutex:
            return sorted(self._attributions.values(), key=lambda a: a.attributed_at, reverse=True)

    def get_portfolio_summary(self) -> PortfolioSavingsSummary:
        """
        Aggregate portfolio-wide savings metrics.
        """
        with self._mutex:
            attrs = list(self._attributions.values())

        if not attrs:
            return PortfolioSavingsSummary()

        total_pred = sum(a.predicted_monthly_savings_usd for a in attrs)
        total_veri = sum(a.verified_monthly_savings_usd for a in attrs)
        total_ann = sum(a.annualized_savings_usd for a in attrs)

        avg_realization = sum(a.realization_percentage for a in attrs) / len(attrs)

        highest = max(attrs, key=lambda a: a.realization_percentage)
        lowest = min(attrs, key=lambda a: a.realization_percentage)

        return PortfolioSavingsSummary(
            total_actions_evaluated=len(attrs),
            total_predicted_monthly_usd=round(total_pred, 2),
            total_verified_monthly_usd=round(total_veri, 2),
            total_annualized_usd=round(total_ann, 2),
            average_realization_percentage=round(avg_realization, 2),
            highest_realized_action_id=highest.action_id,
            lowest_realized_action_id=lowest.action_id,
            generated_at=datetime.now(timezone.utc),
        )

    def clear_all(self) -> None:
        with self._mutex:
            self._attributions.clear()


_attribution_engine_instance: Optional[SavingsAttributionEngine] = None


def get_savings_attribution_engine() -> SavingsAttributionEngine:
    global _attribution_engine_instance
    if _attribution_engine_instance is None:
        _attribution_engine_instance = SavingsAttributionEngine()
    return _attribution_engine_instance

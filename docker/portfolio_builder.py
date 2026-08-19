"""
Portfolio Builder Component

Organizes optimization plans into a strategic portfolio:
- Immediate wins, medium-term wins, long-term architecture, tech debt, and operational improvements.
"""

from __future__ import annotations

import logging
from models_strategy import OptimizationPlan, StrategyPortfolio

logger = logging.getLogger(__name__)


class PortfolioBuilder:
    """Builds a balanced recommendation portfolio from generated plans."""

    def __init__(self) -> None:
        """Initialize Portfolio Builder."""
        pass

    def build_portfolio(self, plans: list[OptimizationPlan]) -> StrategyPortfolio:
        """Categorize plans into portfolio buckets.

        Args:
            plans: Calculated Optimization Plans

        Returns:
            StrategyPortfolio object
        """
        immediate = []
        medium = []
        long_term = []
        tech_debt = []
        ops = []

        for plan in plans:
            risk = plan.recommended_strategy.risk_level
            complexity = plan.roi_analysis.engineering_hours # (maps to complexity)

            # Categorize based on rules
            if "zombie" in plan.problem_statement.lower() or "orphan" in plan.problem_statement.lower():
                tech_debt.append(plan)
            elif "autoscaling" in plan.problem_statement.lower():
                ops.append(plan)
            elif risk in ("SAFE", "LOW") and complexity <= 8.0:
                immediate.append(plan)
            elif risk == "MEDIUM":
                medium.append(plan)
            else:
                long_term.append(plan)

        # Fallbacks: if portfolio buckets are empty, put plans into immediate for baseline APIs
        if not immediate and not medium and not long_term and not tech_debt and not ops and plans:
            immediate = plans

        logger.info(
            "Portfolio built: %d immediate, %d medium, %d long-term, %d debt, %d ops",
            len(immediate), len(medium), len(long_term), len(tech_debt), len(ops)
        )

        return StrategyPortfolio(
            immediate_wins=immediate,
            medium_term_wins=medium,
            long_term_architecture=long_term,
            technical_debt=tech_debt,
            operational_improvements=ops
        )

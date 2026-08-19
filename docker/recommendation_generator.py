"""
Recommendation Generator Component

Generates candidate optimization strategies (at least 2 options), performs trade-off analysis,
and constructs explainability contexts.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from models_strategy import CandidateStrategy, Recommendation, OptimizationCategory, ApprovalLevel
from opportunity_detector import OptimizationOpportunity
from roi_calculator import ROICalculator
from priority_engine import PriorityEngine

logger = logging.getLogger(__name__)


class RecommendationGenerator:
    """Generates comparative candidate options and trade-off analyzes for optimization opportunities."""

    def __init__(
        self,
        roi_calculator: Optional[ROICalculator] = None,
        priority_engine: Optional[PriorityEngine] = None,
    ) -> None:
        """Initialize Recommendation Generator."""
        self.roi_calculator = roi_calculator or ROICalculator()
        self.priority_engine = priority_engine or PriorityEngine()

    def generate_recommendation(
        self,
        opportunity: OptimizationOpportunity,
        target_resource: Optional[Any],
        target_app: Optional[Any],
        risk_level: str = "LOW",
        confidence_score: float = 95.0
    ) -> Recommendation:
        """Formulate candidate options and select the recommended path.

        Args:
            opportunity: Opportunity info
            target_resource: Target resource context
            target_app: Application context
            risk_level: Inferred Risk level
            confidence_score: Inferred confidence rating

        Returns:
            Recommendation model
        """
        candidates: list[CandidateStrategy] = []
        monthly_cost = opportunity.metrics.get("monthly_cost", 100.0)

        # Generate candidates based on optimization type
        if opportunity.type == "COMPUTE":
            # Strategy A: Resize instances (Conservative)
            candidates.append(
                CandidateStrategy(
                    strategy_id=f"strat-{uuid.uuid4().hex[:8]}",
                    name="Resize Instances",
                    expected_savings_monthly=monthly_cost * 0.3,
                    risk_level="LOW",
                    confidence_score=95.0,
                    description=f"Downgrade size to match actual CPU utilization boundaries. Saves ${monthly_cost * 0.3:.2f}/mo."
                )
            )
            # Strategy B: Enable Spot Instances (Aggressive)
            candidates.append(
                CandidateStrategy(
                    strategy_id=f"strat-{uuid.uuid4().hex[:8]}",
                    name="Enable Spot Instances",
                    expected_savings_monthly=monthly_cost * 0.6,
                    risk_level="MEDIUM",
                    confidence_score=85.0,
                    description=f"Leverage Spot compute nodes for non-critical scaling tasks. Saves ${monthly_cost * 0.6:.2f}/mo."
                )
            )

        elif opportunity.type == "DATABASES":
            # Strategy A: Storage Auto-Scaling
            candidates.append(
                CandidateStrategy(
                    strategy_id=f"strat-{uuid.uuid4().hex[:8]}",
                    name="Enable Storage Auto-Scaling",
                    expected_savings_monthly=monthly_cost * 0.15,
                    risk_level="SAFE",
                    confidence_score=98.0,
                    description="Enable dynamic storage scaling. Saves storage allocation cost overhead."
                )
            )
            # Strategy B: Downgrade Instance Size
            candidates.append(
                CandidateStrategy(
                    strategy_id=f"strat-{uuid.uuid4().hex[:8]}",
                    name="Resize Database Instance",
                    expected_savings_monthly=monthly_cost * 0.4,
                    risk_level="HIGH" if target_app and target_app.tier.value == "tier_1" else "MEDIUM",
                    confidence_score=88.0,
                    description="Modify db size parameters. Downward scaling saves significant active node cost."
                )
            )

        elif opportunity.type == "STORAGE":
            # Strategy A: Lifecycle Policy (Safe)
            candidates.append(
                CandidateStrategy(
                    strategy_id=f"strat-{uuid.uuid4().hex[:8]}",
                    name="Apply Lifecycle Rules",
                    expected_savings_monthly=monthly_cost * 0.25,
                    risk_level="SAFE",
                    confidence_score=99.0,
                    description="Transition low-activity files automatically to colder storage tier categories."
                )
            )
            # Strategy B: Delete Unused Storage
            candidates.append(
                CandidateStrategy(
                    strategy_id=f"strat-{uuid.uuid4().hex[:8]}",
                    name="Decommission Unused Buckets",
                    expected_savings_monthly=monthly_cost * 0.8,
                    risk_level="MEDIUM",
                    confidence_score=92.0,
                    description="Delete orphaned storage volumes and detached disks."
                )
            )

        else:  # Defaults / Architecture / Autoscale
            # Strategy A: Basic Optimization
            candidates.append(
                CandidateStrategy(
                    strategy_id=f"strat-{uuid.uuid4().hex[:8]}",
                    name="Resource Right-Sizing",
                    expected_savings_monthly=monthly_cost * 0.2,
                    risk_level="LOW",
                    confidence_score=94.0,
                    description="Perform right-sizing modifications to balance efficiency."
                )
            )
            # Strategy B: Decommission Zombie Resource
            candidates.append(
                CandidateStrategy(
                    strategy_id=f"strat-{uuid.uuid4().hex[:8]}",
                    name="Decommission Zombie Resource",
                    expected_savings_monthly=monthly_cost * 1.0,
                    risk_level="MEDIUM",
                    confidence_score=90.0,
                    description="Decommission zombie instance since it belongs to no active application environment."
                )
            )

        # Select recommended candidate (typically the highest savings with reasonable risk)
        recommended = candidates[0]
        for c in candidates:
            if c.expected_savings_monthly > recommended.expected_savings_monthly and c.risk_level in ("SAFE", "LOW", "MEDIUM"):
                recommended = c

        # Assess ROI metrics for chosen strategy
        complexity = "LOW" if recommended.risk_level in ("SAFE", "LOW") else "MEDIUM"
        roi = self.roi_calculator.calculate_roi(recommended.expected_savings_monthly, complexity)

        # Compute prioritization score
        biz_crit = target_app.criticality.criticality_score if target_app and target_app.criticality else 50.0
        priority = self.priority_engine.calculate_priority(
            roi.roi_score, recommended.risk_level, recommended.confidence_score, complexity, biz_crit
        )

        # Infer approval level
        approval = ApprovalLevel.APPROVAL_REQUIRED
        if recommended.risk_level == "SAFE":
            approval = ApprovalLevel.AUTO_EXECUTE
        elif recommended.risk_level in ("HIGH", "CRITICAL"):
            approval = ApprovalLevel.EXECUTIVE_APPROVAL

        # Set category
        try:
            category = OptimizationCategory(opportunity.type)
        except ValueError:
            category = OptimizationCategory.COMPUTE

        # Build explains rationale
        explanations = [
            f"Recommended strategy '{recommended.name}' selected because it balances monthly savings with risk tolerances.",
            f"Alternative option '{[c.name for c in candidates if c.strategy_id != recommended.strategy_id][0]}' has different trade-offs."
        ]

        return Recommendation(
            recommendation_id=f"rec-{uuid.uuid4().hex[:12]}",
            target_id=opportunity.target_id,
            description=opportunity.description,
            category=category,
            recommended_strategy_name=recommended.name,
            candidates=candidates,
            roi=roi,
            risk_category=recommended.risk_level,
            confidence_score=recommended.confidence_score,
            complexity=complexity,
            priority_score=round(priority, 1),
            approval_level=approval,
            explanation=explanations
        )

"""
Strategy Engine Component

Orchestrates all M5 engines and builders to generate complete, structured Optimization Plans.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from models_resource import CloudResource
from models_application import Application
from models_strategy import OptimizationPlan
from opportunity_detector import OpportunityDetector, OptimizationOpportunity
from recommendation_generator import RecommendationGenerator
from dependency_planner import DependencyPlanner
from approval_engine import ApprovalEngine
from portfolio_builder import PortfolioBuilder
from roadmap_builder import RoadmapBuilder

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Core synthesis engine orchestrating opportunity detection, ROI/risk assessment, and blueprint mapping."""

    def __init__(
        self,
        opportunity_detector: Optional[OpportunityDetector] = None,
        recommendation_generator: Optional[RecommendationGenerator] = None,
        dependency_planner: Optional[DependencyPlanner] = None,
        approval_engine: Optional[ApprovalEngine] = None,
        portfolio_builder: Optional[PortfolioBuilder] = None,
        roadmap_builder: Optional[RoadmapBuilder] = None,
    ) -> None:
        """Initialize Strategy Engine."""
        self.detector = opportunity_detector or OpportunityDetector()
        self.generator = recommendation_generator or RecommendationGenerator()
        self.planner = dependency_planner or DependencyPlanner()
        self.approval_engine = approval_engine or ApprovalEngine()
        self.portfolio_builder = portfolio_builder or PortfolioBuilder()
        self.roadmap_builder = roadmap_builder or RoadmapBuilder()

        logger.info("StrategyEngine initialized")

    def generate_plans(
        self,
        resources: list[CloudResource],
        applications: list[Application],
        risk_agent: Optional[Any] = None,
    ) -> list[OptimizationPlan]:
        """Formulate Optimization Plans for all detected opportunities.

        Args:
            resources: Discovered resources
            applications: Discovered applications
            risk_agent: M4 RiskIntelligenceAgent reference for risk assessments

        Returns:
            List of generated OptimizationPlan objects
        """
        opportunities = self.detector.detect_opportunities(resources, applications)
        plans = []

        resource_map = {r.id: r for r in resources}

        for opp in opportunities:
            # Match context
            target_res = resource_map.get(opp.target_id)
            target_app = None
            for app in applications:
                if opp.target_id in app.resource_ids:
                    target_app = app
                    break

            # Evaluate risk metrics using M4 if available
            risk_category = "LOW"
            confidence = 95.0
            risk_metadata = {"risk_score": 25.0}

            if risk_agent:
                try:
                    # Run simulated assessment
                    from models_risk import ActionType
                    assessment = risk_agent.assess_resource_risk(opp.target_id, ActionType.TERMINATE)
                    if assessment:
                        risk_category = assessment.risk_category.value
                        confidence = assessment.confidence_score
                        risk_metadata = assessment.dict()
                except Exception as e:
                    logger.warning("M4 risk check failed for %s: %s", opp.target_id, e)

            # Generate comparative recommendations
            rec = self.generator.generate_recommendation(
                opp, target_res, target_app, risk_category, confidence
            )

            # Build execution sequence
            blueprint = self.planner.build_execution_sequence(
                opp.target_id, rec.category.value, rec.recommended_strategy_name
            )

            # Calculate approval workflow
            approval = self.approval_engine.determine_approval_workflow(
                target_res, target_app, "TERMINATE", risk_category
            )

            # Retrieve chosen recommended strategy details
            chosen_candidate = next(
                (c for c in rec.candidates if c.name == rec.recommended_strategy_name),
                rec.candidates[0]
            )

            # Define trade-off details
            alternatives = [c for c in rec.candidates if c.strategy_id != chosen_candidate.strategy_id]
            trade_off = (
                f"We recommend '{chosen_candidate.name}' (savings: ${chosen_candidate.expected_savings_monthly:.2f}/mo, "
                f"risk: {chosen_candidate.risk_level}) over alternative '{alternatives[0].name}' (savings: "
                f"${alternatives[0].expected_savings_monthly:.2f}/mo, risk: {alternatives[0].risk_level}) due to lower risk exposure."
            )

            # Formulate structured plan
            plan = OptimizationPlan(
                plan_id=f"plan-{uuid.uuid4().hex[:12]}",
                executive_summary=(
                    f"Perform {chosen_candidate.name} on target '{opp.name}' to optimize cost efficiency. "
                    f"This strategy delivers a payback period of {rec.roi.payback_period_days} days."
                ),
                current_state=f"Resource '{opp.name}' is currently running with low usage metrics.",
                problem_statement=opp.description,
                candidate_strategies=rec.candidates,
                trade_off_analysis=trade_off,
                recommended_strategy=chosen_candidate,
                expected_savings_monthly=chosen_candidate.expected_savings_monthly,
                risk_assessment={
                    "risk_score": risk_metadata.get("risk_score", 20.0),
                    "risk_category": risk_category,
                    "confidence_score": confidence,
                    "policy_violations": risk_metadata.get("policy_violations", [])
                },
                roi_analysis=rec.roi,
                execution_blueprint=blueprint,
                success_metrics=[
                    "Validate cpu utilization has stabilized below performance thresholds.",
                    "Verify active connections remain intact after scaling transition.",
                    f"Verify monthly billing checks show cost drop of ~${chosen_candidate.expected_savings_monthly:.2f}/mo."
                ]
            )
            plans.append(plan)

        logger.info("Generated %d optimization plans", len(plans))
        return plans

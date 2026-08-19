"""
Strategy Agent — Main Orchestrator

Consumes discoveries and risk metrics from M1-M4 to build complete, prioritized Optimization Plans.
Supports roadmap builds, portfolio queries, and scenario what-if simulations.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from models_resource import ResourceGraph
from models_application import ApplicationGraph
from models_strategy import OptimizationPlan, StrategyPortfolio, RoadmapPhase, ScenarioParameter
from strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)


class StrategyAgent:
    """Orchestrates Strategic Optimization runs and simulates planning portfolios."""

    def __init__(
        self,
        strategy_engine: Optional[StrategyEngine] = None,
        m1_repo: Optional[Any] = None,
        m2_repo: Optional[Any] = None,
        m3_repo: Optional[Any] = None,
        risk_agent: Optional[Any] = None,
    ) -> None:
        """Initialize the Strategy Agent.

        Args:
            strategy_engine: Strategy Engine instance
            m1_repo: M1 resource repository
            m2_repo: M2 cost repository
            m3_repo: M3 application repository
            risk_agent: M4 RiskIntelligenceAgent
        """
        self.strategy_engine = strategy_engine or StrategyEngine()
        self.m1_repo = m1_repo
        self.m2_repo = m2_repo
        self.m3_repo = m3_repo
        self.risk_agent = risk_agent

        # State cache fallback
        self._resources: list[Any] = []
        self._applications: list[Any] = []
        self._generated_plans: list[OptimizationPlan] = []
        logger.info("StrategyAgent initialized successfully")

    def load_context(
        self,
        resource_graph: ResourceGraph,
        app_graph: ApplicationGraph
    ) -> None:
        """Load operational environment context cache.

        Args:
            resource_graph: Discovered M1 resources
            app_graph: Discovered M3 applications
        """
        self._resources = resource_graph.resources
        self._applications = app_graph.applications
        logger.info(
            "Loaded context: %d resources, %d applications",
            len(self._resources),
            len(self._applications)
        )

    def generate_strategies(self) -> list[OptimizationPlan]:
        """Trigger the strategy generation pipeline.

        Returns:
            List of generated OptimizationPlan objects
        """
        resources = self._get_resources()
        applications = self._get_applications()

        plans = self.strategy_engine.generate_plans(resources, applications, self.risk_agent)
        self._generated_plans = plans
        return plans

    def get_plans(self) -> list[OptimizationPlan]:
        """Get the current generated optimization plans.

        Returns:
            List of generated plans
        """
        if not self._generated_plans:
            self.generate_strategies()
        return self._generated_plans

    def get_plan(self, plan_id: str) -> Optional[OptimizationPlan]:
        """Retrieve single plan by ID.

        Args:
            plan_id: Plan identifier

        Returns:
            OptimizationPlan or None
        """
        plans = self.get_plans()
        return next((p for p in plans if p.plan_id == plan_id), None)

    def get_portfolio(self) -> StrategyPortfolio:
        """Group active plans into portfolio buckets.

        Returns:
            StrategyPortfolio details
        """
        plans = self.get_plans()
        return self.strategy_engine.portfolio_builder.build_portfolio(plans)

    def get_roadmap(self) -> list[RoadmapPhase]:
        """Build chronological roadmap phases.

        Returns:
            List of RoadmapPhase
        """
        plans = self.get_plans()
        return self.strategy_engine.roadmap_builder.build_roadmap(plans)

    def run_whatif_scenario(self, parameter: ScenarioParameter) -> list[OptimizationPlan]:
        """Run what-if scenario planning over the current plans.

        Args:
            parameter: What-if parameters

        Returns:
            Adjusted list of OptimizationPlan objects
        """
        from whatif_engine import WhatIfEngine
        plans = self.get_plans()
        whatif_runner = WhatIfEngine()
        return whatif_runner.simulate_scenario(plans, parameter)

    def _get_resources(self) -> list[Any]:
        """Fetch resources from repository or cache fallback."""
        if self.m1_repo:
            try:
                return self.m1_repo.get_all_resources()
            except Exception:
                pass
        return self._resources

    def _get_applications(self) -> list[Application]:
        """Fetch applications from repository or cache fallback."""
        if self.m3_repo:
            try:
                return self.m3_repo.get_all_applications()
            except Exception:
                pass
        return self._applications

"""
Strategy API Routes

FastAPI router exposing endpoints for strategic optimization plans, portfolio views, roadmaps, and ROI priorities.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models_strategy import OptimizationPlan, StrategyPortfolio, RoadmapPhase, ScenarioParameter, ROIMetrics
from strategy_agent import StrategyAgent

logger = logging.getLogger(__name__)


# --- Helper Response Models ---

class PriorityMatrixItem(BaseModel):
    """Item in priority ranked matrix output."""

    plan_id: str
    name: str
    priority_score: float
    risk_level: str
    expected_savings: float


class StrategySummaryResponse(BaseModel):
    """General summary details of optimization proposals."""

    total_plans: int
    total_expected_savings: float
    active_roadmaps_count: int


def create_strategy_router(
    agent: Any = None,
    repository: Any = None,
) -> APIRouter:
    """Create FastAPI router for Strategic Decision Intelligence Agent.

    Args:
        agent: StrategyAgent instance
        repository: StrategyRepository instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/strategies", tags=["strategies"])

    @router.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Health status
        """
        return {"status": "healthy", "service": "strategy-agent"}

    @router.get("", response_model=list[OptimizationPlan])
    async def get_strategies() -> list[OptimizationPlan]:
        """List all generated optimization strategies.

        Returns:
            List of OptimizationPlan objects
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        return agent.get_plans()

    @router.get("/portfolio", response_model=StrategyPortfolio)
    async def get_portfolio() -> StrategyPortfolio:
        """Get portfolio-structured view.

        Returns:
            StrategyPortfolio categorized details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        return agent.get_portfolio()

    @router.get("/roadmap", response_model=list[RoadmapPhase])
    async def get_roadmap() -> list[RoadmapPhase]:
        """Get phased optimization roadmap.

        Returns:
            List of chronological RoadmapPhase steps
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        return agent.get_roadmap()

    @router.get("/priorities", response_model=list[PriorityMatrixItem])
    async def get_priorities() -> list[PriorityMatrixItem]:
        """Get priority ranked matrix.

        Returns:
            List of priority items sorted by rank score
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        plans = agent.get_plans()
        items = []
        for plan in plans:
            # Recompute priority on-the-fly or extract from blueprint attributes
            # Priority scores mapped from risk and ROI
            roi_term = min(plan.roi_analysis.roi_score * 5.0, 100.0)
            risk_term = 80.0 if plan.recommended_strategy.risk_level == "LOW" else 50.0
            p_score = (roi_term * 0.35) + (risk_term * 0.35) + 30.0

            items.append(
                PriorityMatrixItem(
                    plan_id=plan.plan_id,
                    name=plan.recommended_strategy.name,
                    priority_score=round(p_score, 1),
                    risk_level=plan.recommended_strategy.risk_level,
                    expected_savings=plan.expected_savings_monthly
                )
            )

        return sorted(items, key=lambda i: i.priority_score, reverse=True)

    @router.get("/roi", response_model=list[ROIMetrics])
    async def get_roi_reports() -> list[ROIMetrics]:
        """Get ROI analysis reports.

        Returns:
            List of ROIMetrics summaries
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        plans = agent.get_plans()
        return [p.roi_analysis for p in plans]

    @router.get("/{id}", response_model=OptimizationPlan)
    async def get_strategy(id: str) -> OptimizationPlan:
        """Get details of a specific strategy plan.

        Args:
            id: Plan ID

        Returns:
            OptimizationPlan details
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        plan = agent.get_plan(id)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {id} not found")

        return plan

    @router.post("/generate", response_model=list[OptimizationPlan])
    async def generate_strategies() -> list[OptimizationPlan]:
        """Trigger new optimization strategies generation.

        Returns:
            Newly generated OptimizationPlan list
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            plans = agent.generate_strategies()
            if repository:
                for plan in plans:
                    try:
                        repository.save_plan(plan)
                    except Exception as e:
                        logger.error("Failed to persist strategy plan %s: %s", plan.plan_id, e)
            return plans
        except Exception as e:
            logger.error("Failed to execute strategy generation pipeline: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/whatif", response_model=list[OptimizationPlan])
    async def run_whatif(parameter: ScenarioParameter) -> list[OptimizationPlan]:
        """Run what-if scenario simulations.

        Args:
            parameter: Scenario parameter criteria

        Returns:
            Simulated OptimizationPlan list
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")

        try:
            return agent.run_whatif_scenario(parameter)
        except Exception as e:
            logger.error("Failed to simulate what-if scenario: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    return router

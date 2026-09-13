"""
Stage 5: M5 Strategy Agent Stage.
Generates prioritized optimization plans, ROI models, roadmaps, and portfolios.
"""

from __future__ import annotations

from typing import List

from models_strategy import OptimizationPlan
from pipeline.models import StageResult, StageStatus, StrategyStageOutput, UnifiedExecutionContext
from pipeline.stages.base import BasePipelineStage
from strategy_agent import StrategyAgent


class M5StrategyStage(BasePipelineStage):
    """
    Stage 5: Synthesizes M1-M4 insights into actionable, prioritized Optimization Plans.
    """
    stage_id = "m5_strategy"
    stage_name = "M5 Strategy Agent"
    is_critical = True

    def __init__(self, agent: StrategyAgent = None) -> None:
        super().__init__(is_critical=True, max_retries=1)
        self.agent = agent or StrategyAgent()

    def _run(self, context: UnifiedExecutionContext) -> StageResult:
        res_graph = context.infrastructure_state
        app_graph = context.applications

        if not res_graph or not app_graph:
            raise ValueError("M5 requires M1 infrastructure_state and M3 applications in context")

        # Load context
        self.agent.load_context(res_graph, app_graph)

        # Generate plans
        plans: List[OptimizationPlan] = self.agent.generate_strategies()
        portfolio = self.agent.get_portfolio()
        roadmap = self.agent.get_roadmap()

        total_savings = sum(p.expected_savings_monthly for p in plans)

        strategy_output = StrategyStageOutput(
            plans=plans,
            portfolio=portfolio,
            roadmap=roadmap,
            total_potential_savings_monthly_usd=round(total_savings, 2),
        )
        context.strategies = strategy_output

        evidence = {
            "total_plans_generated": len(plans),
            "total_potential_savings_monthly_usd": round(total_savings, 2),
            "immediate_wins_count": len(portfolio.immediate_wins) if portfolio else 0,
            "roadmap_phases_count": len(roadmap),
            "plans_summary": [
                {
                    "plan_id": p.plan_id,
                    "strategy": p.recommended_strategy.name,
                    "savings_usd": p.expected_savings_monthly,
                    "risk_level": p.recommended_strategy.risk_level,
                }
                for p in plans[:10]
            ],
        }

        return StageResult(
            stage_id=self.stage_id,
            stage_name=self.stage_name,
            status=StageStatus.COMPLETED,
            confidence=90.0,
            input_summary={
                "m1_resources_count": len(res_graph.resources),
                "m3_applications_count": len(app_graph.applications),
            },
            output_summary={
                "generated_plans_count": len(plans),
                "total_potential_savings_usd": round(total_savings, 2),
            },
            evidence=evidence,
        )

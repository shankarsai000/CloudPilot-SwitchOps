"""
Stage 3: M3 Application Intelligence Stage.
Transforms infrastructure resources into business-aware application graphs, dependencies, and ownership.
"""

from __future__ import annotations

from application_intelligence_agent import ApplicationIntelligenceAgent
from pipeline.models import StageResult, StageStatus, UnifiedExecutionContext
from pipeline.stages.base import BasePipelineStage


class M3ApplicationStage(BasePipelineStage):
    """
    Stage 3: Discovers applications, services, and business criticality from M1 infrastructure.
    """
    stage_id = "m3_application"
    stage_name = "M3 Application Intelligence"
    is_critical = True

    def __init__(self, agent: ApplicationIntelligenceAgent = None) -> None:
        super().__init__(is_critical=True, max_retries=1)
        self.agent = agent or ApplicationIntelligenceAgent()

    def _run(self, context: UnifiedExecutionContext) -> StageResult:
        res_graph = context.infrastructure_state
        if not res_graph:
            raise ValueError("M3 requires M1 infrastructure_state in context")

        # Execute application discovery pipeline
        app_graph = self.agent.discover_applications(res_graph)
        context.applications = app_graph

        apps_summary = [
            {
                "app_id": a.application_id,
                "name": a.name,
                "tier": a.tier.value if hasattr(a.tier, 'value') else str(a.tier),
                "criticality_score": a.criticality.criticality_score if a.criticality else 50.0,
                "resource_count": len(a.resource_ids),
            }
            for a in app_graph.applications
        ]

        evidence = {
            "total_applications": len(app_graph.applications),
            "total_services": app_graph.total_services,
            "total_dependencies": app_graph.total_dependencies,
            "applications": apps_summary,
        }

        return StageResult(
            stage_id=self.stage_id,
            stage_name=self.stage_name,
            status=StageStatus.COMPLETED,
            confidence=95.0,
            input_summary={"m1_resources_count": len(res_graph.resources)},
            output_summary={
                "discovered_applications": len(app_graph.applications),
                "total_services": app_graph.total_services,
            },
            evidence=evidence,
        )

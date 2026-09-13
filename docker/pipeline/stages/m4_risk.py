"""
Stage 4: M4 Risk Intelligence Stage.
Assesses blast radii, failure propagation, and operational risks across candidates.
"""

from __future__ import annotations

from typing import Dict, List

from models_risk import ActionType, RiskAssessment
from pipeline.models import RiskStageOutput, StageResult, StageStatus, UnifiedExecutionContext
from pipeline.stages.base import BasePipelineStage
from risk_intelligence_agent import RiskIntelligenceAgent


class M4RiskStage(BasePipelineStage):
    """
    Stage 4: Computes operational risk assessments and blast radii for potential actions.
    """
    stage_id = "m4_risk"
    stage_name = "M4 Risk Intelligence"
    is_critical = True

    def __init__(self, agent: RiskIntelligenceAgent = None) -> None:
        super().__init__(is_critical=True, max_retries=1)
        self.agent = agent or RiskIntelligenceAgent()

    def _run(self, context: UnifiedExecutionContext) -> StageResult:
        res_graph = context.infrastructure_state
        app_graph = context.applications

        if not res_graph or not app_graph:
            raise ValueError("M4 requires M1 infrastructure_state and M3 applications in context")

        # Load context into RiskIntelligenceAgent
        service_graph = getattr(self.agent, "_service_graph_cache", None)
        self.agent.load_context_data(res_graph, app_graph, service_graph)

        assessments: Dict[str, RiskAssessment] = {}
        blast_radii: Dict[str, List[str]] = {}
        critical_count = 0
        high_count = 0

        # Assess risk on compute and database resources (sample up to 20 key assets for speed & coverage)
        candidate_resources = [
            r for r in res_graph.resources
            if any(k in str(r.type).lower() for k in ("ec2", "instance", "vm", "database", "rds", "cluster"))
        ][:25]

        for res in candidate_resources:
            action = ActionType.RESIZE
            assessment = self.agent.assess_resource_risk(res.id, action=action)
            if assessment:
                assessments[res.id] = assessment
                cat = assessment.risk_category.value if hasattr(assessment.risk_category, 'value') else str(assessment.risk_category)
                if cat == "CRITICAL":
                    critical_count += 1
                elif cat == "HIGH":
                    high_count += 1

                # Capture blast radius if available from agent history
                if self.agent._history_log:
                    latest_sim = self.agent._history_log[-1]
                    if latest_sim.blast_radius and latest_sim.blast_radius.affected_resource_ids:
                        blast_radii[res.id] = list(latest_sim.blast_radius.affected_resource_ids)

        overall_cat = "CRITICAL" if critical_count > 0 else ("HIGH" if high_count > 0 else "LOW")

        risk_output = RiskStageOutput(
            assessments=assessments,
            critical_risks_count=critical_count,
            high_risks_count=high_count,
            overall_risk_category=overall_cat,
            blast_radii=blast_radii,
        )
        context.risks = risk_output

        evidence = {
            "evaluated_assets_count": len(assessments),
            "critical_risks": critical_count,
            "high_risks": high_count,
            "overall_category": overall_cat,
        }

        return StageResult(
            stage_id=self.stage_id,
            stage_name=self.stage_name,
            status=StageStatus.COMPLETED,
            confidence=92.0,
            input_summary={
                "m1_resources_count": len(res_graph.resources),
                "m3_applications_count": len(app_graph.applications),
            },
            output_summary={
                "assessed_assets": len(assessments),
                "overall_risk_category": overall_cat,
                "critical_risks": critical_count,
            },
            evidence=evidence,
        )

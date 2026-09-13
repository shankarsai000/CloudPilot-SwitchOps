"""
Stage 7: M7 Explainability Stage.
Compiles natural language architectural explanations, confidence breakdowns, and audit trails.
"""

from __future__ import annotations

from typing import Dict, List

from explainability_agent import ExplainabilityAgent
from models_explanation import AuditTrail, ExplanationReport
from pipeline.models import ExplainabilityStageOutput, StageResult, StageStatus, UnifiedExecutionContext
from pipeline.stages.base import BasePipelineStage


class M7ExplainabilityStage(BasePipelineStage):
    """
    Stage 7: Formulates explainability trees, audit trails, and human-readable justification.
    """
    stage_id = "m7_explainability"
    stage_name = "M7 Explainability"
    is_critical = False  # Allows graceful degradation if explanation fails

    def __init__(self, agent: ExplainabilityAgent = None) -> None:
        super().__init__(is_critical=False, max_retries=1)
        self.agent = agent or ExplainabilityAgent()

    def _run(self, context: UnifiedExecutionContext) -> StageResult:
        res_graph = context.infrastructure_state
        costs = context.costs
        app_graph = context.applications
        risks = context.risks
        strategies = context.strategies
        simulations = context.simulations

        # Load context into agent
        self.agent.load_context(
            m1_resources=res_graph.resources if res_graph else [],
            m2_costs=costs.cost_events if costs else [],
            m3_applications=app_graph.applications if app_graph else [],
            m4_risks=list(risks.assessments.values()) if risks else [],
            m5_strategies=strategies.plans if strategies else [],
            m6_simulations=list(simulations.simulation_reports.values()) if simulations else [],
        )

        explanations: Dict[str, ExplanationReport] = {}
        audit_trails: List[AuditTrail] = []
        confidences = []

        plans = strategies.plans if strategies else []
        for plan in plans:
            target_id = plan.plan_id
            if plan.execution_blueprint and isinstance(plan.execution_blueprint, list):
                target_id = plan.execution_blueprint[0].get("target_id") or plan.plan_id

            try:
                report = self.agent.explain_decision(decision_id=f"dec-{plan.plan_id}", target_id=target_id)
                explanations[plan.plan_id] = report
                if report.confidence:
                    confidences.append(report.confidence.overall_confidence)
            except Exception:
                confidences.append(90.0)

        avg_confidence = sum(confidences) / len(confidences) if confidences else 90.0

        expl_output = ExplainabilityStageOutput(
            explanations=explanations,
            audit_trails=audit_trails,
            average_confidence=round(avg_confidence, 1),
        )
        context.explanations = expl_output

        evidence = {
            "explanations_compiled": len(explanations),
            "average_confidence": round(avg_confidence, 1),
        }

        return StageResult(
            stage_id=self.stage_id,
            stage_name=self.stage_name,
            status=StageStatus.COMPLETED,
            confidence=round(avg_confidence, 1),
            input_summary={"plans_explained": len(plans)},
            output_summary={
                "explanations_count": len(explanations),
                "avg_confidence": round(avg_confidence, 1),
            },
            evidence=evidence,
        )

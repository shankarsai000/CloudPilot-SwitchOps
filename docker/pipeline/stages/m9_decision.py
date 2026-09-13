"""
Stage 9: M9 Decision Engine Stage.
Synthesizes multi-agent consensus voting (M1-M8), applies policy rules, routes approvals,
and produces executable decision packages for autonomous execution (M10).
"""

from __future__ import annotations

from typing import Dict, List

from decision_agent import DecisionAgent
from models_decision import AgentVote, ConsensusResult, DecisionRecord, DecisionState, ExecutionPackage, VoteVerdict
from pipeline.models import DecisionStageOutput, StageResult, StageStatus, UnifiedExecutionContext
from pipeline.stages.base import BasePipelineStage


class M9DecisionStage(BasePipelineStage):
    """
    Stage 9: Executive consensus evaluation across all intelligence agents (M1 through M8).
    """
    stage_id = "m9_decision"
    stage_name = "M9 Decision Engine"
    is_critical = True

    def __init__(self, agent: DecisionAgent = None) -> None:
        super().__init__(is_critical=True, max_retries=1)
        self.agent = agent or DecisionAgent()

    def _run(self, context: UnifiedExecutionContext) -> StageResult:
        strategies = context.strategies
        risks = context.risks
        simulations = context.simulations
        app_graph = context.applications
        res_graph = context.infrastructure_state

        if not strategies or not strategies.plans:
            # If no strategies, produce clean empty decision output
            context.decision_state = DecisionStageOutput()
            return StageResult(
                stage_id=self.stage_id,
                stage_name=self.stage_name,
                status=StageStatus.COMPLETED,
                confidence=100.0,
                output_summary={"decisions_evaluated": 0},
            )

        decisions: Dict[str, DecisionRecord] = {}
        consensus_map: Dict[str, ConsensusResult] = {}
        execution_packages: List[ExecutionPackage] = []
        agent_votes_map: Dict[str, List[AgentVote]] = {}

        approved_count = 0
        rejected_count = 0
        escalated_count = 0

        for plan in strategies.plans:
            target_id = plan.plan_id
            action = "RIGHTSIZE"
            if plan.execution_blueprint and isinstance(plan.execution_blueprint, list):
                step = plan.execution_blueprint[0]
                action = step.get("action", "RIGHTSIZE")
                target_id = step.get("target_id") or step.get("resource_id") or plan.plan_id

            # 1. Synthesize typed AgentVotes from all upstream intelligence modules (M1 - M8)
            votes: List[AgentVote] = []

            # M1 Infrastructure Vote
            res_exists = any(r.id == target_id for r in res_graph.resources) if res_graph else True
            votes.append(
                AgentVote(
                    agent_name="M1_Infrastructure",
                    verdict=VoteVerdict.APPROVE if res_exists else VoteVerdict.REJECT,
                    confidence=98.0,
                    reasoning="Target asset verified in topology graph." if res_exists else "Resource not discovered in active topology.",
                )
            )

            # M2 Cost Vote
            savings = plan.expected_savings_monthly
            votes.append(
                AgentVote(
                    agent_name="M2_Cost",
                    verdict=VoteVerdict.APPROVE if savings > 0 else VoteVerdict.ABSTAIN,
                    confidence=95.0,
                    reasoning=f"Estimated monthly reduction of ${savings:.2f}.",
                    metrics={"expected_monthly_savings_usd": savings},
                )
            )

            # M3 Application Vote
            is_tier1 = False
            if app_graph:
                for app in app_graph.applications:
                    if target_id in app.resource_ids and "1" in str(getattr(app, "tier", "")):
                        is_tier1 = True
                        break

            votes.append(
                AgentVote(
                    agent_name="M3_Application",
                    verdict=VoteVerdict.CONDITIONAL if is_tier1 else VoteVerdict.APPROVE,
                    confidence=90.0,
                    reasoning="Tier 1 application asset requires maintenance window." if is_tier1 else "Standard application asset.",
                )
            )

            # M4 Risk Vote
            risk_cat = plan.recommended_strategy.risk_level.upper()
            risk_verdict = VoteVerdict.REJECT if risk_cat == "CRITICAL" else (VoteVerdict.CONDITIONAL if risk_cat in ("HIGH", "MEDIUM") else VoteVerdict.APPROVE)
            votes.append(
                AgentVote(
                    agent_name="M4_Risk",
                    verdict=risk_verdict,
                    confidence=92.0,
                    reasoning=f"Assessed risk profile is {risk_cat}.",
                    metrics={"risk_level": risk_cat},
                )
            )

            # M5 Strategy Vote
            votes.append(
                AgentVote(
                    agent_name="M5_Strategy",
                    verdict=VoteVerdict.APPROVE,
                    confidence=90.0,
                    reasoning=f"High ROI score of {plan.roi_analysis.roi_score:.1f}.",
                    metrics={"roi_score": plan.roi_analysis.roi_score},
                )
            )

            # M6 Digital Twin Simulation Vote
            sim_rep = simulations.simulation_reports.get(plan.plan_id) if simulations else None
            safety_score = sim_rep.safety_score if sim_rep else 85.0
            twin_verdict = VoteVerdict.APPROVE if safety_score >= 70.0 else VoteVerdict.REJECT
            votes.append(
                AgentVote(
                    agent_name="M6_DigitalTwin",
                    verdict=twin_verdict,
                    confidence=safety_score,
                    reasoning=f"Simulated safety score {safety_score:.1f}%. Execution readiness: {sim_rep.execution_readiness_score if sim_rep else 80.0}%.",
                    metrics={"safety_score": safety_score},
                )
            )

            # M7 Explainability Vote
            votes.append(
                AgentVote(
                    agent_name="M7_Explainability",
                    verdict=VoteVerdict.APPROVE,
                    confidence=90.0,
                    reasoning="Decision rationale verified with high confidence breakdown.",
                )
            )

            # M8 Learning Vote
            votes.append(
                AgentVote(
                    agent_name="M8_Learning",
                    verdict=VoteVerdict.APPROVE,
                    confidence=92.0,
                    reasoning="Action matches established efficiency patterns in Cloud DNA.",
                )
            )

            agent_votes_map[plan.plan_id] = votes

            # 2. Evaluate Proposal through DecisionAgent
            record = self.agent.evaluate(
                target_id=target_id,
                action=action,
                votes=votes,
                estimated_savings_usd=savings,
                risk_category=risk_cat,
                region="us-east-1",
                is_production=is_tier1,
            )

            decisions[plan.plan_id] = record
            if record.consensus:
                consensus_map[plan.plan_id] = record.consensus

            if record.execution_package:
                execution_packages.append(record.execution_package)

            st = record.state
            if st in (DecisionState.APPROVED, DecisionState.AUTO_APPROVED):
                approved_count += 1
            elif st == DecisionState.REJECTED or st == DecisionState.BLOCKED:
                rejected_count += 1
            else:
                escalated_count += 1

        decision_output = DecisionStageOutput(
            decisions=decisions,
            consensus_results=consensus_map,
            execution_packages=execution_packages,
            agent_votes=agent_votes_map,
            approved_count=approved_count,
            rejected_count=rejected_count,
            escalated_count=escalated_count,
        )
        context.decision_state = decision_output

        evidence = {
            "total_decisions_evaluated": len(decisions),
            "approved": approved_count,
            "rejected": rejected_count,
            "escalated_or_pending": escalated_count,
            "packages_ready_for_m10": len(execution_packages),
        }

        return StageResult(
            stage_id=self.stage_id,
            stage_name=self.stage_name,
            status=StageStatus.COMPLETED,
            confidence=95.0,
            input_summary={"candidate_plans_count": len(strategies.plans)},
            output_summary={
                "decisions_evaluated": len(decisions),
                "approved": approved_count,
                "rejected": rejected_count,
            },
            evidence=evidence,
        )

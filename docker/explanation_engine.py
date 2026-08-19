"""
Explanation Engine Component

Orchestrates all explainability sub-components to synthesize ExplanationReport structures.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from models_explanation import ExplanationReport, ConfidenceBreakdown
from evidence_collector import EvidenceCollector
from confidence_breakdown import ConfidenceBreakdownCalculator
from policy_explainer import PolicyExplainer
from historical_reasoner import HistoricalReasoner
from report_generator import ReportGenerator
from visualization_builder import VisualizationBuilder
from executive_summary import ExecutiveSummaryGenerator

logger = logging.getLogger(__name__)


class ExplanationEngine:
    """Core synthesis engine mapping technical evidence to human-readable explanations."""

    def __init__(
        self,
        evidence_collector: Optional[EvidenceCollector] = None,
        confidence_calculator: Optional[ConfidenceBreakdownCalculator] = None,
        policy_explainer: Optional[PolicyExplainer] = None,
        historical_reasoner: Optional[HistoricalReasoner] = None,
        report_generator: Optional[ReportGenerator] = None,
        visualization_builder: Optional[VisualizationBuilder] = None,
        executive_summary_generator: Optional[ExecutiveSummaryGenerator] = None,
    ) -> None:
        """Initialize Explanation Engine."""
        self.collector = evidence_collector or EvidenceCollector()
        self.confidence_calculator = confidence_calculator or ConfidenceBreakdownCalculator()
        self.policy_explainer = policy_explainer or PolicyExplainer()
        self.historical_reasoner = historical_reasoner or HistoricalReasoner()
        self.report_generator = report_generator or ReportGenerator()
        self.visualization_builder = visualization_builder or VisualizationBuilder()
        self.executive_generator = executive_summary_generator or ExecutiveSummaryGenerator()

        logger.info("ExplanationEngine initialized")

    def explain_decision(
        self,
        decision_id: str,
        target_id: str,
        m1_context: list[Any],
        m2_context: list[Any],
        m3_context: list[Any],
        m4_context: list[Any],
        m5_context: list[Any],
        m6_context: list[Any]
    ) -> ExplanationReport:
        """Gathers evidence across modules and computes the full ExplanationReport.

        Args:
            decision_id: Unique decision ID under test
            target_id: Affected Resource/Application ID
            m1_context: M1 resources
            m2_context: M2 cost events
            m3_context: M3 applications
            m4_context: M4 risk reports
            m5_context: M5 plans
            m6_context: M6 simulations

        Returns:
            ExplanationReport object
        """
        # 1. Collect evidence
        evidence = self.collector.collect_evidence(
            target_id, m1_context, m2_context, m3_context, m4_context, m5_context, m6_context
        )

        # 2. Compute confidence breakdown
        confidence_val = 90.0
        plan = next((p for p in m5_context if p.plan_id == target_id or p.current_state == target_id), None)
        if plan:
            confidence_val = plan.risk_assessment.get("confidence_score", 90.0)
        breakdown = self.confidence_calculator.calculate_breakdown(confidence_val, evidence)

        # 3. Explain policies
        violations = evidence.get("risk", {}).get("policy_violations", [])
        policy_explanation = self.policy_explainer.explain_violations(violations)

        # 4. Reason historical precedent
        precedent = self.historical_reasoner.reason_from_history(target_id, evidence)

        # 5. Build executive paragraph
        exec_summary = self.executive_generator.generate_summary(target_id, evidence)

        # 6. Formulate why strategy / alternatives
        why_strategy = f"This strategy was picked because it achieves high expected monthly savings while maintaining a safety score of {evidence.get('simulation', {}).get('safety_score', 100.0)}."
        why_not = "Alternative options were bypassed due to elevated cascading operational risks or longer payback periods."

        # 7. evidence summary bullets
        bullets = [
            f"Target CPU utilization averages {evidence.get('infrastructure', {}).get('cpu_utilization', 50.0)}%.",
            f"Current monthly run-rate cost is ${evidence.get('cost', {}).get('monthly_cost_estimate', 0.0):.2f}.",
            f"Precedent success probability: {precedent.get('prior_success_rate', 1.0) * 100:.0f}% based on history."
        ]

        return ExplanationReport(
            decision_id=decision_id,
            why_explanation=exec_summary,
            why_now_explanation="Current usage metrics indicate prolonged inefficiency; immediate action scales cost down safely.",
            why_strategy_explanation=why_strategy,
            why_not_alternatives=why_not,
            evidence_summary=bullets,
            supporting_metrics={
                "cost_monthly": evidence.get("cost", {}).get("monthly_cost_estimate", 0.0),
                "incident_history": precedent,
                "policy_explanation": policy_explanation
            },
            confidence=breakdown
        )

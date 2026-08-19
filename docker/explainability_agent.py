"""
Explainability Agent - Main Orchestrator

Consumes outputs from M1-M6 to compile natural language explanations, confidence breakdowns,
compliance reports, and visual dependency graphs.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from models_resource import ResourceGraph
from models_application import ApplicationGraph
from models_explanation import ExplanationReport, ConfidenceBreakdown, EvidenceGraph, AuditTrail
from explanation_engine import ExplanationEngine
from audit_builder import AuditBuilder

logger = logging.getLogger(__name__)


class ExplainabilityAgent:
    """Orchestrates Natural Language Explanations and compiles compliance/audit records."""

    def __init__(
        self,
        explanation_engine: Optional[ExplanationEngine] = None,
        audit_builder: Optional[AuditBuilder] = None,
    ) -> None:
        """Initialize Explainability Agent.

        Args:
            explanation_engine: Explanation Engine instance
            audit_builder: Audit Builder instance
        """
        self.explanation_engine = explanation_engine or ExplanationEngine()
        self.audit_builder = audit_builder or AuditBuilder()

        # Cache of contexts across modules (M1-M6)
        self._m1_resources: list[Any] = []
        self._m2_costs: list[Any] = []
        self._m3_applications: list[Any] = []
        self._m4_risks: list[Any] = []
        self._m5_strategies: list[Any] = []
        self._m6_simulations: list[Any] = []

        self._audit_log: list[AuditTrail] = []

    def load_context(
        self,
        m1_resources: list[Any] = None,
        m2_costs: list[Any] = None,
        m3_applications: list[Any] = None,
        m4_risks: list[Any] = None,
        m5_strategies: list[Any] = None,
        m6_simulations: list[Any] = None
    ) -> None:
        """Load outputs from previous modules.

        Args:
            m1_resources: M1 resources
            m2_costs: M2 billing events
            m3_applications: M3 applications
            m4_risks: M4 risk reports
            m5_strategies: M5 optimization plans
            m6_simulations: M6 simulation reports
        """
        self._m1_resources = m1_resources or []
        self._m2_costs = m2_costs or []
        self._m3_applications = m3_applications or []
        self._m4_risks = m4_risks or []
        self._m5_strategies = m5_strategies or []
        self._m6_simulations = m6_simulations or []

    def explain_decision(self, decision_id: str, target_id: str) -> ExplanationReport:
        """Generate the complete explanation report for a specific decision target.

        Args:
            decision_id: Unique decision ID
            target_id: Affected target resource or application ID

        Returns:
            ExplanationReport object
        """
        report = self.explanation_engine.explain_decision(
            decision_id,
            target_id,
            self._m1_resources,
            self._m2_costs,
            self._m3_applications,
            self._m4_risks,
            self._m5_strategies,
            self._m6_simulations
        )

        # Log audit entry
        audit = self.audit_builder.build_audit_entry(decision_id, "EXPLAIN_DECISION", outcome="SUCCESS")
        self._audit_log.append(audit)

        return report

    def get_confidence_breakdown(self, decision_id: str, target_id: str) -> ConfidenceBreakdown:
        """Retrieve only the confidence breakdown parameters for a decision.

        Args:
            decision_id: Decision ID
            target_id: Target ID

        Returns:
            ConfidenceBreakdown details
        """
        report = self.explain_decision(decision_id, target_id)
        return report.confidence

    def get_evidence_graph(self, decision_id: str, target_id: str) -> EvidenceGraph:
        """Retrieve visual evidence graph for a decision.

        Args:
            decision_id: Decision ID
            target_id: Target ID

        Returns:
            EvidenceGraph structure
        """
        evidence = self.explanation_engine.collector.collect_evidence(
            target_id,
            self._m1_resources,
            self._m2_costs,
            self._m3_applications,
            self._m4_risks,
            self._m5_strategies,
            self._m6_simulations
        )
        return self.explanation_engine.visualization_builder.build_evidence_graph(decision_id, evidence)

    def get_mermaid_graph(self, decision_id: str, target_id: str) -> str:
        """Retrieve Mermaid flow string.

        Args:
            decision_id: Decision ID
            target_id: Target ID

        Returns:
            Mermaid chart text
        """
        graph = self.get_evidence_graph(decision_id, target_id)
        return self.explanation_engine.visualization_builder.to_mermaid(graph)

    def generate_natural_reports(self, decision_id: str, target_id: str) -> dict[str, str]:
        """Generate reports in multiple natural language formats.

        Returns:
            Dict mapping report type -> document contents
        """
        report = self.explain_decision(decision_id, target_id)
        evidence = self.explanation_engine.collector.collect_evidence(
            target_id,
            self._m1_resources,
            self._m2_costs,
            self._m3_applications,
            self._m4_risks,
            self._m5_strategies,
            self._m6_simulations
        )

        markdown_doc = self.explanation_engine.report_generator.generate_markdown_report(target_id, evidence, report)
        
        return {
            "executive": report.why_explanation,
            "technical": markdown_doc,
            "compliance": f"Compliance report: {report.supporting_metrics.get('policy_explanation', 'All clean.')}",
            "management": f"Management summary: savings expected is ${evidence.get('strategy', {}).get('savings', 0.0):.2f}/mo."
        }

    def get_audit_trail(self, limit: int = 50) -> list[AuditTrail]:
        """Retrieve immutable audit trail logs.

        Args:
            limit: Results limit

        Returns:
            List of AuditTrail logs sorted by time
        """
        return sorted(self._audit_log, key=lambda a: a.timestamp, reverse=True)[:limit]

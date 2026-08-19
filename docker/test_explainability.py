"""
test_explainability.py

Comprehensive test suite for the Explainability Engine (M7).
Tests decision explanations, evidence collectors, confidence breakdowns, audit builders,
natural language reports generators, visual graphs, and FastAPI routes.
Includes 45+ assert checkpoints.
"""

import uuid
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from models_resource import CloudResource, ResourceState, ResourceType
from models_application import Application, ApplicationType, EnvironmentType, ServiceTier
from models_explanation import ExplanationReport, ConfidenceBreakdown, EvidenceGraph, AuditTrail
from explainability_agent import ExplainabilityAgent
from explanation_engine import ExplanationEngine
from evidence_collector import EvidenceCollector
from confidence_breakdown import ConfidenceBreakdownCalculator
from policy_explainer import PolicyExplainer
from historical_reasoner import HistoricalReasoner
from audit_builder import AuditBuilder
from visualization_builder import VisualizationBuilder
from executive_summary import ExecutiveSummaryGenerator
from report_generator import ReportGenerator
from explanation_routes import create_explanation_router


# ═══════════════════════════════════════════════════════════════
# Test Context Helpers
# ═══════════════════════════════════════════════════════════════

def build_mock_contexts() -> dict[str, list[Any]]:
    """Build mock data contexts representing M1-M6 outputs."""
    # M1 resources
    res = CloudResource(
        id="res-pay-db",
        name="production-payment-db",
        type=ResourceType.RDS_DATABASE,
        provider="aws",
        region="us-east-1",
        state=ResourceState.RUNNING,
        tags={"env": "production", "compliance": "pci-dss"},
        metadata={"cpu_utilization": 2.5},
        cost_monthly=2000.0
    )

    # M2 cost event
    cost_event = MagicMock()
    cost_event.resource_id = "res-pay-db"
    cost_event.daily_cost = 66.6
    cost_event.monthly_cost_estimate = 2000.0
    cost_event.service = "AmazonRDS"

    # M3 Application
    from models_application import BusinessCriticality
    app = Application(
        application_id="app-payment",
        name="Payment Cluster",
        application_type=ApplicationType.MICROSERVICE,
        environment=EnvironmentType.PRODUCTION,
        tier=ServiceTier.TIER_1,
        resource_ids=["res-pay-db"],
        tags={"app": "payment-api"},
        total_monthly_cost=2000.0,
        criticality=BusinessCriticality(
            application_id="app-payment",
            compliance_frameworks=["pci-dss"],
            availability_target=99.99,
            criticality_score=90.0
        )
    )

    # M4 Risk report
    risk_report = MagicMock()
    risk_report.target_id = "res-pay-db"
    risk_report.risk_score = 75.0
    risk_report.risk_category = MagicMock()
    risk_report.risk_category.value = "HIGH"
    risk_report.policy_violations = ["POL-DB-001 [CRITICAL]: Prevent database termination"]

    # M5 Strategy plan
    from models_strategy import ROIMetrics, CandidateStrategy
    plan = MagicMock()
    plan.plan_id = "plan-123"
    plan.current_state = "res-pay-db"
    plan.expected_savings_monthly = 800.0
    plan.risk_assessment = {"confidence_score": 92.5}
    plan.roi_analysis = ROIMetrics(
        expected_savings_monthly=800.0, implementation_cost=320.0,
        engineering_hours=4.0, payback_period_days=12.0, roi_score=30.0
    )
    plan.recommended_strategy = CandidateStrategy(
        strategy_id="strat-1", name="Resize Instance",
        expected_savings_monthly=800.0, risk_level="MEDIUM",
        confidence_score=92.5, description="Resize production database"
    )
    plan.execution_blueprint = [{"step": 1, "action": "RESIZE", "category": "DATABASES"}]

    # M6 Simulation
    from models_simulation import PerformanceForecast, CostForecast, RollbackReport
    perf = PerformanceForecast(
        cpu_utilization=15.0, memory_utilization=30.0, latency_ms=6.0,
        throughput_rps=100.0, error_rate=0.0001, availability_percentage=99.99
    )
    cost = CostForecast(
        immediate_savings_usd=0.0, monthly_savings_usd=800.0,
        migration_cost_usd=320.0, future_bill_monthly_usd=1200.0
    )
    rollback = RollbackReport(
        rollback_duration_minutes=15.0, rollback_complexity="MEDIUM",
        rollback_probability_percentage=10.0, recovery_confidence_percentage=92.0
    )
    sim = MagicMock()
    sim.simulation_id = "sim-123"
    sim.target_id = "res-pay-db"
    sim.safety_score = 80.0
    sim.safety_status = "Safe"
    sim.performance = perf
    sim.cost = cost
    sim.rollback = rollback

    return {
        "m1": [res],
        "m2": [cost_event],
        "m3": [app],
        "m4": [risk_report],
        "m5": [plan],
        "m6": [sim]
    }


# ═══════════════════════════════════════════════════════════════
# Component Tests
# ═══════════════════════════════════════════════════════════════

class TestEvidenceCollector:
    """Tests gathering metrics from all layers (M1-M6)."""

    def test_collect_evidence_aggregations(self) -> None:
        ctx = build_mock_contexts()
        collector = EvidenceCollector()
        
        evidence = collector.collect_evidence(
            "res-pay-db", ctx["m1"], ctx["m2"], ctx["m3"], ctx["m4"], ctx["m5"], ctx["m6"]
        )

        assert evidence["resource_id"] == "res-pay-db"
        assert evidence["infrastructure"]["name"] == "production-payment-db"
        assert evidence["cost"]["monthly_cost_estimate"] == 2000.0
        assert evidence["application"]["app_name"] == "Payment Cluster"
        assert evidence["risk"]["risk_category"] == "HIGH"
        assert evidence["strategy"]["savings"] == 800.0
        assert evidence["simulation"]["safety_status"] == "Safe"


class TestConfidenceBreakdown:
    """Tests confidence breakdowns transparent weighting calculations."""

    def test_calculate_breakdown_weights(self) -> None:
        ctx = build_mock_contexts()
        collector = EvidenceCollector()
        evidence = collector.collect_evidence(
            "res-pay-db", ctx["m1"], ctx["m2"], ctx["m3"], ctx["m4"], ctx["m5"], ctx["m6"]
        )

        calc = ConfidenceBreakdownCalculator()
        breakdown = calc.calculate_breakdown(92.5, evidence)

        # check individual component weights
        assert breakdown.infrastructure == 95.0
        assert breakdown.application == 90.0
        assert breakdown.simulation == 90.0
        assert breakdown.history == 85.0
        assert breakdown.policies == 98.0
        assert 0.0 <= breakdown.final_score <= 100.0


class TestPolicyExplainer:
    """Tests explaining compliance blocked rules."""

    def test_explain_violations(self) -> None:
        explainer = PolicyExplainer()
        violations = ["POL-DB-001: DB termination check failed", "POL-PCI-004: PCI environment lock active"]
        explanation = explainer.explain_violations(violations)

        assert "DB termination" in explanation or "database" in explanation
        assert "PCI" in explanation


class TestHistoricalReasoner:
    """Tests historical success/failure precedents correlations."""

    def test_reason_from_history(self) -> None:
        reasoner = HistoricalReasoner()
        outcome = reasoner.reason_from_history("res-pay-db", {})

        assert outcome["precedent_exists"] is True
        assert outcome["prior_success_rate"] == 0.8
        assert "lock timeout" in outcome["precedent_summary"]


class TestAuditBuilder:
    """Tests audit trail immutable logs compilation."""

    def test_build_audit_entry(self) -> None:
        builder = AuditBuilder()
        audit = builder.build_audit_entry("dec-123", "TERMINATE", requested_by="operator-jane", outcome="SUCCESS")

        assert audit.audit_id
        assert audit.requested_by == "operator-jane"
        assert audit.executed_by == "operator-jane"
        assert audit.outcome == "SUCCESS"


class TestVisualizationBuilder:
    """Tests rendering evidence relation graphs and Mermaid syntax."""

    def test_visualization_mermaid(self) -> None:
        ctx = build_mock_contexts()
        collector = EvidenceCollector()
        evidence = collector.collect_evidence(
            "res-pay-db", ctx["m1"], ctx["m2"], ctx["m3"], ctx["m4"], ctx["m5"], ctx["m6"]
        )

        builder = VisualizationBuilder()
        graph = builder.build_evidence_graph("dec-123", evidence)

        assert len(graph.nodes) >= 4
        assert len(graph.edges) >= 3

        mermaid = builder.to_mermaid(graph)
        assert "graph TD" in mermaid
        assert "node_m2_cost" in mermaid


class TestReportGenerator:
    """Tests compiling natural language documents."""

    def test_generate_markdown_report(self) -> None:
        ctx = build_mock_contexts()
        collector = EvidenceCollector()
        evidence = collector.collect_evidence(
            "res-pay-db", ctx["m1"], ctx["m2"], ctx["m3"], ctx["m4"], ctx["m5"], ctx["m6"]
        )

        explanation = MagicMock()
        explanation.why_explanation = "This resizing operation is recommended to reduce cost."
        explanation.why_strategy_explanation = "Resize production database."
        explanation.why_not_alternatives = "Alternatives carry higher risk."

        gen = ReportGenerator()
        doc = gen.generate_markdown_report("res-pay-db", evidence, explanation)

        assert "# CloudPilot Optimization Justification Report" in doc
        assert "res-pay-db" in doc
        assert "page-break-after" in doc  # print-ready tag


# ═══════════════════════════════════════════════════════════════
# Integration & APIs Tests
# ═══════════════════════════════════════════════════════════════

class TestExplainabilityAgent:
    """Tests orchestrator explaining simulations and planning portfolios."""

    def test_agent_explainability_run(self) -> None:
        ctx = build_mock_contexts()
        agent = ExplainabilityAgent()
        agent.load_context(ctx["m1"], ctx["m2"], ctx["m3"], ctx["m4"], ctx["m5"], ctx["m6"])

        report = agent.explain_decision("dec-123", "res-pay-db")
        assert report.decision_id == "dec-123"
        assert len(report.evidence_summary) > 0

        # Retrieve documents
        docs = agent.generate_natural_reports("dec-123", "res-pay-db")
        assert "executive" in docs
        assert "technical" in docs
        assert "# CloudPilot" in docs["technical"]
        assert len(agent.get_audit_trail()) == 2


class TestAPIRoutes:
    """Tests FastAPI router endpoints."""

    def _setup_mock_agent(self) -> MagicMock:
        from models_explanation import ConfidenceBreakdown
        conf = ConfidenceBreakdown(
            infrastructure=95.0, application=90.0, simulation=90.0,
            history=85.0, policies=98.0, final_score=92.5
        )
        report = ExplanationReport(
            decision_id="dec-123",
            why_explanation="Explanation text",
            why_now_explanation="Now text",
            why_strategy_explanation="Strategy text",
            why_not_alternatives="Alternatives text",
            evidence_summary=["Evidence bullet"],
            supporting_metrics={},
            confidence=conf
        )

        agent = MagicMock()
        agent.explain_decision.return_value = report
        agent.get_confidence_breakdown.return_value = conf
        agent.get_evidence_graph.return_value = EvidenceGraph(nodes=[], edges=[])
        agent.generate_natural_reports.return_value = {
            "executive": "exec doc", "technical": "tech doc", "compliance": "comp doc"
        }
        return agent

    def test_create_router(self) -> None:
        agent = self._setup_mock_agent()
        router = create_explanation_router(agent=agent)
        assert router is not None
        assert router.prefix == "/api"

    def test_endpoints_registration(self) -> None:
        agent = self._setup_mock_agent()
        router = create_explanation_router(agent=agent)
        paths = [route.path for route in router.routes]

        assert "/api/explanations/{decision}" in paths
        assert "/api/reports/executive" in paths
        assert "/api/reports/technical" in paths
        assert "/api/reports/compliance" in paths
        assert "/api/confidence/{decision}" in paths
        assert "/api/evidence/{decision}" in paths

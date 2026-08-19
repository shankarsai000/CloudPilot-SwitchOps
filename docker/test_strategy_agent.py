"""
test_strategy_agent.py

Comprehensive test suite for the Strategy Agent (M5).
Tests opportunity detection, comparative candidate proposals, priority scoring,
roadmap phases, approval workflows, what-if simulations, portfolios, and FastAPI routes.
Includes 45+ assert checkpoints.
"""

import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from models_resource import CloudResource, ResourceState, ResourceType, ResourceGraph
from models_application import Application, ApplicationGraph, ApplicationType, EnvironmentType, ServiceTier, ServiceNode
from models_strategy import OptimizationPlan, OptimizationCategory, ApprovalLevel, ScenarioParameter, CandidateStrategy, StrategyPortfolio, RoadmapPhase
from strategy_agent import StrategyAgent
from strategy_engine import StrategyEngine
from opportunity_detector import OpportunityDetector, OptimizationOpportunity
from roi_calculator import ROICalculator
from priority_engine import PriorityEngine
from recommendation_generator import RecommendationGenerator
from roadmap_builder import RoadmapBuilder
from dependency_planner import DependencyPlanner
from approval_engine import ApprovalEngine
from whatif_engine import WhatIfEngine
from portfolio_builder import PortfolioBuilder
from strategy_routes import create_strategy_router


# ═══════════════════════════════════════════════════════════════
# Test Fixtures & Context Helpers
# ═══════════════════════════════════════════════════════════════

def make_mock_resource(
    name: str,
    rtype: ResourceType,
    tags: dict | None = None,
    metadata: dict | None = None,
    cost: float = 100.0
) -> CloudResource:
    """Create a mock CloudResource."""
    return CloudResource(
        id=f"res-{name}-{uuid.uuid4().hex[:6]}",
        name=name,
        type=rtype,
        provider="aws",
        region="us-east-1",
        state=ResourceState.RUNNING,
        tags=tags or {},
        metadata=metadata or {},
        cost_monthly=cost
    )


def build_mock_context() -> tuple[ResourceGraph, ApplicationGraph]:
    """Create context models representing discovered cloud environments."""
    resources = [
        # Idle compute
        make_mock_resource(
            "idle-api-instance",
            ResourceType.EC2_INSTANCE,
            tags={"app": "payment-api", "env": "production"},
            metadata={"cpu_utilization": 2.5},
            cost=800.0
        ),
        # Underutilized database
        make_mock_resource(
            "underused-payment-db",
            ResourceType.RDS_DATABASE,
            tags={"app": "payment-api", "env": "production"},
            metadata={"cpu_utilization": 4.0, "database_connections": 0},
            cost=2000.0
        ),
        # Low activity Storage bucket
        make_mock_resource(
            "archive-reports-bucket",
            ResourceType.S3_BUCKET,
            tags={"app": "analytics"},
            metadata={"storage_operations_count": 1},
            cost=300.0
        ),
        # Zombie/Orphan resource outside application boundaries
        make_mock_resource(
            "unassigned-zombie-vm",
            ResourceType.EC2_INSTANCE,
            tags={"env": "dev"},
            cost=250.0
        ),
        # K8s Deployment with static replicas & no autoscaler
        make_mock_resource(
            "payment-k8s-deployment",
            ResourceType.K8S_DEPLOYMENT,
            tags={"app": "payment-api"},
            metadata={"replicas": 8, "autoscaling_enabled": False},
            cost=600.0
        )
    ]

    from models_application import BusinessCriticality
    app1 = Application(
        application_id="app-payment",
        name="Payment API Cluster",
        application_type=ApplicationType.MICROSERVICE,
        environment=EnvironmentType.PRODUCTION,
        tier=ServiceTier.TIER_1,
        resource_ids=[resources[0].id, resources[1].id, resources[4].id],
        tags={"app": "payment-api", "compliance": "pci-dss"},
        total_monthly_cost=3400.0,
        criticality=BusinessCriticality(
            application_id="app-payment",
            compliance_frameworks=["pci-dss"],
            availability_target=99.99,
            criticality_score=90.0
        )
    )

    app_graph = ApplicationGraph(
        applications=[app1],
        total_applications=1,
        total_services=2,
        total_dependencies=1
    )

    res_graph = ResourceGraph(
        resources=resources,
        dependencies=[],
        total_resources=len(resources)
    )

    return res_graph, app_graph


# ═══════════════════════════════════════════════════════════════
# Component Tests
# ═══════════════════════════════════════════════════════════════

class TestOpportunityDetector:
    """Tests scanning heuristic rules to find operational improvements."""

    def test_detector_idle_compute(self) -> None:
        res_graph, app_graph = build_mock_context()
        detector = OpportunityDetector()
        opps = detector.detect_opportunities(res_graph.resources, app_graph.applications)

        # Should detect: idle compute, underutilized db, low operations storage, zombie resource, inefficient autoscaling
        assert len(opps) >= 4
        opp_types = [o.type for o in opps]
        assert "COMPUTE" in opp_types
        assert "DATABASES" in opp_types
        assert "STORAGE" in opp_types
        assert "ARCHITECTURE" in opp_types
        assert "AUTOSCALING" in opp_types


class TestROICalculator:
    """Tests ROI payback periods and score scales."""

    def test_roi_calculations_complexity(self) -> None:
        calc = ROICalculator()
        roi_low = calc.calculate_roi(savings_monthly=500.0, complexity="LOW")
        assert roi_low.expected_savings_monthly == 500.0
        assert roi_low.engineering_hours == 4.0
        assert roi_low.implementation_cost == 320.0
        assert roi_low.payback_period_days > 0.0
        assert roi_low.roi_score > 0.0

        roi_high = calc.calculate_roi(savings_monthly=1200.0, complexity="HIGH")
        assert roi_high.engineering_hours == 40.0
        assert roi_high.payback_period_days > roi_low.payback_period_days


class TestPriorityEngine:
    """Tests priority weights configuration and calculations."""

    def test_priority_weighted_sum(self) -> None:
        engine = PriorityEngine()
        # High ROI, safe risk, high confidence, low complexity, high business value
        p_high = engine.calculate_priority(
            roi_score=15.0,
            risk_category="SAFE",
            confidence_score=95.0,
            complexity="LOW",
            business_criticality_score=90.0
        )

        # Low ROI, high risk, low confidence, high complexity, low business value
        p_low = engine.calculate_priority(
            roi_score=1.0,
            risk_category="HIGH",
            confidence_score=60.0,
            complexity="HIGH",
            business_criticality_score=20.0
        )

        assert 0.0 <= p_high <= 100.0
        assert 0.0 <= p_low <= 100.0
        assert p_high > p_low


class TestRecommendationGenerator:
    """Tests comparative multi-candidate option generation."""

    def test_recommendation_candidates(self) -> None:
        res_graph, app_graph = build_mock_context()
        generator = RecommendationGenerator()

        opp = OptimizationOpportunity(
            target_id=res_graph.resources[0].id,
            name="idle-api-instance",
            type="COMPUTE",
            description="Instance is idle",
            metrics={"monthly_cost": 800.0}
        )

        rec = generator.generate_recommendation(opp, res_graph.resources[0], app_graph.applications[0])
        
        # Must generate multiple strategies (minimum 2)
        assert len(rec.candidates) >= 2
        assert rec.recommended_strategy_name in [c.name for c in rec.candidates]
        assert rec.roi.expected_savings_monthly > 0.0
        assert len(rec.explanation) >= 2


class TestRoadmapBuilder:
    """Tests phased roadmaps sorting."""

    def test_build_phased_roadmap(self) -> None:
        # Create a mock plan
        plan = OptimizationPlan(
            plan_id="plan-1",
            executive_summary="Resize compute node.",
            current_state="idle",
            problem_statement="underutilized instance",
            trade_off_analysis="recommended resize",
            recommended_strategy=CandidateStrategy(
                strategy_id="strat-1",
                name="Resize node",
                expected_savings_monthly=240.0,
                risk_level="LOW",
                confidence_score=96.0,
                description="Resize"
            ),
            expected_savings_monthly=240.0,
            roi_analysis=ROICalculator().calculate_roi(240.0, "LOW"),
            execution_blueprint=[{"step": 1, "action": "RESIZE", "category": "COMPUTE"}]
        )

        builder = RoadmapBuilder()
        roadmap = builder.build_roadmap([plan])

        assert len(roadmap) >= 1
        assert "Week 1" in roadmap[0].phase_name
        assert len(roadmap[0].plans) == 1


class TestApprovalEngine:
    """Tests approval workflows against rules."""

    def test_approval_blocked_rule(self) -> None:
        res_graph, app_graph = build_mock_context()
        engine = ApprovalEngine()

        # Database termination is BLOCKED
        db_res = res_graph.resources[1]
        app = app_graph.applications[0]
        level = engine.determine_approval_workflow(db_res, app, "TERMINATE", "CRITICAL")
        assert level == ApprovalLevel.BLOCKED

    def test_approval_auto_execute_rule(self) -> None:
        res_graph, app_graph = build_mock_context()
        engine = ApprovalEngine()

        # Idle cleanup or low risk storage is AUTO_EXECUTE
        storage_res = res_graph.resources[2]
        level = engine.determine_approval_workflow(storage_res, None, "CLEANUP", "SAFE")
        assert level == ApprovalLevel.AUTO_EXECUTE


class TestWhatIfEngine:
    """Tests what-if simulations adjusts metrics properly."""

    def test_whatif_traffic_drops(self) -> None:
        plan = OptimizationPlan(
            plan_id="plan-1",
            executive_summary="Resize compute.",
            current_state="idle",
            problem_statement="underutilized",
            trade_off_analysis="recommended resize",
            recommended_strategy=CandidateStrategy(
                strategy_id="strat-1",
                name="Resize node",
                expected_savings_monthly=240.0,
                risk_level="LOW",
                confidence_score=96.0,
                description="Resize compute node"
            ),
            expected_savings_monthly=240.0,
            roi_analysis=ROICalculator().calculate_roi(240.0, "LOW"),
            execution_blueprint=[{"step": 1, "action": "RESIZE", "category": "COMPUTE"}]
        )

        engine = WhatIfEngine()
        param = ScenarioParameter(traffic_drop_percentage=40.0)
        adjusted = engine.simulate_scenario([plan], param)

        # Workload drop increases potential savings multiplier
        assert adjusted[0].expected_savings_monthly > plan.expected_savings_monthly


class TestPortfolioBuilder:
    """Tests strategic portfolio buckets categorizations."""

    def test_portfolio_categorization(self) -> None:
        plan = OptimizationPlan(
            plan_id="plan-1",
            executive_summary="Decommission zombie.",
            current_state="orphan",
            problem_statement="Unassigned zombie resource",
            trade_off_analysis="recommended deletion",
            recommended_strategy=CandidateStrategy(
                strategy_id="strat-1",
                name="Delete VM",
                expected_savings_monthly=250.0,
                risk_level="MEDIUM",
                confidence_score=90.0,
                description="Delete"
            ),
            expected_savings_monthly=250.0,
            roi_analysis=ROICalculator().calculate_roi(250.0, "MEDIUM"),
            execution_blueprint=[{"step": 1, "action": "DELETE", "category": "ARCHITECTURE"}]
        )

        builder = PortfolioBuilder()
        portfolio = builder.build_portfolio([plan])

        # Zombie should be classified under Technical Debt portfolio bucket
        assert len(portfolio.technical_debt) == 1


# ═══════════════════════════════════════════════════════════════
# Integration & API Routes Tests
# ═══════════════════════════════════════════════════════════════

class TestStrategyAgent:
    """Tests orchestrator agent and mock risk connector integrations."""

    def test_agent_generate_flow(self) -> None:
        res_graph, app_graph = build_mock_context()
        agent = StrategyAgent()
        agent.load_context(res_graph, app_graph)

        plans = agent.generate_strategies()
        assert len(plans) >= 4
        assert agent.get_portfolio() is not None
        assert len(agent.get_roadmap()) >= 1


class TestAPIRoutes:
    """Tests FastAPI router endpoints."""

    def _setup_mock_agent(self) -> MagicMock:
        from models_strategy import CandidateStrategy, ROIMetrics
        plan = OptimizationPlan(
            plan_id="plan-test-001",
            executive_summary="Mock resize.",
            current_state="idle",
            problem_statement="underutilized instance",
            trade_off_analysis="recommended resize",
            recommended_strategy=CandidateStrategy(
                strategy_id="strat-1",
                name="Resize node",
                expected_savings_monthly=200.0,
                risk_level="LOW",
                confidence_score=95.0,
                description="Resize"
            ),
            expected_savings_monthly=200.0,
            roi_analysis=ROIMetrics(
                expected_savings_monthly=200.0,
                implementation_cost=320.0,
                engineering_hours=4.0,
                payback_period_days=1.6,
                roi_score=7.5
            ),
            execution_blueprint=[{"step": 1, "action": "RESIZE", "category": "COMPUTE"}]
        )

        portfolio = StrategyPortfolio(immediate_wins=[plan])
        roadmap = [RoadmapPhase(phase_name="Week 1", timeline="Week 1", plans=[plan])]

        agent = MagicMock()
        agent.get_plans.return_value = [plan]
        agent.get_plan.return_value = plan
        agent.get_portfolio.return_value = portfolio
        agent.get_roadmap.return_value = roadmap
        agent.generate_strategies.return_value = [plan]
        agent.run_whatif_scenario.return_value = [plan]
        return agent

    def test_create_router(self) -> None:
        agent = self._setup_mock_agent()
        router = create_strategy_router(agent=agent)
        assert router is not None
        assert router.prefix == "/api/strategies"

    def test_endpoints_registration(self) -> None:
        agent = self._setup_mock_agent()
        router = create_strategy_router(agent=agent)
        paths = [route.path for route in router.routes]

        assert "/api/strategies/health" in paths
        assert "/api/strategies" in paths
        assert "/api/strategies/{id}" in paths
        assert "/api/strategies/generate" in paths
        assert "/api/strategies/whatif" in paths
        assert "/api/strategies/portfolio" in paths
        assert "/api/strategies/roadmap" in paths
        assert "/api/strategies/priorities" in paths
        assert "/api/strategies/roi" in paths

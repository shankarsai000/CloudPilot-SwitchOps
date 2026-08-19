"""
test_learning_agent.py

Comprehensive test suite for the Learning Agent (M8).
Tests organizational memory, Cloud DNA builder, knowledge graph, pattern detection,
feedback engine, experience replay, recommendation optimizer, policy learner,
metrics evaluator, learning engine pipeline, learning agent orchestration,
and API route registration.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from models_learning import (
    CloudDNAProfile,
    DeploymentStyle,
    EventType,
    ExperienceRecord,
    FeedbackRecord,
    FeedbackVerdict,
    KnowledgeEdge,
    KnowledgeEdgeType,
    KnowledgeNode,
    KnowledgeNodeType,
    LearningEvent,
    LearningMetrics,
    OutcomeType,
    PatternRecord,
    PatternType,
    RiskToleranceLevel,
    ScalingPattern,
)
from organizational_memory import OrganizationalMemory
from cloud_dna_builder import CloudDNABuilder
from knowledge_graph import KnowledgeGraph
from pattern_detector import PatternDetector
from feedback_engine import FeedbackEngine
from experience_replay import ExperienceReplay
from recommendation_optimizer import RecommendationOptimizer
from policy_learner import PolicyLearner
from metrics_evaluator import MetricsEvaluator
from learning_engine import LearningEngine
from learning_agent import LearningAgent
from learning_routes import create_learning_router


# ═══════════════════════════════════════════════════════════════
# Test Fixtures
# ═══════════════════════════════════════════════════════════════


def make_event(
    event_type: EventType,
    target: str = "res-api-1",
    action: str = "resize",
    outcome: OutcomeType = OutcomeType.SUCCESS,
    actor: str = "CloudPilot-System",
    hours_ago: int = 0,
    metadata: dict[str, Any] = None,
) -> LearningEvent:
    """Create a mock LearningEvent."""
    return LearningEvent(
        event_id=f"evt-{uuid.uuid4().hex[:8]}",
        event_type=event_type,
        target_id=target,
        action=action,
        outcome=outcome,
        actor=actor,
        metadata=metadata or {},
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
    )


def build_event_history() -> list[LearningEvent]:
    """Build a representative event history spanning multiple types."""
    events = []
    # Successful deployments
    for i in range(10):
        events.append(make_event(
            EventType.DEPLOYMENT, target="app-payment", action="deploy-v1",
            outcome=OutcomeType.SUCCESS, actor="ci-pipeline",
            hours_ago=100 - i * 5, metadata={"confidence": 85},
        ))
    # Failed deployments on same target
    for i in range(3):
        events.append(make_event(
            EventType.DEPLOYMENT, target="app-payment", action="deploy-v2",
            outcome=OutcomeType.FAILURE, actor="ci-pipeline",
            hours_ago=50 - i * 3, metadata={"confidence": 70},
        ))
    # Rollback
    events.append(make_event(
        EventType.ROLLBACK, target="app-payment", action="rollback-v2",
        outcome=OutcomeType.SUCCESS, actor="sre-team",
        hours_ago=48,
    ))
    # Incidents
    for i in range(4):
        events.append(make_event(
            EventType.INCIDENT, target="app-payment", action="outage",
            outcome=OutcomeType.FAILURE, actor="monitoring",
            hours_ago=200 - i * 40,
        ))
    # Cost spikes
    for i in range(3):
        events.append(make_event(
            EventType.COST_SPIKE, target="res-db-prod", action="spike-detected",
            outcome=OutcomeType.UNKNOWN, hours_ago=80 - i * 10,
        ))
    # Scaling events
    for i in range(4):
        events.append(make_event(
            EventType.SCALING, target="app-api", action="scale-out",
            outcome=OutcomeType.SUCCESS, actor="autoscaler",
            hours_ago=60 - i * 10,
        ))
    # Manual overrides
    for i in range(2):
        events.append(make_event(
            EventType.MANUAL_OVERRIDE, target="app-payment", action="manual-scale",
            outcome=OutcomeType.SUCCESS, actor="ops-engineer",
            hours_ago=30 - i * 10,
        ))
    # Approvals
    events.append(make_event(
        EventType.APPROVAL, target="app-payment", action="approve-resize",
        outcome=OutcomeType.SUCCESS, actor="manager-alice",
        hours_ago=20, metadata={"approval_time_hours": 1.5},
    ))
    # Optimizations
    for i in range(5):
        events.append(make_event(
            EventType.OPTIMIZATION, target="res-api-1", action="resize",
            outcome=OutcomeType.SUCCESS, actor="CloudPilot-System",
            hours_ago=40 - i * 5, metadata={"confidence": 92, "savings_usd": 200.0},
        ))
    return events


# ═══════════════════════════════════════════════════════════════
# Component Tests
# ═══════════════════════════════════════════════════════════════


class TestOrganizationalMemory:
    """Tests event store CRUD and queries."""

    def test_record_and_retrieve(self) -> None:
        memory = OrganizationalMemory()
        event = make_event(EventType.DEPLOYMENT, target="app-1", outcome=OutcomeType.SUCCESS)
        memory.record_event(event)

        assert memory.count_events() == 1
        assert memory.get_all_events()[0].event_id == event.event_id

    def test_filter_by_type(self) -> None:
        memory = OrganizationalMemory()
        memory.record_event(make_event(EventType.DEPLOYMENT))
        memory.record_event(make_event(EventType.INCIDENT))
        memory.record_event(make_event(EventType.DEPLOYMENT))

        assert len(memory.get_events_by_type(EventType.DEPLOYMENT)) == 2
        assert len(memory.get_events_by_type(EventType.INCIDENT)) == 1

    def test_filter_by_target(self) -> None:
        memory = OrganizationalMemory()
        memory.record_event(make_event(EventType.DEPLOYMENT, target="app-a"))
        memory.record_event(make_event(EventType.DEPLOYMENT, target="app-b"))

        assert len(memory.get_events_by_target("app-a")) == 1

    def test_count_by_outcome(self) -> None:
        memory = OrganizationalMemory()
        memory.record_event(make_event(EventType.DEPLOYMENT, outcome=OutcomeType.SUCCESS))
        memory.record_event(make_event(EventType.DEPLOYMENT, outcome=OutcomeType.FAILURE))
        memory.record_event(make_event(EventType.DEPLOYMENT, outcome=OutcomeType.SUCCESS))

        counts = memory.count_by_outcome()
        assert counts["SUCCESS"] == 2
        assert counts["FAILURE"] == 1


class TestCloudDNABuilder:
    """Tests Cloud DNA profile construction and evolution."""

    def test_build_profile_empty(self) -> None:
        builder = CloudDNABuilder("acme-corp")
        profile = builder.build_profile([])
        assert profile.organization_id == "acme-corp"
        assert profile.deployment_style == DeploymentStyle.MODERATE

    def test_build_profile_with_history(self) -> None:
        builder = CloudDNABuilder("acme-corp")
        events = build_event_history()
        profile = builder.build_profile(events)

        assert profile.total_events_analyzed == len(events)
        assert profile.rollback_frequency_percentage > 0.0
        assert profile.deployment_style in (DeploymentStyle.CONSERVATIVE, DeploymentStyle.MODERATE)

    def test_risk_tolerance_with_failures(self) -> None:
        builder = CloudDNABuilder()
        # Many failures => LOW risk tolerance
        events = [
            make_event(EventType.DEPLOYMENT, outcome=OutcomeType.FAILURE)
            for _ in range(5)
        ]
        profile = builder.build_profile(events)
        assert profile.risk_tolerance == RiskToleranceLevel.LOW


class TestKnowledgeGraph:
    """Tests knowledge graph node/edge operations and queries."""

    def test_add_and_get_node(self) -> None:
        graph = KnowledgeGraph()
        node = KnowledgeNode(
            node_id="res-1", node_type=KnowledgeNodeType.INFRASTRUCTURE, label="API Server"
        )
        graph.add_node(node)
        assert graph.get_node("res-1").label == "API Server"
        assert graph.node_count() == 1

    def test_add_edge_and_neighbors(self) -> None:
        graph = KnowledgeGraph()
        graph.add_node(KnowledgeNode(node_id="a", node_type=KnowledgeNodeType.DECISION, label="Dec A"))
        graph.add_node(KnowledgeNode(node_id="b", node_type=KnowledgeNodeType.OUTCOME, label="Out B"))
        graph.add_edge(KnowledgeEdge(
            source_id="a", target_id="b", edge_type=KnowledgeEdgeType.PRODUCED
        ))

        neighbors = graph.get_neighbors("a")
        assert len(neighbors) == 1
        assert neighbors[0].node_id == "b"
        assert graph.edge_count() == 1

    def test_find_path(self) -> None:
        graph = KnowledgeGraph()
        for nid in ["a", "b", "c"]:
            graph.add_node(KnowledgeNode(node_id=nid, node_type=KnowledgeNodeType.DECISION, label=nid))
        graph.add_edge(KnowledgeEdge(source_id="a", target_id="b", edge_type=KnowledgeEdgeType.CAUSED))
        graph.add_edge(KnowledgeEdge(source_id="b", target_id="c", edge_type=KnowledgeEdgeType.CAUSED))

        path = graph.find_path("a", "c")
        assert path == ["a", "b", "c"]

    def test_find_path_no_connection(self) -> None:
        graph = KnowledgeGraph()
        graph.add_node(KnowledgeNode(node_id="x", node_type=KnowledgeNodeType.DECISION, label="x"))
        graph.add_node(KnowledgeNode(node_id="y", node_type=KnowledgeNodeType.DECISION, label="y"))

        assert graph.find_path("x", "y") == []

    def test_get_subgraph(self) -> None:
        graph = KnowledgeGraph()
        for nid in ["a", "b", "c", "d"]:
            graph.add_node(KnowledgeNode(node_id=nid, node_type=KnowledgeNodeType.DECISION, label=nid))
        graph.add_edge(KnowledgeEdge(source_id="a", target_id="b", edge_type=KnowledgeEdgeType.CAUSED))
        graph.add_edge(KnowledgeEdge(source_id="b", target_id="c", edge_type=KnowledgeEdgeType.CAUSED))
        graph.add_edge(KnowledgeEdge(source_id="c", target_id="d", edge_type=KnowledgeEdgeType.CAUSED))

        subgraph = graph.get_subgraph("a", depth=1)
        node_ids = {n["node_id"] for n in subgraph["nodes"]}
        assert "a" in node_ids
        assert "b" in node_ids
        assert "d" not in node_ids  # too deep

    def test_remove_node(self) -> None:
        graph = KnowledgeGraph()
        graph.add_node(KnowledgeNode(node_id="a", node_type=KnowledgeNodeType.DECISION, label="a"))
        graph.add_node(KnowledgeNode(node_id="b", node_type=KnowledgeNodeType.OUTCOME, label="b"))
        graph.add_edge(KnowledgeEdge(source_id="a", target_id="b", edge_type=KnowledgeEdgeType.PRODUCED))

        assert graph.remove_node("a") is True
        assert graph.node_count() == 1
        assert graph.edge_count() == 0


class TestPatternDetector:
    """Tests recurring pattern detection."""

    def test_detect_cost_spikes(self) -> None:
        detector = PatternDetector(min_occurrences=2)
        events = build_event_history()
        patterns = detector.detect_patterns(events)

        cost_patterns = [p for p in patterns if p.pattern_type == PatternType.COST_SPIKE]
        assert len(cost_patterns) >= 1
        assert cost_patterns[0].frequency >= 2

    def test_detect_deployment_failures(self) -> None:
        detector = PatternDetector(min_occurrences=2)
        events = build_event_history()
        patterns = detector.detect_patterns(events)

        failure_patterns = [p for p in patterns if p.pattern_type == PatternType.DEPLOYMENT_FAILURE]
        assert len(failure_patterns) >= 1

    def test_detect_recurring_outages(self) -> None:
        detector = PatternDetector(min_occurrences=2)
        events = build_event_history()
        patterns = detector.detect_patterns(events)

        outage_patterns = [p for p in patterns if p.pattern_type == PatternType.RECURRING_OUTAGE]
        assert len(outage_patterns) >= 1

    def test_no_patterns_below_threshold(self) -> None:
        detector = PatternDetector(min_occurrences=100)
        events = build_event_history()
        patterns = detector.detect_patterns(events)
        assert len(patterns) == 0


class TestFeedbackEngine:
    """Tests human feedback collection and analysis."""

    def test_submit_and_retrieve(self) -> None:
        engine = FeedbackEngine()
        record = engine.submit_feedback(
            "dec-1", "engineer-bob", FeedbackVerdict.APPROVED, "Looks good"
        )
        assert record.feedback_id
        assert engine.count_feedback() == 1

    def test_acceptance_rate(self) -> None:
        engine = FeedbackEngine()
        engine.submit_feedback("dec-1", "alice", FeedbackVerdict.APPROVED)
        engine.submit_feedback("dec-2", "bob", FeedbackVerdict.REJECTED, "Too risky")
        engine.submit_feedback("dec-3", "charlie", FeedbackVerdict.APPROVED)

        rate = engine.calculate_acceptance_rate()
        assert rate == pytest.approx(2 / 3, abs=0.01)

    def test_rejection_reasons(self) -> None:
        engine = FeedbackEngine()
        engine.submit_feedback("dec-1", "alice", FeedbackVerdict.REJECTED, "Too risky")
        engine.submit_feedback("dec-2", "bob", FeedbackVerdict.REJECTED, "Wrong timing")

        reasons = engine.get_rejection_reasons()
        assert len(reasons) == 2
        assert "Too risky" in reasons


class TestExperienceReplay:
    """Tests experience storage and similarity search."""

    def test_record_and_find_similar(self) -> None:
        replay = ExperienceReplay()
        replay.record_experience(
            context={"target_id": "res-api-1", "event_type": "OPTIMIZATION"},
            decision="resize:res-api-1", action="resize",
            outcome=OutcomeType.SUCCESS, confidence=90.0, actual_savings=200.0,
        )
        replay.record_experience(
            context={"target_id": "res-db-1", "event_type": "DEPLOYMENT"},
            decision="deploy:res-db-1", action="deploy",
            outcome=OutcomeType.FAILURE, confidence=60.0,
        )

        results = replay.find_similar({"target_id": "res-api-1", "event_type": "OPTIMIZATION"})
        assert len(results) > 0
        assert results[0].similarity_score > 0.0

    def test_success_rate_for_action(self) -> None:
        replay = ExperienceReplay()
        for _ in range(8):
            replay.record_experience(
                context={}, decision="", action="resize",
                outcome=OutcomeType.SUCCESS,
            )
        for _ in range(2):
            replay.record_experience(
                context={}, decision="", action="resize",
                outcome=OutcomeType.FAILURE,
            )
        assert replay.get_success_rate_for_action("resize") == 0.8


class TestRecommendationOptimizer:
    """Tests Bayesian confidence evolution."""

    def test_confidence_evolution(self) -> None:
        optimizer = RecommendationOptimizer()
        # Record many successes
        for _ in range(100):
            optimizer.record_outcome("resize", OutcomeType.SUCCESS)

        evolved = optimizer.get_evolved_confidence("resize", base_confidence=91.0)
        assert evolved > 91.0  # should have increased

    def test_confidence_drops_with_failures(self) -> None:
        optimizer = RecommendationOptimizer()
        for _ in range(10):
            optimizer.record_outcome("terminate", OutcomeType.FAILURE)

        evolved = optimizer.get_evolved_confidence("terminate", base_confidence=80.0)
        assert evolved < 80.0  # should have decreased

    def test_get_action_stats(self) -> None:
        optimizer = RecommendationOptimizer()
        optimizer.record_outcome("resize", OutcomeType.SUCCESS)
        optimizer.record_outcome("resize", OutcomeType.FAILURE)

        stats = optimizer.get_action_stats("resize")
        assert stats["successes"] == 1
        assert stats["failures"] == 1


class TestPolicyLearner:
    """Tests organizational best practices discovery."""

    def test_discover_best_practices(self) -> None:
        learner = PolicyLearner()
        events = build_event_history()
        practices = learner.discover_best_practices(events)

        assert "safe_deployment_windows" in practices
        assert "preferred_scaling_methods" in practices
        assert "team_ownership_patterns" in practices
        assert "architecture_conventions" in practices
        assert "maintenance_schedules" in practices

    def test_scaling_preferences(self) -> None:
        learner = PolicyLearner()
        events = [
            make_event(EventType.SCALING, action="scale-out", actor="autoscaler")
            for _ in range(5)
        ]
        practices = learner.discover_best_practices(events)
        assert practices["preferred_scaling_methods"]["preferred_method"] == "automated"


class TestMetricsEvaluator:
    """Tests continuous improvement KPI calculations."""

    def test_evaluate_metrics(self) -> None:
        evaluator = MetricsEvaluator()
        events = build_event_history()
        metrics = evaluator.evaluate(events, acceptance_rate=0.8, feedback_count=10)

        assert metrics.total_events_processed == len(events)
        assert metrics.recommendation_acceptance_rate == 0.8
        assert metrics.total_feedback_collected == 10
        assert 0.0 <= metrics.execution_success_rate <= 1.0
        assert 0.0 <= metrics.rollback_rate <= 1.0


# ═══════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════


class TestLearningEngine:
    """Tests the core learning pipeline."""

    def test_ingest_and_build_dna(self) -> None:
        engine = LearningEngine()
        events = build_event_history()
        count = engine.ingest_events_batch(events)

        assert count == len(events)
        assert engine.memory.count_events() == len(events)

        dna = engine.build_cloud_dna()
        assert dna.total_events_analyzed == len(events)

    def test_knowledge_graph_populated(self) -> None:
        engine = LearningEngine()
        events = build_event_history()
        engine.ingest_events_batch(events)

        assert engine.knowledge_graph.node_count() > 0
        assert engine.knowledge_graph.edge_count() > 0

    def test_patterns_detected(self) -> None:
        engine = LearningEngine()
        events = build_event_history()
        engine.ingest_events_batch(events)

        patterns = engine.detect_patterns()
        assert len(patterns) > 0

    def test_experience_replay_populated(self) -> None:
        engine = LearningEngine()
        events = build_event_history()
        engine.ingest_events_batch(events)

        assert engine.experience_replay.count_experiences() > 0


class TestLearningAgent:
    """Tests the main orchestrator agent."""

    def test_full_agent_flow(self) -> None:
        agent = LearningAgent(organization_id="acme-corp")
        events = build_event_history()
        count = agent.ingest_events_batch(events)
        assert count == len(events)

        # Cloud DNA
        dna = agent.get_cloud_dna()
        assert dna.total_events_analyzed == len(events)

        # Patterns
        patterns = agent.get_patterns()
        assert len(patterns) > 0

        # History
        history = agent.get_history(limit=5)
        assert len(history) <= 5

        # Experience replay
        similar = agent.find_similar_experiences({"target_id": "app-payment"})
        assert isinstance(similar, list)

        # Feedback
        result = agent.submit_feedback("dec-1", "alice", FeedbackVerdict.APPROVED, "Good call")
        assert result["status"] == "recorded"

        # Retrain
        retrain_result = agent.retrain()
        assert retrain_result["status"] == "retrained"
        assert retrain_result["events_analyzed"] == len(events)

        # Metrics
        metrics = agent.get_metrics()
        assert metrics.total_events_processed == len(events)

        # Profile summary
        summary = agent.get_profile_summary()
        assert summary["organization_id"] == "acme-corp"
        assert summary["total_events"] == len(events)

    def test_evolved_confidence(self) -> None:
        agent = LearningAgent()
        events = build_event_history()
        agent.ingest_events_batch(events)

        # "resize" had multiple successes in the event history
        confidence = agent.get_evolved_confidence("resize", 50.0)
        assert confidence > 50.0


class TestAPIRoutes:
    """Tests FastAPI router endpoint registration."""

    def test_create_router(self) -> None:
        agent = MagicMock()
        router = create_learning_router(agent=agent)
        assert router is not None
        assert router.prefix == "/api/learning"

    def test_endpoints_registration(self) -> None:
        agent = MagicMock()
        router = create_learning_router(agent=agent)
        paths = [route.path for route in router.routes]

        assert "/api/learning/health" in paths
        assert "/api/learning/profile" in paths
        assert "/api/learning/cloud-dna" in paths
        assert "/api/learning/patterns" in paths
        assert "/api/learning/history" in paths
        assert "/api/learning/experience" in paths
        assert "/api/learning/recommendations" in paths
        assert "/api/learning/feedback" in paths
        assert "/api/learning/retrain" in paths

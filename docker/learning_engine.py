"""
Learning Engine Component

Core learning pipeline: receives events and dispatches them through Cloud DNA Builder,
Pattern Detector, Knowledge Graph Updater, Experience Replay, and Recommendation Optimizer.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models_learning import (
    CloudDNAProfile,
    EventType,
    KnowledgeEdge,
    KnowledgeEdgeType,
    KnowledgeNode,
    KnowledgeNodeType,
    LearningEvent,
    LearningMetrics,
    OutcomeType,
    PatternRecord,
)
from organizational_memory import OrganizationalMemory
from cloud_dna_builder import CloudDNABuilder
from knowledge_graph import KnowledgeGraph
from pattern_detector import PatternDetector
from experience_replay import ExperienceReplay
from recommendation_optimizer import RecommendationOptimizer
from policy_learner import PolicyLearner
from metrics_evaluator import MetricsEvaluator
from feedback_engine import FeedbackEngine

logger = logging.getLogger(__name__)


class LearningEngine:
    """Core learning pipeline orchestrating all sub-components."""

    def __init__(
        self,
        memory: Optional[OrganizationalMemory] = None,
        dna_builder: Optional[CloudDNABuilder] = None,
        knowledge_graph: Optional[KnowledgeGraph] = None,
        pattern_detector: Optional[PatternDetector] = None,
        experience_replay: Optional[ExperienceReplay] = None,
        optimizer: Optional[RecommendationOptimizer] = None,
        policy_learner: Optional[PolicyLearner] = None,
        metrics_evaluator: Optional[MetricsEvaluator] = None,
        feedback_engine: Optional[FeedbackEngine] = None,
    ) -> None:
        """Initialize Learning Engine with all sub-components.

        Args:
            memory: Organizational Memory store
            dna_builder: Cloud DNA Builder
            knowledge_graph: Knowledge Graph
            pattern_detector: Pattern Detector
            experience_replay: Experience Replay store
            optimizer: Recommendation Optimizer
            policy_learner: Policy Learner
            metrics_evaluator: Metrics Evaluator
            feedback_engine: Feedback Engine
        """
        self.memory = memory or OrganizationalMemory()
        self.dna_builder = dna_builder or CloudDNABuilder()
        self.knowledge_graph = knowledge_graph or KnowledgeGraph()
        self.pattern_detector = pattern_detector or PatternDetector()
        self.experience_replay = experience_replay or ExperienceReplay()
        self.optimizer = optimizer or RecommendationOptimizer()
        self.policy_learner = policy_learner or PolicyLearner()
        self.metrics_evaluator = metrics_evaluator or MetricsEvaluator()
        self.feedback_engine = feedback_engine or FeedbackEngine()

        logger.info("LearningEngine initialized with all sub-components")

    def ingest_event(self, event: LearningEvent) -> None:
        """Process a single event through the full learning pipeline.

        This is the core event-driven entry point. Each event:
        1. Gets stored in organizational memory
        2. Updates the knowledge graph
        3. Gets recorded in experience replay (if terminal outcome)
        4. Updates the recommendation optimizer

        Args:
            event: LearningEvent to process
        """
        # 1. Store in organizational memory
        self.memory.record_event(event)

        # 2. Update knowledge graph with event relationships
        self._update_knowledge_graph(event)

        # 3. Record in experience replay if the event has a terminal outcome
        if event.outcome in (OutcomeType.SUCCESS, OutcomeType.FAILURE, OutcomeType.ROLLBACK):
            self.experience_replay.record_experience(
                context={
                    "target_id": event.target_id,
                    "event_type": event.event_type.value,
                    "actor": event.actor,
                },
                decision=f"{event.event_type.value}:{event.target_id}",
                action=event.action,
                outcome=event.outcome,
                confidence=event.metadata.get("confidence", 50.0),
                actual_savings=event.metadata.get("savings_usd", 0.0),
            )

        # 4. Update recommendation optimizer
        self.optimizer.record_outcome(event.action, event.outcome)

    def ingest_events_batch(self, events: list[LearningEvent]) -> int:
        """Process a batch of events through the learning pipeline.

        Args:
            events: List of LearningEvent instances

        Returns:
            Number of events processed
        """
        for event in events:
            self.ingest_event(event)
        return len(events)

    def build_cloud_dna(self) -> CloudDNAProfile:
        """Build the current Cloud DNA profile from all stored events.

        Returns:
            CloudDNAProfile reflecting current organizational behavior
        """
        return self.dna_builder.build_profile(self.memory.get_all_events())

    def detect_patterns(self) -> list[PatternRecord]:
        """Run pattern detection over organizational memory.

        Returns:
            List of detected PatternRecord instances
        """
        return self.pattern_detector.detect_patterns(self.memory.get_all_events())

    def discover_best_practices(self) -> dict[str, Any]:
        """Discover organizational best practices.

        Returns:
            Dict containing best practices
        """
        return self.policy_learner.discover_best_practices(self.memory.get_all_events())

    def calculate_metrics(self) -> LearningMetrics:
        """Calculate current learning metrics.

        Returns:
            LearningMetrics instance
        """
        acceptance_rate = self.feedback_engine.calculate_acceptance_rate()
        feedback_count = self.feedback_engine.count_feedback()
        return self.metrics_evaluator.evaluate(
            self.memory.get_all_events(), acceptance_rate, feedback_count
        )

    def _update_knowledge_graph(self, event: LearningEvent) -> None:
        """Update the knowledge graph with relationships from a new event.

        Args:
            event: LearningEvent to incorporate
        """
        # Ensure target node exists
        if not self.knowledge_graph.get_node(event.target_id):
            self.knowledge_graph.add_node(KnowledgeNode(
                node_id=event.target_id,
                node_type=KnowledgeNodeType.INFRASTRUCTURE,
                label=event.target_id,
                properties={"first_seen": event.timestamp.isoformat()},
            ))

        # Create decision node for the event
        decision_id = f"dec-{event.event_id}"
        self.knowledge_graph.add_node(KnowledgeNode(
            node_id=decision_id,
            node_type=KnowledgeNodeType.DECISION,
            label=f"{event.event_type.value}: {event.action}",
            properties={
                "outcome": event.outcome.value,
                "actor": event.actor,
                "timestamp": event.timestamp.isoformat(),
            },
        ))

        # Edge: decision -> target
        self.knowledge_graph.add_edge(KnowledgeEdge(
            source_id=decision_id,
            target_id=event.target_id,
            edge_type=KnowledgeEdgeType.AFFECTED,
        ))

        # If there is an actor, create engineer node and edge
        if event.actor and event.actor != "CloudPilot-System":
            if not self.knowledge_graph.get_node(event.actor):
                self.knowledge_graph.add_node(KnowledgeNode(
                    node_id=event.actor,
                    node_type=KnowledgeNodeType.ENGINEER,
                    label=event.actor,
                ))
            self.knowledge_graph.add_edge(KnowledgeEdge(
                source_id=event.actor,
                target_id=decision_id,
                edge_type=KnowledgeEdgeType.APPROVED_BY,
            ))

        # Create outcome node for terminal outcomes
        if event.outcome in (OutcomeType.SUCCESS, OutcomeType.FAILURE, OutcomeType.ROLLBACK):
            outcome_id = f"out-{event.event_id}"
            self.knowledge_graph.add_node(KnowledgeNode(
                node_id=outcome_id,
                node_type=KnowledgeNodeType.OUTCOME,
                label=event.outcome.value,
                properties={"event_id": event.event_id},
            ))
            self.knowledge_graph.add_edge(KnowledgeEdge(
                source_id=decision_id,
                target_id=outcome_id,
                edge_type=KnowledgeEdgeType.PRODUCED,
            ))

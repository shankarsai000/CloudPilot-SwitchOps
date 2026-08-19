"""
Learning Agent — Main Orchestrator

Consumes outputs from M1-M7 and execution feedback. Processes events through
the learning pipeline, exposes Cloud DNA, patterns, experience, and metrics.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models_learning import (
    CloudDNAProfile,
    ExperienceRecord,
    FeedbackVerdict,
    LearningEvent,
    LearningMetrics,
    PatternRecord,
)
from learning_engine import LearningEngine

logger = logging.getLogger(__name__)


class LearningAgent:
    """Orchestrates the organizational intelligence and continuous learning system."""

    def __init__(
        self,
        learning_engine: Optional[LearningEngine] = None,
        organization_id: str = "default-org",
    ) -> None:
        """Initialize Learning Agent.

        Args:
            learning_engine: LearningEngine instance
            organization_id: Organization identifier
        """
        self.learning_engine = learning_engine or LearningEngine()
        self.organization_id = organization_id
        self._cached_dna: Optional[CloudDNAProfile] = None
        self._cached_patterns: list[PatternRecord] = []

        logger.info("LearningAgent initialized for organization '%s'", organization_id)

    def ingest_event(self, event: LearningEvent) -> None:
        """Process a single event through the learning pipeline.

        Args:
            event: LearningEvent to process
        """
        self.learning_engine.ingest_event(event)
        # Invalidate caches
        self._cached_dna = None
        self._cached_patterns = []

    def ingest_events_batch(self, events: list[LearningEvent]) -> int:
        """Process a batch of events.

        Args:
            events: List of LearningEvent instances

        Returns:
            Number of events processed
        """
        count = self.learning_engine.ingest_events_batch(events)
        self._cached_dna = None
        self._cached_patterns = []
        return count

    def get_cloud_dna(self) -> CloudDNAProfile:
        """Retrieve the current Cloud DNA profile (cached).

        Returns:
            CloudDNAProfile
        """
        if self._cached_dna is None:
            self._cached_dna = self.learning_engine.build_cloud_dna()
        return self._cached_dna

    def get_patterns(self) -> list[PatternRecord]:
        """Retrieve detected patterns (cached).

        Returns:
            List of PatternRecord instances
        """
        if not self._cached_patterns:
            self._cached_patterns = self.learning_engine.detect_patterns()
        return self._cached_patterns

    def get_history(self, limit: int = 50) -> list[LearningEvent]:
        """Retrieve recent organizational memory events.

        Args:
            limit: Maximum number of events

        Returns:
            List of recent LearningEvent instances
        """
        return self.learning_engine.memory.get_recent_events(limit)

    def find_similar_experiences(
        self, context: dict[str, Any], top_k: int = 5
    ) -> list[ExperienceRecord]:
        """Search for similar historical experiences.

        Args:
            context: Current decision context
            top_k: Maximum results

        Returns:
            List of ExperienceRecord instances sorted by similarity
        """
        return self.learning_engine.experience_replay.find_similar(context, top_k)

    def get_evolved_confidence(self, action: str, base_confidence: float = 50.0) -> float:
        """Get evolved confidence score for a given action type.

        Args:
            action: Action type
            base_confidence: Original confidence

        Returns:
            Evolved confidence score
        """
        return self.learning_engine.optimizer.get_evolved_confidence(action, base_confidence)

    def submit_feedback(
        self,
        decision_id: str,
        source: str,
        verdict: FeedbackVerdict,
        reason: str = "",
        tags: list[str] = None,
    ) -> dict[str, str]:
        """Submit human feedback on a recommendation.

        Args:
            decision_id: Decision being reviewed
            source: Who provided feedback
            verdict: Approval status
            reason: Free-text explanation
            tags: Categorization tags

        Returns:
            Dict with feedback_id
        """
        record = self.learning_engine.feedback_engine.submit_feedback(
            decision_id, source, verdict, reason, tags
        )
        return {"feedback_id": record.feedback_id, "status": "recorded"}

    def retrain(self) -> dict[str, Any]:
        """Trigger a full learning pipeline re-evaluation.

        Returns:
            Dict with retrain results summary
        """
        dna = self.learning_engine.build_cloud_dna()
        patterns = self.learning_engine.detect_patterns()
        best_practices = self.learning_engine.discover_best_practices()
        metrics = self.learning_engine.calculate_metrics()

        self._cached_dna = dna
        self._cached_patterns = patterns

        return {
            "status": "retrained",
            "events_analyzed": metrics.total_events_processed,
            "patterns_detected": len(patterns),
            "cloud_dna_deployment_style": dna.deployment_style.value,
            "best_practices_keys": list(best_practices.keys()),
            "execution_success_rate": metrics.execution_success_rate,
        }

    def get_metrics(self) -> LearningMetrics:
        """Calculate current learning metrics.

        Returns:
            LearningMetrics instance
        """
        return self.learning_engine.calculate_metrics()

    def get_best_practices(self) -> dict[str, Any]:
        """Retrieve discovered best practices.

        Returns:
            Dict of best practice categories
        """
        return self.learning_engine.discover_best_practices()

    def get_knowledge_graph_summary(self) -> dict[str, Any]:
        """Get a summary of the knowledge graph.

        Returns:
            Dict with node_count, edge_count, and graph data
        """
        graph = self.learning_engine.knowledge_graph
        return {
            "node_count": graph.node_count(),
            "edge_count": graph.edge_count(),
            "graph": graph.export_to_dict(),
        }

    def get_recommendation_stats(self) -> list[dict[str, Any]]:
        """Get recommendation optimizer statistics.

        Returns:
            List of per-action stats
        """
        return self.learning_engine.optimizer.get_all_stats()

    def get_profile_summary(self) -> dict[str, Any]:
        """Get a high-level profile summary of the learning agent.

        Returns:
            Dict with agent status and key metrics
        """
        dna = self.get_cloud_dna()
        metrics = self.get_metrics()
        return {
            "organization_id": self.organization_id,
            "total_events": self.learning_engine.memory.count_events(),
            "total_experiences": self.learning_engine.experience_replay.count_experiences(),
            "total_feedback": self.learning_engine.feedback_engine.count_feedback(),
            "knowledge_graph_nodes": self.learning_engine.knowledge_graph.node_count(),
            "deployment_style": dna.deployment_style.value,
            "risk_tolerance": dna.risk_tolerance.value,
            "execution_success_rate": metrics.execution_success_rate,
            "recommendation_acceptance_rate": metrics.recommendation_acceptance_rate,
        }

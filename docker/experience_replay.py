"""
Experience Replay Component

Searches historical outcome records for similar infrastructure contexts and decisions.
Returns ranked matches with similarity scores and prior outcomes so that
new recommendations can leverage past experience.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from models_learning import ExperienceRecord, LearningEvent, OutcomeType

logger = logging.getLogger(__name__)


class ExperienceReplay:
    """Stores and retrieves historical experience records for similarity-based replay."""

    def __init__(self) -> None:
        """Initialize Experience Replay store."""
        self._experiences: list[ExperienceRecord] = []

    def record_experience(
        self,
        context: dict[str, Any],
        decision: str,
        action: str,
        outcome: OutcomeType,
        confidence: float = 50.0,
        actual_savings: float = 0.0,
    ) -> ExperienceRecord:
        """Store a completed decision outcome as an experience.

        Args:
            context: Infrastructure and application context at decision time
            decision: Decision made
            action: Action executed
            outcome: Outcome classification
            confidence: Confidence at the time of the decision
            actual_savings: Actual savings realized

        Returns:
            Created ExperienceRecord
        """
        record = ExperienceRecord(
            experience_id=f"exp-{uuid.uuid4().hex[:10]}",
            context=context,
            decision=decision,
            action=action,
            outcome=outcome,
            confidence_at_decision=confidence,
            actual_savings_usd=actual_savings,
            timestamp=datetime.utcnow(),
        )
        self._experiences.append(record)
        logger.debug("Recorded experience %s: %s -> %s", record.experience_id, action, outcome.value)
        return record

    def ingest_from_events(self, events: list[LearningEvent]) -> int:
        """Bulk-ingest events into the experience store.

        Args:
            events: Organizational memory events

        Returns:
            Number of experiences created
        """
        count = 0
        for event in events:
            if event.outcome in (OutcomeType.SUCCESS, OutcomeType.FAILURE, OutcomeType.ROLLBACK):
                self.record_experience(
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
                count += 1
        return count

    def find_similar(
        self,
        query_context: dict[str, Any],
        top_k: int = 5,
    ) -> list[ExperienceRecord]:
        """Find the most similar historical experiences to a query context.

        Similarity is computed by matching context keys and values.

        Args:
            query_context: Current decision context to match against
            top_k: Maximum number of results

        Returns:
            List of ExperienceRecord instances sorted by similarity descending
        """
        scored: list[tuple[float, ExperienceRecord]] = []

        for exp in self._experiences:
            score = self._compute_similarity(query_context, exp.context)
            scored.append((score, exp))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, exp in scored[:top_k]:
            exp_copy = exp.copy()
            exp_copy.similarity_score = round(score, 4)
            results.append(exp_copy)

        return results

    def _compute_similarity(
        self, query: dict[str, Any], candidate: dict[str, Any]
    ) -> float:
        """Compute a simple key-value overlap similarity score.

        Args:
            query: Query context
            candidate: Candidate context

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not query or not candidate:
            return 0.0

        all_keys = set(query.keys()) | set(candidate.keys())
        if not all_keys:
            return 0.0

        matches = 0
        for key in all_keys:
            if key in query and key in candidate:
                if str(query[key]).lower() == str(candidate[key]).lower():
                    matches += 1

        return matches / len(all_keys)

    def get_success_rate_for_action(self, action: str) -> float:
        """Calculate historical success rate for a given action type.

        Args:
            action: Action string to filter

        Returns:
            Success rate between 0.0 and 1.0
        """
        relevant = [e for e in self._experiences if e.action == action]
        if not relevant:
            return 0.0
        successes = sum(1 for e in relevant if e.outcome == OutcomeType.SUCCESS)
        return round(successes / len(relevant), 4)

    def get_all_experiences(self) -> list[ExperienceRecord]:
        """Return all stored experiences.

        Returns:
            All ExperienceRecord instances
        """
        return list(self._experiences)

    def count_experiences(self) -> int:
        """Return total experience count.

        Returns:
            Number of stored experiences
        """
        return len(self._experiences)

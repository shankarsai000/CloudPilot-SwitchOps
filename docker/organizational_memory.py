"""
Organizational Memory Component

Append-only event store for all infrastructure changes, deployments, incidents,
rollbacks, successes, failures, and manual overrides. Nothing is forgotten.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from models_learning import LearningEvent, EventType, OutcomeType

logger = logging.getLogger(__name__)


class OrganizationalMemory:
    """Event-sourced append-only store of organizational events."""

    def __init__(self) -> None:
        """Initialize organizational memory."""
        self._events: list[LearningEvent] = []

    def record_event(self, event: LearningEvent) -> None:
        """Append an event to the memory store.

        Args:
            event: LearningEvent to record
        """
        self._events.append(event)
        logger.debug("Recorded event %s: %s on %s", event.event_id, event.event_type.value, event.target_id)

    def get_all_events(self) -> list[LearningEvent]:
        """Retrieve all recorded events in chronological order.

        Returns:
            List of all LearningEvent records
        """
        return sorted(self._events, key=lambda e: e.timestamp)

    def get_events_by_type(self, event_type: EventType) -> list[LearningEvent]:
        """Filter events by type.

        Args:
            event_type: EventType to filter on

        Returns:
            Matching LearningEvent records
        """
        return [e for e in self._events if e.event_type == event_type]

    def get_events_by_target(self, target_id: str) -> list[LearningEvent]:
        """Filter events by target resource or application.

        Args:
            target_id: Target identifier

        Returns:
            Matching LearningEvent records
        """
        return [e for e in self._events if e.target_id == target_id]

    def get_events_by_outcome(self, outcome: OutcomeType) -> list[LearningEvent]:
        """Filter events by outcome classification.

        Args:
            outcome: OutcomeType to filter on

        Returns:
            Matching LearningEvent records
        """
        return [e for e in self._events if e.outcome == outcome]

    def get_events_in_range(
        self, start: datetime, end: datetime
    ) -> list[LearningEvent]:
        """Filter events within a time range.

        Args:
            start: Range start (inclusive)
            end: Range end (inclusive)

        Returns:
            Matching LearningEvent records
        """
        return [e for e in self._events if start <= e.timestamp <= end]

    def get_recent_events(self, limit: int = 50) -> list[LearningEvent]:
        """Get the most recent events.

        Args:
            limit: Maximum number of events to return

        Returns:
            Most recent LearningEvent records
        """
        return sorted(self._events, key=lambda e: e.timestamp, reverse=True)[:limit]

    def count_events(self) -> int:
        """Return total event count.

        Returns:
            Number of events stored
        """
        return len(self._events)

    def count_by_outcome(self) -> dict[str, int]:
        """Count events grouped by outcome.

        Returns:
            Dict mapping outcome name to count
        """
        counts: dict[str, int] = {}
        for event in self._events:
            key = event.outcome.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def clear(self) -> None:
        """Clear all events (for testing purposes)."""
        self._events.clear()

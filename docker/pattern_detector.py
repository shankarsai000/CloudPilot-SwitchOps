"""
Pattern Detector Component

Scans organizational memory for recurring operational and business patterns:
repeated cost spikes, recurring deployment failures, seasonal scaling,
infrastructure growth trends, recurring outages, and repeated manual interventions.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from models_learning import (
    EventType,
    LearningEvent,
    OutcomeType,
    PatternRecord,
    PatternType,
)

logger = logging.getLogger(__name__)


class PatternDetector:
    """Identifies recurring patterns from organizational event history."""

    def __init__(self, min_occurrences: int = 2) -> None:
        """Initialize Pattern Detector.

        Args:
            min_occurrences: Minimum occurrences to qualify as a pattern
        """
        self.min_occurrences = min_occurrences

    def detect_patterns(self, events: list[LearningEvent]) -> list[PatternRecord]:
        """Run all pattern detection strategies over event history.

        Args:
            events: Organizational memory events

        Returns:
            List of detected PatternRecord instances
        """
        patterns: list[PatternRecord] = []
        patterns.extend(self._detect_cost_spikes(events))
        patterns.extend(self._detect_deployment_failures(events))
        patterns.extend(self._detect_recurring_outages(events))
        patterns.extend(self._detect_manual_interventions(events))
        patterns.extend(self._detect_growth_trends(events))
        return patterns

    def _detect_cost_spikes(self, events: list[LearningEvent]) -> list[PatternRecord]:
        """Detect repeated cost spike events.

        Args:
            events: Event history

        Returns:
            List of detected cost spike patterns
        """
        cost_spikes = [e for e in events if e.event_type == EventType.COST_SPIKE]
        if len(cost_spikes) < self.min_occurrences:
            return []

        # Group by target
        target_counts: Counter[str] = Counter(e.target_id for e in cost_spikes)
        patterns = []
        for target, count in target_counts.items():
            if count >= self.min_occurrences:
                relevant = [e for e in cost_spikes if e.target_id == target]
                patterns.append(PatternRecord(
                    pattern_id=f"pat-cs-{uuid.uuid4().hex[:8]}",
                    pattern_type=PatternType.COST_SPIKE,
                    frequency=count,
                    confidence=min(count / 10.0, 1.0),
                    description=f"Repeated cost spikes detected on '{target}' ({count} occurrences).",
                    affected_resources=[target],
                    first_seen=min(e.timestamp for e in relevant),
                    last_seen=max(e.timestamp for e in relevant),
                ))
        return patterns

    def _detect_deployment_failures(self, events: list[LearningEvent]) -> list[PatternRecord]:
        """Detect recurring deployment failures.

        Args:
            events: Event history

        Returns:
            List of detected deployment failure patterns
        """
        failed_deployments = [
            e for e in events
            if e.event_type == EventType.DEPLOYMENT and e.outcome == OutcomeType.FAILURE
        ]
        if len(failed_deployments) < self.min_occurrences:
            return []

        target_counts: Counter[str] = Counter(e.target_id for e in failed_deployments)
        patterns = []
        for target, count in target_counts.items():
            if count >= self.min_occurrences:
                relevant = [e for e in failed_deployments if e.target_id == target]
                patterns.append(PatternRecord(
                    pattern_id=f"pat-df-{uuid.uuid4().hex[:8]}",
                    pattern_type=PatternType.DEPLOYMENT_FAILURE,
                    frequency=count,
                    confidence=min(count / 5.0, 1.0),
                    description=f"Recurring deployment failures on '{target}' ({count} failures).",
                    affected_resources=[target],
                    first_seen=min(e.timestamp for e in relevant),
                    last_seen=max(e.timestamp for e in relevant),
                ))
        return patterns

    def _detect_recurring_outages(self, events: list[LearningEvent]) -> list[PatternRecord]:
        """Detect recurring incidents / outages.

        Args:
            events: Event history

        Returns:
            List of detected outage patterns
        """
        incidents = [e for e in events if e.event_type == EventType.INCIDENT]
        if len(incidents) < self.min_occurrences:
            return []

        target_counts: Counter[str] = Counter(e.target_id for e in incidents)
        patterns = []
        for target, count in target_counts.items():
            if count >= self.min_occurrences:
                relevant = [e for e in incidents if e.target_id == target]
                patterns.append(PatternRecord(
                    pattern_id=f"pat-ro-{uuid.uuid4().hex[:8]}",
                    pattern_type=PatternType.RECURRING_OUTAGE,
                    frequency=count,
                    confidence=min(count / 5.0, 1.0),
                    description=f"Recurring outages on '{target}' ({count} incidents).",
                    affected_resources=[target],
                    first_seen=min(e.timestamp for e in relevant),
                    last_seen=max(e.timestamp for e in relevant),
                ))
        return patterns

    def _detect_manual_interventions(self, events: list[LearningEvent]) -> list[PatternRecord]:
        """Detect repeated manual override patterns.

        Args:
            events: Event history

        Returns:
            List of detected manual intervention patterns
        """
        overrides = [e for e in events if e.event_type == EventType.MANUAL_OVERRIDE]
        if len(overrides) < self.min_occurrences:
            return []

        target_counts: Counter[str] = Counter(e.target_id for e in overrides)
        patterns = []
        for target, count in target_counts.items():
            if count >= self.min_occurrences:
                relevant = [e for e in overrides if e.target_id == target]
                patterns.append(PatternRecord(
                    pattern_id=f"pat-mi-{uuid.uuid4().hex[:8]}",
                    pattern_type=PatternType.MANUAL_INTERVENTION,
                    frequency=count,
                    confidence=min(count / 5.0, 1.0),
                    description=f"Repeated manual interventions on '{target}' ({count} overrides).",
                    affected_resources=[target],
                    first_seen=min(e.timestamp for e in relevant),
                    last_seen=max(e.timestamp for e in relevant),
                ))
        return patterns

    def _detect_growth_trends(self, events: list[LearningEvent]) -> list[PatternRecord]:
        """Detect infrastructure growth trends from scaling events.

        Args:
            events: Event history

        Returns:
            List of detected growth trend patterns
        """
        scaling = [e for e in events if e.event_type == EventType.SCALING]
        if len(scaling) < self.min_occurrences:
            return []

        return [PatternRecord(
            pattern_id=f"pat-gt-{uuid.uuid4().hex[:8]}",
            pattern_type=PatternType.GROWTH_TREND,
            frequency=len(scaling),
            confidence=min(len(scaling) / 10.0, 1.0),
            description=f"Infrastructure scaling trend detected ({len(scaling)} scaling events).",
            affected_resources=list({e.target_id for e in scaling}),
            first_seen=min(e.timestamp for e in scaling),
            last_seen=max(e.timestamp for e in scaling),
        )]

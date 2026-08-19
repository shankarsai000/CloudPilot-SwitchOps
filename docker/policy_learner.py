"""
Policy Learner Component

Discovers organizational best practices from event history:
safe deployment windows, preferred scaling methods, architecture conventions,
team ownership patterns, and maintenance schedules.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from models_learning import EventType, LearningEvent

logger = logging.getLogger(__name__)


class PolicyLearner:
    """Discovers organizational best practices from historical events."""

    def __init__(self) -> None:
        """Initialize Policy Learner."""
        pass

    def discover_best_practices(self, events: list[LearningEvent]) -> dict[str, Any]:
        """Analyze events and extract organizational best practices.

        Args:
            events: Organizational memory events

        Returns:
            Dict containing discovered best practices
        """
        return {
            "safe_deployment_windows": self._discover_safe_windows(events),
            "preferred_scaling_methods": self._discover_scaling_preferences(events),
            "team_ownership_patterns": self._discover_ownership_patterns(events),
            "architecture_conventions": self._discover_architecture_conventions(events),
            "maintenance_schedules": self._discover_maintenance_schedules(events),
        }

    def _discover_safe_windows(self, events: list[LearningEvent]) -> dict[str, Any]:
        """Identify time windows where deployments succeed most often.

        Args:
            events: Event history

        Returns:
            Dict with safe window recommendations
        """
        deployments = [e for e in events if e.event_type == EventType.DEPLOYMENT]
        if not deployments:
            return {"recommendation": "Insufficient data", "safest_hours": "09:00-17:00"}

        # Count successes by hour
        hour_success: Counter[int] = Counter()
        hour_total: Counter[int] = Counter()
        for d in deployments:
            hour = d.timestamp.hour
            hour_total[hour] += 1
            if d.outcome.value == "SUCCESS":
                hour_success[hour] += 1

        # Find hours with highest success rate
        safe_hours = []
        for hour in sorted(hour_total.keys()):
            rate = hour_success[hour] / hour_total[hour] if hour_total[hour] > 0 else 0
            if rate >= 0.8:
                safe_hours.append(hour)

        if safe_hours:
            window = f"{min(safe_hours):02d}:00-{max(safe_hours) + 1:02d}:00"
        else:
            window = "09:00-17:00"

        return {"recommendation": "Deploy during safe windows", "safest_hours": window}

    def _discover_scaling_preferences(self, events: list[LearningEvent]) -> dict[str, Any]:
        """Identify preferred scaling methods from event actors.

        Args:
            events: Event history

        Returns:
            Dict with scaling method preferences
        """
        scaling = [e for e in events if e.event_type == EventType.SCALING]
        if not scaling:
            return {"preferred_method": "manual", "auto_percentage": 0.0}

        auto_count = sum(1 for e in scaling if e.actor in ("CloudPilot-System", "autoscaler"))
        auto_pct = round((auto_count / len(scaling)) * 100.0, 2)
        preferred = "automated" if auto_pct > 50.0 else "manual"

        return {"preferred_method": preferred, "auto_percentage": auto_pct}

    def _discover_ownership_patterns(self, events: list[LearningEvent]) -> dict[str, Any]:
        """Identify which actors are most active on which targets.

        Args:
            events: Event history

        Returns:
            Dict mapping targets to most active actors
        """
        target_actors: dict[str, Counter[str]] = {}
        for e in events:
            if e.target_id not in target_actors:
                target_actors[e.target_id] = Counter()
            target_actors[e.target_id][e.actor] += 1

        ownership: dict[str, str] = {}
        for target, actor_counts in target_actors.items():
            if actor_counts:
                ownership[target] = actor_counts.most_common(1)[0][0]

        return {"target_owners": ownership}

    def _discover_architecture_conventions(self, events: list[LearningEvent]) -> dict[str, Any]:
        """Discover naming conventions and infrastructure patterns.

        Args:
            events: Event history

        Returns:
            Dict with architecture conventions
        """
        targets = [e.target_id for e in events]
        prefixes: Counter[str] = Counter()
        for t in targets:
            parts = t.split("-")
            if len(parts) >= 2:
                prefixes[parts[0]] += 1

        common = prefixes.most_common(5)
        return {"common_prefixes": [p[0] for p in common], "unique_targets": len(set(targets))}

    def _discover_maintenance_schedules(self, events: list[LearningEvent]) -> dict[str, Any]:
        """Discover typical maintenance windows from events.

        Args:
            events: Event history

        Returns:
            Dict with maintenance schedule insights
        """
        maintenance = [
            e for e in events
            if e.event_type in (EventType.INFRASTRUCTURE_CHANGE, EventType.SCALING)
        ]
        if not maintenance:
            return {"typical_window": "weekdays 02:00-06:00", "data_points": 0}

        # Count by day of week
        day_counts: Counter[int] = Counter(e.timestamp.weekday() for e in maintenance)
        most_common_day = day_counts.most_common(1)[0][0] if day_counts else 0
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        return {
            "typical_window": f"{day_names[most_common_day]}s 02:00-06:00",
            "data_points": len(maintenance),
        }

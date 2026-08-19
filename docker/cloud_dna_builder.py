"""
Cloud DNA Builder Component

Analyzes organizational memory events to build and evolve an organization-specific
Cloud DNA profile reflecting deployment style, risk tolerance, scaling patterns,
approval habits, and automation level.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from models_learning import (
    CloudDNAProfile,
    DeploymentStyle,
    EventType,
    LearningEvent,
    OutcomeType,
    RiskToleranceLevel,
    ScalingPattern,
)

logger = logging.getLogger(__name__)


class CloudDNABuilder:
    """Builds and evolves organization-specific Cloud DNA profiles from event history."""

    def __init__(self, organization_id: str = "default-org") -> None:
        """Initialize Cloud DNA Builder.

        Args:
            organization_id: Organization identifier
        """
        self.organization_id = organization_id

    def build_profile(self, events: list[LearningEvent]) -> CloudDNAProfile:
        """Analyze events and construct the current Cloud DNA profile.

        Args:
            events: Organizational memory events

        Returns:
            CloudDNAProfile reflecting organizational behavior
        """
        if not events:
            return CloudDNAProfile(organization_id=self.organization_id)

        deployment_style = self._infer_deployment_style(events)
        risk_tolerance = self._infer_risk_tolerance(events)
        scaling_pattern = self._infer_scaling_pattern(events)
        rollback_freq = self._calculate_rollback_frequency(events)
        automation_level = self._calculate_automation_level(events)
        deploy_freq = self._calculate_deployment_frequency(events)
        approval_time = self._estimate_approval_time(events)

        return CloudDNAProfile(
            organization_id=self.organization_id,
            deployment_style=deployment_style,
            risk_tolerance=risk_tolerance,
            scaling_pattern=scaling_pattern,
            peak_hours="09:00-17:00",
            preferred_regions=["us-east-1"],
            average_approval_time_hours=approval_time,
            rollback_frequency_percentage=rollback_freq,
            automation_level_percentage=automation_level,
            deployment_frequency_per_week=deploy_freq,
            total_events_analyzed=len(events),
            last_updated=datetime.utcnow(),
        )

    def _infer_deployment_style(self, events: list[LearningEvent]) -> DeploymentStyle:
        """Infer deployment style from event patterns.

        Args:
            events: Event history

        Returns:
            DeploymentStyle classification
        """
        deployments = [e for e in events if e.event_type == EventType.DEPLOYMENT]
        if not deployments:
            return DeploymentStyle.MODERATE

        rollbacks = [e for e in events if e.event_type == EventType.ROLLBACK]
        manual_overrides = [e for e in events if e.event_type == EventType.MANUAL_OVERRIDE]

        # Conservative: high rollback ratio or many manual overrides
        rollback_ratio = len(rollbacks) / max(len(deployments), 1)
        override_ratio = len(manual_overrides) / max(len(deployments), 1)

        if rollback_ratio > 0.15 or override_ratio > 0.2:
            return DeploymentStyle.CONSERVATIVE
        elif rollback_ratio < 0.05 and override_ratio < 0.05:
            return DeploymentStyle.AGGRESSIVE
        return DeploymentStyle.MODERATE

    def _infer_risk_tolerance(self, events: list[LearningEvent]) -> RiskToleranceLevel:
        """Infer risk tolerance from failure and incident patterns.

        Args:
            events: Event history

        Returns:
            RiskToleranceLevel classification
        """
        failures = [e for e in events if e.outcome == OutcomeType.FAILURE]
        total = len(events)
        if total == 0:
            return RiskToleranceLevel.MEDIUM

        failure_ratio = len(failures) / total
        if failure_ratio > 0.1:
            return RiskToleranceLevel.LOW
        elif failure_ratio < 0.03:
            return RiskToleranceLevel.HIGH
        return RiskToleranceLevel.MEDIUM

    def _infer_scaling_pattern(self, events: list[LearningEvent]) -> ScalingPattern:
        """Infer scaling behavior from scaling events.

        Args:
            events: Event history

        Returns:
            ScalingPattern classification
        """
        scaling_events = [e for e in events if e.event_type == EventType.SCALING]
        if not scaling_events:
            return ScalingPattern.MANUAL

        auto_count = sum(1 for e in scaling_events if e.actor == "CloudPilot-System" or e.actor == "autoscaler")
        manual_count = len(scaling_events) - auto_count

        if auto_count > manual_count * 2:
            return ScalingPattern.PREDICTIVE
        elif manual_count > auto_count * 2:
            return ScalingPattern.MANUAL
        return ScalingPattern.HYBRID

    def _calculate_rollback_frequency(self, events: list[LearningEvent]) -> float:
        """Calculate rollback frequency as a percentage of deployments.

        Args:
            events: Event history

        Returns:
            Rollback frequency percentage
        """
        deployments = [e for e in events if e.event_type == EventType.DEPLOYMENT]
        rollbacks = [e for e in events if e.event_type == EventType.ROLLBACK]
        if not deployments:
            return 0.0
        return round((len(rollbacks) / len(deployments)) * 100.0, 2)

    def _calculate_automation_level(self, events: list[LearningEvent]) -> float:
        """Calculate automation level as percentage of system-initiated events.

        Args:
            events: Event history

        Returns:
            Automation level percentage
        """
        if not events:
            return 50.0
        automated = sum(1 for e in events if e.actor in ("CloudPilot-System", "autoscaler", "ci-pipeline"))
        return round((automated / len(events)) * 100.0, 2)

    def _calculate_deployment_frequency(self, events: list[LearningEvent]) -> float:
        """Calculate average deployments per week.

        Args:
            events: Event history

        Returns:
            Deployments per week
        """
        deployments = [e for e in events if e.event_type == EventType.DEPLOYMENT]
        if len(deployments) < 2:
            return float(len(deployments))

        sorted_deps = sorted(deployments, key=lambda e: e.timestamp)
        span_days = max((sorted_deps[-1].timestamp - sorted_deps[0].timestamp).total_seconds() / 86400.0, 1.0)
        weeks = max(span_days / 7.0, 1.0)
        return round(len(deployments) / weeks, 2)

    def _estimate_approval_time(self, events: list[LearningEvent]) -> float:
        """Estimate average approval turnaround time in hours.

        Args:
            events: Event history

        Returns:
            Average approval time in hours
        """
        approvals = [e for e in events if e.event_type == EventType.APPROVAL]
        if not approvals:
            return 2.0

        # Use metadata field if available, otherwise default
        times = []
        for a in approvals:
            t = a.metadata.get("approval_time_hours", 2.0)
            times.append(float(t))
        return round(sum(times) / len(times), 2) if times else 2.0

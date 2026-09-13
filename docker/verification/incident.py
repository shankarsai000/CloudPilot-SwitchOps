"""
Post-Execution Incident Detector.

Monitors operational telemetry after execution to detect anomalies:
- Latency spikes (percentage increase or absolute ceiling violation)
- Availability drops (SLO violation)
- CPU starvation / resource exhaustion
- Error rate anomalies

Automatically coordinates with AutomatedRollbackManager when HIGH or CRITICAL incidents occur.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional
import uuid

from verification.models import (
    ActualOutcome,
    ExpectedOutcome,
    IncidentSeverity,
    PostExecutionIncident,
    RollbackResult,
)
from verification.rollback import get_rollback_manager

logger = logging.getLogger(__name__)


class PostExecutionIncidentDetector:
    """
    Detects post-execution incidents and triggers automated emergency rollback when necessary.
    """

    def __init__(self) -> None:
        self._incidents: List[PostExecutionIncident] = []
        self._mutex = threading.Lock()

    def evaluate_telemetry(
        self,
        expected: ExpectedOutcome,
        actual: ActualOutcome,
        auto_rollback_on_critical: bool = True,
    ) -> List[PostExecutionIncident]:
        """
        Evaluate actual telemetry against safety expectations and thresholds.
        Identifies incidents and optionally fires automated rollback for HIGH/CRITICAL issues.
        """
        detected: List[PostExecutionIncident] = []
        t = expected.thresholds
        now = datetime.now(timezone.utc)

        # 1. Latency Spike Check
        if expected.expected_latency_p99_ms > 0:
            lat_pct = ((actual.measured_latency_p99_ms - expected.expected_latency_p99_ms) / expected.expected_latency_p99_ms) * 100.0
        else:
            lat_pct = 0.0

        if actual.measured_latency_p99_ms > t.max_latency_absolute_ms:
            detected.append(
                PostExecutionIncident(
                    incident_id=f"inc-{uuid.uuid4().hex[:8]}",
                    action_id=expected.action_id,
                    target_resource_id=expected.target_resource_id,
                    target_service=expected.target_service,
                    severity=IncidentSeverity.CRITICAL,
                    incident_type="LATENCY_CEILING_BREACH",
                    description=f"p99 latency {actual.measured_latency_p99_ms:.1f}ms exceeds hard ceiling of {t.max_latency_absolute_ms}ms",
                    observed_metric="latency_p99_ms",
                    observed_value=actual.measured_latency_p99_ms,
                    threshold_value=t.max_latency_absolute_ms,
                    detected_at=now,
                )
            )
        elif lat_pct > t.max_latency_increase_pct:
            sev = IncidentSeverity.HIGH if lat_pct > (t.max_latency_increase_pct * 2.0) else IncidentSeverity.MEDIUM
            detected.append(
                PostExecutionIncident(
                    incident_id=f"inc-{uuid.uuid4().hex[:8]}",
                    action_id=expected.action_id,
                    target_resource_id=expected.target_resource_id,
                    target_service=expected.target_service,
                    severity=sev,
                    incident_type="LATENCY_SPIKE",
                    description=f"p99 latency increased by {lat_pct:.1f}% (threshold: {t.max_latency_increase_pct}%)",
                    observed_metric="latency_p99_pct_increase",
                    observed_value=lat_pct,
                    threshold_value=t.max_latency_increase_pct,
                    detected_at=now,
                )
            )

        # 2. Availability Drop Check
        if actual.measured_availability_pct < t.min_availability_pct:
            drop = expected.expected_availability_pct - actual.measured_availability_pct
            sev = IncidentSeverity.CRITICAL if drop > 0.5 else IncidentSeverity.HIGH
            detected.append(
                PostExecutionIncident(
                    incident_id=f"inc-{uuid.uuid4().hex[:8]}",
                    action_id=expected.action_id,
                    target_resource_id=expected.target_resource_id,
                    target_service=expected.target_service,
                    severity=sev,
                    incident_type="AVAILABILITY_DROP",
                    description=f"Availability {actual.measured_availability_pct:.2f}% breached minimum SLO {t.min_availability_pct}%",
                    observed_metric="availability_pct",
                    observed_value=actual.measured_availability_pct,
                    threshold_value=t.min_availability_pct,
                    detected_at=now,
                )
            )

        # 3. CPU Starvation Check
        if actual.measured_cpu_utilization_pct > t.max_cpu_utilization_pct:
            sev = IncidentSeverity.CRITICAL if actual.measured_cpu_utilization_pct >= 95.0 else IncidentSeverity.HIGH
            detected.append(
                PostExecutionIncident(
                    incident_id=f"inc-{uuid.uuid4().hex[:8]}",
                    action_id=expected.action_id,
                    target_resource_id=expected.target_resource_id,
                    target_service=expected.target_service,
                    severity=sev,
                    incident_type="CPU_STARVATION",
                    description=f"CPU utilization {actual.measured_cpu_utilization_pct:.1f}% exceeded safety limit {t.max_cpu_utilization_pct}%",
                    observed_metric="cpu_utilization_pct",
                    observed_value=actual.measured_cpu_utilization_pct,
                    threshold_value=t.max_cpu_utilization_pct,
                    detected_at=now,
                )
            )

        # 4. Error Rate Spike Check
        if actual.measured_error_rate_pct > 2.0:
            detected.append(
                PostExecutionIncident(
                    incident_id=f"inc-{uuid.uuid4().hex[:8]}",
                    action_id=expected.action_id,
                    target_resource_id=expected.target_resource_id,
                    target_service=expected.target_service,
                    severity=IncidentSeverity.HIGH if actual.measured_error_rate_pct > 5.0 else IncidentSeverity.MEDIUM,
                    incident_type="ERROR_RATE_SPIKE",
                    description=f"Error rate {actual.measured_error_rate_pct:.2f}% exceeded 2.0% threshold",
                    observed_metric="error_rate_pct",
                    observed_value=actual.measured_error_rate_pct,
                    threshold_value=2.0,
                    detected_at=now,
                )
            )

        # 5. Automated Rollback Trigger for HIGH or CRITICAL incidents
        requires_rollback = any(inc.severity in (IncidentSeverity.HIGH, IncidentSeverity.CRITICAL) for inc in detected)
        if requires_rollback and auto_rollback_on_critical:
            rollback_mgr = get_rollback_manager()
            plan = rollback_mgr.generate_rollback_plan(
                action_id=expected.action_id,
                target_resource_id=expected.target_resource_id,
                original_action_type="rightsize_instance",
                original_parameters={"source_type": "t3.large", "target_type": "t3.small"},
            )
            rollback_mgr.execute_rollback(
                plan=plan,
                actor="PostExecutionIncidentDetector",
                reason=f"Automated incident rollback triggered: {len(detected)} safety anomalies detected",
            )
            for inc in detected:
                inc.triggered_rollback = True

        with self._mutex:
            self._incidents.extend(detected)

        return detected

    def list_incidents(self) -> List[PostExecutionIncident]:
        with self._mutex:
            return sorted(self._incidents, key=lambda inc: inc.detected_at, reverse=True)

    def get_incidents_for_action(self, action_id: str) -> List[PostExecutionIncident]:
        with self._mutex:
            return [inc for inc in self._incidents if inc.action_id == action_id]

    def clear_all(self) -> None:
        with self._mutex:
            self._incidents.clear()


_incident_detector_instance: Optional[PostExecutionIncidentDetector] = None


def get_incident_detector() -> PostExecutionIncidentDetector:
    global _incident_detector_instance
    if _incident_detector_instance is None:
        _incident_detector_instance = PostExecutionIncidentDetector()
    return _incident_detector_instance

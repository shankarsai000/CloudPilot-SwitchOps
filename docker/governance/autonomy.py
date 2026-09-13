"""
Progressive Autonomy Level Manager & Automatic Demotion Engine.

Enforces L0 to L5 operational bounds and executes automated demotions upon:
- Confidence degradation
- Consecutive execution failures
- Rollback frequency spikes
- Critical policy violations
- Anomaly / unexpected behavior detection
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import logging
import threading
from typing import Deque, Dict, List, Optional, Tuple

from governance.models import (
    AutonomyLevel,
    DemotionReason,
    DemotionTrigger,
)

logger = logging.getLogger(__name__)


class DemotionController:
    """
    Monitors telemetry and health metrics to automatically demote autonomy levels.
    """

    def __init__(
        self,
        confidence_threshold: float = 75.0,
        max_consecutive_failures: int = 3,
        max_rollback_rate: float = 0.15,
        window_size: int = 20,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.max_consecutive_failures = max_consecutive_failures
        self.max_rollback_rate = max_rollback_rate
        self.window_size = window_size

        self._consecutive_failures = 0
        self._recent_confidences: Deque[float] = deque(maxlen=window_size)
        self._recent_outcomes: Deque[str] = deque(maxlen=window_size)  # "SUCCESS", "FAILURE", "ROLLBACK"
        self._demotion_history: List[DemotionTrigger] = []
        self._mutex = threading.Lock()

    def record_success(self, confidence_score: float) -> None:
        with self._mutex:
            self._consecutive_failures = 0
            self._recent_confidences.append(confidence_score)
            self._recent_outcomes.append("SUCCESS")

    def record_failure(self, reason: str) -> None:
        with self._mutex:
            self._consecutive_failures += 1
            self._recent_outcomes.append("FAILURE")

    def record_rollback(self) -> None:
        with self._mutex:
            self._recent_outcomes.append("ROLLBACK")

    def check_demotion_condition(
        self,
        current_level: AutonomyLevel,
    ) -> Optional[Tuple[DemotionReason, AutonomyLevel, str, Dict[str, Any]]]:
        """
        Evaluate if current metrics trigger an automatic autonomy demotion.
        Returns (reason, target_demoted_level, description, metrics_snapshot) or None.
        """
        with self._mutex:
            # Cannot demote below L0
            if current_level == AutonomyLevel.L0_OBSERVE:
                return None

            # 1. Consecutive failures trigger
            if self._consecutive_failures >= self.max_consecutive_failures:
                new_level = AutonomyLevel.L2_SIMULATE if current_level in (AutonomyLevel.L4_LIMITED, AutonomyLevel.L5_FULL) else AutonomyLevel.L1_RECOMMEND
                details = f"Consecutive failures ({self._consecutive_failures}) reached threshold ({self.max_consecutive_failures})"
                snapshot = {"consecutive_failures": self._consecutive_failures}
                return DemotionReason.REPEATED_FAILURES, new_level, details, snapshot

            # 2. Confidence degradation trigger (if we have at least 3 recent observations)
            if len(self._recent_confidences) >= 3:
                avg_conf = sum(self._recent_confidences) / len(self._recent_confidences)
                if avg_conf < self.confidence_threshold:
                    new_level = AutonomyLevel.L3_APPROVAL if current_level in (AutonomyLevel.L4_LIMITED, AutonomyLevel.L5_FULL) else AutonomyLevel.L1_RECOMMEND
                    details = f"Average confidence ({avg_conf:.1f}%) dropped below threshold ({self.confidence_threshold:.1f}%)"
                    snapshot = {"average_confidence": avg_conf, "recent_count": len(self._recent_confidences)}
                    return DemotionReason.CONFIDENCE_DECREASED, new_level, details, snapshot

            # 3. Rollback frequency spike trigger (if we have at least 5 outcomes)
            if len(self._recent_outcomes) >= 5:
                rollbacks = sum(1 for o in self._recent_outcomes if o == "ROLLBACK")
                rate = rollbacks / len(self._recent_outcomes)
                if rate > self.max_rollback_rate:
                    new_level = AutonomyLevel.L3_APPROVAL if current_level in (AutonomyLevel.L4_LIMITED, AutonomyLevel.L5_FULL) else AutonomyLevel.L1_RECOMMEND
                    details = f"Rollback rate ({rate:.1%}) exceeded threshold ({self.max_rollback_rate:.1%})"
                    snapshot = {"rollback_rate": rate, "rollbacks_count": rollbacks}
                    return DemotionReason.ROLLBACK_SPIKE, new_level, details, snapshot

            return None

    def record_demotion_event(self, trigger: DemotionTrigger) -> None:
        with self._mutex:
            self._demotion_history.append(trigger)

    def get_demotion_history(self) -> List[DemotionTrigger]:
        with self._mutex:
            return list(self._demotion_history)

    def reset_metrics(self) -> None:
        with self._mutex:
            self._consecutive_failures = 0
            self._recent_confidences.clear()
            self._recent_outcomes.clear()


class AutonomyLevelManager:
    """
    Manages global or environment-level progressive autonomy.
    Provides automated demotion enforcement and authorized promotion gates.
    """

    def __init__(
        self,
        initial_level: AutonomyLevel = AutonomyLevel.L3_APPROVAL,
        demotion_controller: Optional[DemotionController] = None,
    ) -> None:
        self._current_level = initial_level
        self.demotion_controller = demotion_controller or DemotionController()
        self._mutex = threading.Lock()

    def get_level(self) -> AutonomyLevel:
        """Return the current active autonomy level."""
        with self._mutex:
            return self._current_level

    def set_level(
        self,
        new_level: AutonomyLevel,
        actor: str = "operator",
        reason: str = "Manual configuration update",
    ) -> AutonomyLevel:
        """
        Promote or demote autonomy level explicitly by an authorized operator.
        """
        with self._mutex:
            old_level = self._current_level
            self._current_level = new_level
            # When an operator explicitly resets or sets level, reset failure streaks
            self.demotion_controller.reset_metrics()
            logger.info(
                "Autonomy level changed from %s to %s by %s. Reason: %s",
                old_level.value, new_level.value, actor, reason,
            )
            return self._current_level

    def check_and_apply_automatic_demotion(self) -> Optional[DemotionTrigger]:
        """
        Check if telemetry metrics warrant an automatic demotion and apply it.
        """
        with self._mutex:
            condition = self.demotion_controller.check_demotion_condition(self._current_level)
            if not condition:
                return None

            reason, new_level, details, snapshot = condition
            old_level = self._current_level
            self._current_level = new_level

            trigger = DemotionTrigger(
                reason=reason,
                previous_level=old_level,
                new_level=new_level,
                details=details,
                metrics_snapshot=snapshot,
                triggered_at=datetime.now(timezone.utc),
            )
            self.demotion_controller.record_demotion_event(trigger)
            logger.warning(
                "AUTOMATIC AUTONOMY DEMOTION: Demoted from %s to %s. Trigger: %s (%s)",
                old_level.value, new_level.value, reason.value, details,
            )
            return trigger

    def trigger_policy_violation_demotion(self, violation: str) -> DemotionTrigger:
        """
        Immediately demote autonomy when a severe policy violation is attempted.
        """
        with self._mutex:
            old_level = self._current_level
            new_level = AutonomyLevel.L2_SIMULATE if old_level in (AutonomyLevel.L4_LIMITED, AutonomyLevel.L5_FULL) else AutonomyLevel.L1_RECOMMEND
            self._current_level = new_level

            trigger = DemotionTrigger(
                reason=DemotionReason.POLICY_VIOLATION,
                previous_level=old_level,
                new_level=new_level,
                details=f"Policy violation detected: {violation}",
                metrics_snapshot={"violation": violation},
                triggered_at=datetime.now(timezone.utc),
            )
            self.demotion_controller.record_demotion_event(trigger)
            logger.error(
                "AUTOMATIC DEMOTION TRIGGERED BY POLICY VIOLATION: Demoted from %s to %s",
                old_level.value, new_level.value,
            )
            return trigger

    def trigger_anomaly_demotion(self, details: str) -> DemotionTrigger:
        """
        Immediately demote autonomy when unexpected behavior or an anomaly is detected.
        """
        with self._mutex:
            old_level = self._current_level
            new_level = AutonomyLevel.L2_SIMULATE
            self._current_level = new_level

            trigger = DemotionTrigger(
                reason=DemotionReason.UNEXPECTED_BEHAVIOR,
                previous_level=old_level,
                new_level=new_level,
                details=f"Unexpected behavior detected: {details}",
                metrics_snapshot={"details": details},
                triggered_at=datetime.now(timezone.utc),
            )
            self.demotion_controller.record_demotion_event(trigger)
            return trigger


_autonomy_manager_instance: Optional[AutonomyLevelManager] = None


def get_autonomy_manager() -> AutonomyLevelManager:
    global _autonomy_manager_instance
    if _autonomy_manager_instance is None:
        _autonomy_manager_instance = AutonomyLevelManager()
    return _autonomy_manager_instance

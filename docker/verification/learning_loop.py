"""
CloudPilot Verification & M8 Learning Loop Bridge.

Connects post-execution outcome verification, incident detection, rollbacks,
and human overrides back into M8 (LearningAgent, LearningEngine, CloudDNA, ExperienceReplay).

Guarantees:
1. Continuous learning from:
   - Successful actions
   - Failed actions
   - Rollbacks
   - Human overrides
   - Rejected recommendations
   - Unexpected outcomes
2. Cloud DNA evolution (deployment style, risk tolerance, rollback frequency, automation level)
3. Experience replay retrieval before generating new recommendations
4. Multi-dimensional learning metrics (accuracy, calibration, savings prediction)
5. Safety Precedence Guard: Learning confidence strictly NEVER bypasses safety policies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional
import uuid

from governance.control_plane import SafetyControlPlane, get_safety_control_plane
from governance.models import ProposedAction
from learning_agent import LearningAgent
from models_learning import (
    CloudDNAProfile,
    EventType,
    ExperienceRecord,
    FeedbackVerdict,
    LearningEvent,
    LearningMetrics,
    OutcomeType,
)
from verification.models import (
    LearningUpdateReport,
    OutcomeReport,
    OutcomeVerdict,
    PostExecutionIncident,
)

logger = logging.getLogger(__name__)


_shared_learning_agent: Optional[LearningAgent] = None


def get_shared_learning_agent() -> LearningAgent:
    global _shared_learning_agent
    if _shared_learning_agent is None:
        _shared_learning_agent = LearningAgent(organization_id="cloudpilot-org")
    return _shared_learning_agent


class LearningLoopBridge:
    """
    Orchestrates the bidirectional bridge between post-execution outcomes and M8 Organizational Intelligence.
    """

    def __init__(
        self,
        learning_agent: Optional[LearningAgent] = None,
        control_plane: Optional[SafetyControlPlane] = None,
    ) -> None:
        self.learning_agent = learning_agent or get_shared_learning_agent()
        self.control_plane = control_plane or get_safety_control_plane()
        self._reports: List[LearningUpdateReport] = []
        self._history_outcomes: List[OutcomeReport] = []
        self._mutex = threading.Lock()

    # -------------------------------------------------------------------------
    # 1. Outcome Ingestion into M8
    # -------------------------------------------------------------------------

    def ingest_outcome(
        self,
        report: OutcomeReport,
        actor: str = "VerificationEngine",
    ) -> LearningUpdateReport:
        """
        Ingest a verified outcome report into M8 learning pipeline.
        Updates organizational memory, experience replay, and triggers Cloud DNA re-evaluation.
        """
        now = datetime.now(timezone.utc)

        # Map OutcomeVerdict to EventType and OutcomeType
        if report.verdict == OutcomeVerdict.VERIFIED_SUCCESS:
            ev_type = EventType.OPTIMIZATION
            out_type = OutcomeType.SUCCESS
            reward = 1.0
        elif report.verdict == OutcomeVerdict.ACCEPTABLE_DEVIATION:
            ev_type = EventType.OPTIMIZATION
            out_type = OutcomeType.PARTIAL
            reward = 0.5
        elif report.verdict == OutcomeVerdict.ROLLED_BACK:
            ev_type = EventType.ROLLBACK
            out_type = OutcomeType.ROLLBACK
            reward = -1.5
        else:  # THRESHOLD_BREACH, EXECUTION_FAILED
            ev_type = EventType.FAILURE
            out_type = OutcomeType.FAILURE
            reward = -1.0

        # Create Learning Event
        event = LearningEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            event_type=ev_type,
            target_id=report.target_resource_id,
            action=report.expected.target_service,
            outcome=out_type,
            actor=actor,
            metadata={
                "action_id": report.action_id,
                "cost_variance_pct": report.cost_variance_pct,
                "savings_realization_rate": report.savings_realization_rate,
                "latency_increase_pct": report.latency_increase_pct,
                "verdict": report.verdict.value,
                "breaches": report.breached_thresholds,
            },
            timestamp=datetime.utcnow(),
        )

        # Ingest into M8
        self.learning_agent.ingest_event(event)

        # Record Experience for Experience Replay
        self.learning_agent.learning_engine.experience_replay.record_experience(
            context={
                "action_id": report.action_id,
                "target_service": report.expected.target_service,
                "baseline_cost": report.expected.baseline_monthly_cost_usd,
                "expected_risk": report.expected.expected_risk_level,
                "environment": "production",
            },
            decision=f"Optimize {report.expected.target_service}",
            action=report.expected.target_service,
            outcome=out_type,
            confidence=85.0 if out_type == OutcomeType.SUCCESS else 40.0,
            actual_savings=report.actual.measured_savings_usd,
        )

        # Trigger Cloud DNA Evolution
        dna = self.learning_agent.get_cloud_dna()
        evolved_conf = self.learning_agent.get_evolved_confidence(report.expected.target_service, 50.0)

        update_report = LearningUpdateReport(
            update_id=f"lup-{uuid.uuid4().hex[:8]}",
            action_id=report.action_id,
            event_type=ev_type.value,
            outcome_type=out_type.value,
            confidence_delta=round(evolved_conf - 50.0, 2),
            cloud_dna_version=f"{dna.deployment_style.value}_{dna.risk_tolerance.value}",
            updated_metrics={
                "rollback_frequency": dna.rollback_frequency_percentage,
                "automation_level": dna.automation_level_percentage,
                "evolved_confidence": evolved_conf,
            },
            ingested_at=now,
        )

        with self._mutex:
            self._reports.append(update_report)
            self._history_outcomes.append(report)

        logger.info(
            "Ingested outcome for action %s: verdict=%s, cloud_dna=%s",
            report.action_id,
            report.verdict.value,
            update_report.cloud_dna_version,
        )
        return update_report

    def ingest_human_override(
        self,
        action_id: str,
        target_resource_id: str,
        action: str,
        approver: str,
        override_reason: str,
    ) -> LearningUpdateReport:
        """
        Record a human operator overriding an autonomous recommendation.
        Updates M8 feedback and organizational memory.
        """
        event = LearningEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            event_type=EventType.MANUAL_OVERRIDE,
            target_id=target_resource_id,
            action=action,
            outcome=OutcomeType.SUCCESS,
            actor=approver,
            metadata={"action_id": action_id, "reason": override_reason},
            timestamp=datetime.utcnow(),
        )
        self.learning_agent.ingest_event(event)

        # Submit Feedback to M8 FeedbackEngine
        self.learning_agent.submit_feedback(
            decision_id=action_id,
            source=approver,
            verdict=FeedbackVerdict.MODIFIED,
            reason=override_reason,
            tags=["manual_override"],
        )

        dna = self.learning_agent.get_cloud_dna()
        now = datetime.now(timezone.utc)

        update_report = LearningUpdateReport(
            update_id=f"lup-{uuid.uuid4().hex[:8]}",
            action_id=action_id,
            event_type=EventType.MANUAL_OVERRIDE.value,
            outcome_type=OutcomeType.SUCCESS.value,
            confidence_delta=-5.0,  # Manual override adjusts confidence conservatively
            cloud_dna_version=f"{dna.deployment_style.value}_{dna.risk_tolerance.value}",
            updated_metrics={
                "rollback_frequency": dna.rollback_frequency_percentage,
                "automation_level": dna.automation_level_percentage,
            },
            ingested_at=now,
        )
        with self._mutex:
            self._reports.append(update_report)
        return update_report

    def ingest_rejection(
        self,
        action_id: str,
        target_resource_id: str,
        action: str,
        rejected_by: str,
        rejection_reason: str,
    ) -> LearningUpdateReport:
        """
        Record human rejection of a recommendation before execution.
        """
        event = LearningEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            event_type=EventType.REJECTION,
            target_id=target_resource_id,
            action=action,
            outcome=OutcomeType.FAILURE,
            actor=rejected_by,
            metadata={"action_id": action_id, "reason": rejection_reason},
            timestamp=datetime.utcnow(),
        )
        self.learning_agent.ingest_event(event)

        self.learning_agent.submit_feedback(
            decision_id=action_id,
            source=rejected_by,
            verdict=FeedbackVerdict.REJECTED,
            reason=rejection_reason,
            tags=["rejected"],
        )

        dna = self.learning_agent.get_cloud_dna()
        now = datetime.now(timezone.utc)

        update_report = LearningUpdateReport(
            update_id=f"lup-{uuid.uuid4().hex[:8]}",
            action_id=action_id,
            event_type=EventType.REJECTION.value,
            outcome_type=OutcomeType.FAILURE.value,
            confidence_delta=-10.0,
            cloud_dna_version=f"{dna.deployment_style.value}_{dna.risk_tolerance.value}",
            updated_metrics={
                "rollback_frequency": dna.rollback_frequency_percentage,
                "automation_level": dna.automation_level_percentage,
            },
            ingested_at=now,
        )
        with self._mutex:
            self._reports.append(update_report)
        return update_report

    def ingest_incident(
        self,
        incident: PostExecutionIncident,
    ) -> LearningUpdateReport:
        """
        Record a post-execution operational incident into M8.
        """
        event = LearningEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            event_type=EventType.INCIDENT,
            target_id=incident.target_resource_id,
            action=incident.incident_type,
            outcome=OutcomeType.FAILURE,
            actor="IncidentDetector",
            metadata={
                "action_id": incident.action_id,
                "severity": incident.severity.value,
                "metric": incident.observed_metric,
                "observed": incident.observed_value,
                "threshold": incident.threshold_value,
            },
            timestamp=datetime.utcnow(),
        )
        self.learning_agent.ingest_event(event)
        dna = self.learning_agent.get_cloud_dna()
        now = datetime.now(timezone.utc)

        update_report = LearningUpdateReport(
            update_id=f"lup-{uuid.uuid4().hex[:8]}",
            action_id=incident.action_id,
            event_type=EventType.INCIDENT.value,
            outcome_type=OutcomeType.FAILURE.value,
            confidence_delta=-15.0,
            cloud_dna_version=f"{dna.deployment_style.value}_{dna.risk_tolerance.value}",
            updated_metrics={
                "rollback_frequency": dna.rollback_frequency_percentage,
                "automation_level": dna.automation_level_percentage,
            },
            ingested_at=now,
        )
        with self._mutex:
            self._reports.append(update_report)
        return update_report

    # -------------------------------------------------------------------------
    # 2. Experience Replay Retrieval
    # -------------------------------------------------------------------------

    def retrieve_experience_priors(
        self,
        context: Dict[str, Any],
        top_k: int = 5,
    ) -> List[ExperienceRecord]:
        """
        Retrieve relevant historical decisions and prior outcomes before proposing new actions.
        """
        return self.learning_agent.find_similar_experiences(context, top_k=top_k)

    # -------------------------------------------------------------------------
    # 3. Learning & Continuous Improvement Metrics
    # -------------------------------------------------------------------------

    def get_continuous_improvement_metrics(self) -> Dict[str, Any]:
        """
        Measure whether learning improves recommendation accuracy, risk prediction,
        savings prediction, and decision quality.
        """
        m8_metrics = self.learning_agent.get_metrics()
        dna = self.learning_agent.get_cloud_dna()

        with self._mutex:
            outcomes = list(self._history_outcomes)

        # Calculate savings prediction accuracy across outcomes
        if outcomes:
            accuracy_scores = []
            for out in outcomes:
                pred = out.expected.expected_monthly_savings_usd
                act = out.actual.measured_savings_usd
                if pred > 0:
                    err = abs(act - pred) / pred
                    score = max(0.0, 1.0 - err) * 100.0
                    accuracy_scores.append(score)
            savings_accuracy = round(sum(accuracy_scores) / len(accuracy_scores), 2) if accuracy_scores else 100.0
        else:
            savings_accuracy = 100.0

        return {
            "execution_success_rate_pct": round(m8_metrics.execution_success_rate * 100.0, 2),
            "recommendation_acceptance_rate_pct": round(m8_metrics.recommendation_acceptance_rate * 100.0, 2),
            "savings_prediction_accuracy_pct": savings_accuracy,
            "total_events_processed": m8_metrics.total_events_processed,
            "total_experiences_stored": self.learning_agent.learning_engine.experience_replay.count_experiences(),
            "cloud_dna": {
                "deployment_style": dna.deployment_style.value,
                "risk_tolerance": dna.risk_tolerance.value,
                "rollback_frequency_pct": dna.rollback_frequency_percentage,
                "automation_level_pct": dna.automation_level_percentage,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------------
    # 4. Safety Precedence Guard
    # -------------------------------------------------------------------------

    def verify_governance_authority(
        self,
        action: ProposedAction,
        evolved_confidence: float = 99.0,
        evidence: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Safety Precedence Guard:
        Guarantees that learning (M8) NEVER directly bypasses safety policies.
        Governance (Phase 5) remains authoritative.
        """
        is_authorized, reason, evaluation = self.control_plane.authorize_execution(
            action=action,
            evidence=evidence,
            context=context,
        )

        return {
            "governance_authorized": is_authorized,
            "governance_verdict_reason": reason,
            "action_id": action.action_id,
            "risk_level": evaluation.risk_level.value,
            "reversibility": evaluation.reversibility.value,
            "learning_evolved_confidence": evolved_confidence,
            "learning_bypassed_safety": False,  # Mathematically guaranteed False
            "authoritative_verdict": "AUTHORIZED" if is_authorized else "DENIED_BY_SAFETY_GOVERNANCE",
        }

    def clear_all(self) -> None:
        with self._mutex:
            self._reports.clear()
            self._history_outcomes.clear()


_learning_loop_bridge_instance: Optional[LearningLoopBridge] = None


def get_learning_loop_bridge() -> LearningLoopBridge:
    global _learning_loop_bridge_instance
    if _learning_loop_bridge_instance is None:
        _learning_loop_bridge_instance = LearningLoopBridge()
    return _learning_loop_bridge_instance

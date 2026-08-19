"""
Feedback Engine Component

Collects and processes human feedback from engineers, SRE teams,
operators, and approval workflows to improve future recommendations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from models_learning import FeedbackRecord, FeedbackVerdict

logger = logging.getLogger(__name__)


class FeedbackEngine:
    """Processes human feedback on recommendations and decisions."""

    def __init__(self) -> None:
        """Initialize Feedback Engine."""
        self._feedback_store: list[FeedbackRecord] = []

    def submit_feedback(
        self,
        decision_id: str,
        source: str,
        verdict: FeedbackVerdict,
        reason: str = "",
        tags: list[str] = None,
    ) -> FeedbackRecord:
        """Record human feedback for a recommendation.

        Args:
            decision_id: Decision being reviewed
            source: Who provided feedback
            verdict: Approval status
            reason: Free-text explanation
            tags: Categorization tags

        Returns:
            Created FeedbackRecord
        """
        record = FeedbackRecord(
            feedback_id=f"fb-{uuid.uuid4().hex[:10]}",
            decision_id=decision_id,
            source=source,
            verdict=verdict,
            reason=reason,
            tags=tags or [],
            timestamp=datetime.utcnow(),
        )
        self._feedback_store.append(record)
        logger.info(
            "Feedback recorded: %s by %s on decision %s (%s)",
            record.feedback_id, source, decision_id, verdict.value,
        )
        return record

    def get_feedback_for_decision(self, decision_id: str) -> list[FeedbackRecord]:
        """Get all feedback for a specific decision.

        Args:
            decision_id: Decision identifier

        Returns:
            List of FeedbackRecord instances
        """
        return [f for f in self._feedback_store if f.decision_id == decision_id]

    def get_all_feedback(self) -> list[FeedbackRecord]:
        """Return all collected feedback records.

        Returns:
            All FeedbackRecord instances
        """
        return list(self._feedback_store)

    def calculate_acceptance_rate(self) -> float:
        """Calculate overall recommendation acceptance rate.

        Returns:
            Acceptance rate between 0.0 and 1.0
        """
        if not self._feedback_store:
            return 0.0
        approved = sum(1 for f in self._feedback_store if f.verdict == FeedbackVerdict.APPROVED)
        return round(approved / len(self._feedback_store), 4)

    def get_rejection_reasons(self) -> list[str]:
        """Collect all rejection reasons for analysis.

        Returns:
            List of rejection reason strings
        """
        return [
            f.reason
            for f in self._feedback_store
            if f.verdict == FeedbackVerdict.REJECTED and f.reason
        ]

    def count_feedback(self) -> int:
        """Return total feedback count.

        Returns:
            Total number of feedback records
        """
        return len(self._feedback_store)

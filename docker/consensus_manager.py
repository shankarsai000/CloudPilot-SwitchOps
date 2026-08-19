"""
Consensus Manager Component

Collects votes from intelligence modules and aggregates them into a
ConsensusResult with classification: UNANIMOUS, MAJORITY, SPLIT, or DEADLOCK.
"""

from __future__ import annotations

import logging
from typing import Any

from models_decision import AgentVote, ConsensusResult, VoteVerdict

logger = logging.getLogger(__name__)


class ConsensusManager:
    """Aggregates multi-agent votes into a consensus outcome."""

    def __init__(self) -> None:
        """Initialize Consensus Manager."""
        pass

    def aggregate_votes(self, votes: list[AgentVote]) -> ConsensusResult:
        """Collect and aggregate votes from all intelligence modules.

        Args:
            votes: List of AgentVote from each module

        Returns:
            ConsensusResult with classification and recommended action
        """
        approve_count = sum(1 for v in votes if v.verdict == VoteVerdict.APPROVE)
        reject_count = sum(1 for v in votes if v.verdict == VoteVerdict.REJECT)
        abstain_count = sum(1 for v in votes if v.verdict == VoteVerdict.ABSTAIN)
        conditional_count = sum(1 for v in votes if v.verdict == VoteVerdict.CONDITIONAL)

        total_voting = approve_count + reject_count + conditional_count
        consensus_type = self._classify_consensus(approve_count, reject_count, conditional_count, total_voting)
        recommended = self._determine_recommendation(approve_count, reject_count, conditional_count, total_voting)

        result = ConsensusResult(
            votes=votes,
            approve_count=approve_count,
            reject_count=reject_count,
            abstain_count=abstain_count,
            conditional_count=conditional_count,
            consensus_type=consensus_type,
            recommended_action=recommended,
        )

        logger.info(
            "Consensus: %s (approve=%d, reject=%d, conditional=%d, abstain=%d)",
            consensus_type, approve_count, reject_count, conditional_count, abstain_count,
        )
        return result

    def _classify_consensus(
        self, approve: int, reject: int, conditional: int, total: int
    ) -> str:
        """Classify the consensus type.

        Args:
            approve: Approve vote count
            reject: Reject vote count
            conditional: Conditional vote count
            total: Total non-abstain votes

        Returns:
            Consensus classification string
        """
        if total == 0:
            return "DEADLOCK"
        if approve == total:
            return "UNANIMOUS"
        if reject == total:
            return "UNANIMOUS"
        if approve > total / 2:
            return "MAJORITY"
        if reject > total / 2:
            return "MAJORITY"
        return "SPLIT"

    def _determine_recommendation(
        self, approve: int, reject: int, conditional: int, total: int
    ) -> VoteVerdict:
        """Determine the recommended action from vote counts.

        Args:
            approve: Approve vote count
            reject: Reject vote count
            conditional: Conditional vote count
            total: Total non-abstain votes

        Returns:
            Recommended VoteVerdict
        """
        if total == 0:
            return VoteVerdict.ABSTAIN
        if reject > approve:
            return VoteVerdict.REJECT
        if approve > reject:
            if conditional > 0:
                return VoteVerdict.CONDITIONAL
            return VoteVerdict.APPROVE
        return VoteVerdict.CONDITIONAL

"""
Conflict Resolver Component

Detects and resolves conflicting recommendations from intelligence modules.
Supports multiple resolution strategies: risk-priority, cost-priority,
conservative, and majority-wins.
"""

from __future__ import annotations

import logging
from typing import Any

from models_decision import (
    AgentVote,
    ConflictResolutionStrategy,
    ConsensusResult,
    DecisionState,
    VoteVerdict,
)

logger = logging.getLogger(__name__)


class ConflictResolver:
    """Resolves conflicting module recommendations."""

    def __init__(
        self, strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.CONSERVATIVE
    ) -> None:
        """Initialize Conflict Resolver.

        Args:
            strategy: Default resolution strategy
        """
        self.strategy = strategy

    def has_conflict(self, consensus: ConsensusResult) -> bool:
        """Determine if there is a conflict in the consensus.

        Args:
            consensus: Aggregated consensus result

        Returns:
            True if conflicting votes exist
        """
        return consensus.approve_count > 0 and consensus.reject_count > 0

    def resolve(
        self,
        consensus: ConsensusResult,
        strategy: ConflictResolutionStrategy = None,
    ) -> tuple[DecisionState, str]:
        """Resolve a conflict and determine the decision state.

        Args:
            consensus: Aggregated consensus result
            strategy: Override resolution strategy (optional)

        Returns:
            Tuple of (DecisionState, explanation)
        """
        strat = strategy or self.strategy

        if not self.has_conflict(consensus):
            if consensus.recommended_action == VoteVerdict.APPROVE:
                return DecisionState.APPROVED, "No conflict detected. All non-abstaining modules approve."
            elif consensus.recommended_action == VoteVerdict.REJECT:
                return DecisionState.REJECTED, "No conflict detected. Modules recommend rejection."
            return DecisionState.PENDING, "No clear recommendation from modules."

        # Conflict exists — apply resolution strategy
        if strat == ConflictResolutionStrategy.RISK_PRIORITY:
            return self._resolve_risk_priority(consensus)
        elif strat == ConflictResolutionStrategy.COST_PRIORITY:
            return self._resolve_cost_priority(consensus)
        elif strat == ConflictResolutionStrategy.MAJORITY_WINS:
            return self._resolve_majority(consensus)
        else:
            return self._resolve_conservative(consensus)

    def _resolve_risk_priority(self, consensus: ConsensusResult) -> tuple[DecisionState, str]:
        """Risk module gets veto power.

        Args:
            consensus: Consensus result

        Returns:
            Resolved (DecisionState, explanation)
        """
        risk_vote = next((v for v in consensus.votes if v.agent_name == "Risk"), None)
        if risk_vote and risk_vote.verdict == VoteVerdict.REJECT:
            return (
                DecisionState.REQUIRES_APPROVAL,
                f"Conflict resolved via RISK_PRIORITY: Risk module rejects ({risk_vote.reasoning}). Human approval required.",
            )
        return (
            DecisionState.CONDITIONAL,
            "Conflict exists but Risk module does not reject. Conditional approval granted.",
        )

    def _resolve_cost_priority(self, consensus: ConsensusResult) -> tuple[DecisionState, str]:
        """Cost savings override if risk is not critical.

        Args:
            consensus: Consensus result

        Returns:
            Resolved (DecisionState, explanation)
        """
        cost_vote = next((v for v in consensus.votes if v.agent_name == "Cost"), None)
        risk_vote = next((v for v in consensus.votes if v.agent_name == "Risk"), None)

        if risk_vote and risk_vote.confidence > 80.0 and risk_vote.verdict == VoteVerdict.REJECT:
            return (
                DecisionState.BLOCKED,
                "Conflict resolved via COST_PRIORITY: High-confidence risk rejection overrides cost savings.",
            )
        if cost_vote and cost_vote.verdict == VoteVerdict.APPROVE:
            return (
                DecisionState.CONDITIONAL,
                "Conflict resolved via COST_PRIORITY: Cost module approves. Conditional approval granted.",
            )
        return DecisionState.REQUIRES_APPROVAL, "Conflict requires human arbitration."

    def _resolve_majority(self, consensus: ConsensusResult) -> tuple[DecisionState, str]:
        """Simple majority wins.

        Args:
            consensus: Consensus result

        Returns:
            Resolved (DecisionState, explanation)
        """
        if consensus.approve_count > consensus.reject_count:
            return (
                DecisionState.CONDITIONAL,
                f"Conflict resolved via MAJORITY_WINS: {consensus.approve_count} approve vs {consensus.reject_count} reject.",
            )
        elif consensus.reject_count > consensus.approve_count:
            return (
                DecisionState.REJECTED,
                f"Conflict resolved via MAJORITY_WINS: {consensus.reject_count} reject vs {consensus.approve_count} approve.",
            )
        return DecisionState.ESCALATED, "Deadlock: equal approve and reject votes. Escalating."

    def _resolve_conservative(self, consensus: ConsensusResult) -> tuple[DecisionState, str]:
        """Any rejection triggers approval requirement.

        Args:
            consensus: Consensus result

        Returns:
            Resolved (DecisionState, explanation)
        """
        rejecting_agents = [v.agent_name for v in consensus.votes if v.verdict == VoteVerdict.REJECT]
        return (
            DecisionState.REQUIRES_APPROVAL,
            f"Conflict resolved via CONSERVATIVE: Rejection(s) from {', '.join(rejecting_agents)}. Human approval required.",
        )

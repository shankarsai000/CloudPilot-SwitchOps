"""
CloudPilot SwitchOps — Genuine Multi-Objective Pareto Optimizer

Computes the true non-dominated Pareto frontier across Cost, Security,
Reliability, and Operational Simplicity dimensions.
Ranks non-dominated candidates using explicit, non-overriding preference policies.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from app.domain.decisions import CandidateEvaluation, ParetoStatus
from app.domain.objectives import ObjectiveScores, PreferenceProfile
from app.services.decision.objective_calculator import ObjectiveCalculator

logger = logging.getLogger("cloudpilot.decision.pareto")


class ParetoOptimizer:
    """
    True multi-objective Pareto optimizer.
    Identifies non-dominated engineering options without artificial scalarization during frontier discovery.
    """

    def __init__(self, objective_calculator: Optional[ObjectiveCalculator] = None) -> None:
        self.calculator = objective_calculator or ObjectiveCalculator()

    def calculate_pareto_frontier(
        self,
        evaluations: List[CandidateEvaluation],
        preference_profile: PreferenceProfile = PreferenceProfile.BALANCED,
    ) -> Tuple[List[CandidateEvaluation], List[CandidateEvaluation], List[CandidateEvaluation]]:
        """
        Calculates Pareto dominance across feasible candidate evaluations.
        Returns (pareto_optimal, dominated, rejected).
        """
        feasible: List[CandidateEvaluation] = []
        rejected: List[CandidateEvaluation] = []

        # Step 1: Separate feasible from hard-constraint rejected candidates
        for ev in evaluations:
            if ev.is_feasible:
                feasible.append(ev)
            else:
                ev.pareto_status = ParetoStatus.INFEASIBLE
                rejected.append(ev)

        if not feasible:
            logger.warning("Zero feasible candidates available for Pareto frontier calculation.")
            return [], [], rejected

        pareto_optimal: List[CandidateEvaluation] = []
        dominated: List[CandidateEvaluation] = []

        # Step 2: Genuine pairwise Pareto dominance evaluation
        for i, cand_a in enumerate(feasible):
            is_dominated = False
            dominating_ids: List[str] = []

            for j, cand_b in enumerate(feasible):
                if i == j:
                    continue

                scores_a = cand_a.objective_scores
                scores_b = cand_b.objective_scores

                # Check if candidate B dominates candidate A
                if scores_b.dominates(scores_a):
                    is_dominated = True
                    dominating_ids.append(cand_b.candidate.candidate_id)

            cand_a.dominated_by = dominating_ids
            if is_dominated:
                cand_a.pareto_status = ParetoStatus.DOMINATED
                dominated.append(cand_a)
            else:
                cand_a.pareto_status = ParetoStatus.PARETO_OPTIMAL
                pareto_optimal.append(cand_a)

        # Step 3: Compute weighted scores for ranking within the Pareto frontier
        for ev in pareto_optimal:
            ev.weighted_score = self.calculator.compute_weighted_score(
                ev.objective_scores,
                preference=preference_profile,
            )

        for ev in dominated:
            ev.weighted_score = self.calculator.compute_weighted_score(
                ev.objective_scores,
                preference=preference_profile,
            )

        # Sort Pareto optimal by weighted score descending
        pareto_optimal.sort(key=lambda x: (x.weighted_score or 0.0), reverse=True)
        for rank, ev in enumerate(pareto_optimal, start=1):
            ev.preference_rank = rank

        # Sort dominated by weighted score descending
        dominated.sort(key=lambda x: (x.weighted_score or 0.0), reverse=True)
        for rank, ev in enumerate(dominated, start=len(pareto_optimal) + 1):
            ev.preference_rank = rank

        logger.info(
            "Pareto optimization completed: %d optimal, %d dominated, %d rejected (preference=%s)",
            len(pareto_optimal),
            len(dominated),
            len(rejected),
            preference_profile.value,
        )

        return pareto_optimal, dominated, rejected

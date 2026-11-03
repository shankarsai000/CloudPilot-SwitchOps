"""
CloudPilot SwitchOps — Candidate Evaluator & Interaction Engine

Coordinates candidate constraint validation, multi-objective scoring,
and compatibility analysis (detecting conflicts, redundancies, and dependencies).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from app.domain.candidates import Candidate
from app.domain.decisions import CandidateEvaluation, CandidateInteraction, InteractionType
from app.domain.policies import PolicyConfiguration
from app.services.decision.constraint_engine import ConstraintEngine
from app.services.decision.objective_calculator import ObjectiveCalculator

logger = logging.getLogger("cloudpilot.decision.evaluator")


class CandidateEvaluator:
    """
    Evaluates individual candidates and checks multi-candidate compatibility.
    """

    def __init__(
        self,
        constraint_engine: Optional[ConstraintEngine] = None,
        objective_calculator: Optional[ObjectiveCalculator] = None,
    ) -> None:
        self.constraint_engine = constraint_engine or ConstraintEngine()
        self.objective_calculator = objective_calculator or ObjectiveCalculator()

    def evaluate_all(
        self,
        candidates: List[Candidate],
    ) -> List[CandidateEvaluation]:
        """Evaluate constraints and objective scores for all candidates."""
        evaluations: List[CandidateEvaluation] = []

        for candidate in candidates:
            # 1. Run constraint engine
            constraint_results = self.constraint_engine.evaluate_candidate(candidate)

            # 2. Check feasibility (blocking constraints)
            blocking_results = [cr for cr in constraint_results if cr.is_blocking]
            is_feasible = (len(blocking_results) == 0)
            rejection_reasons = [cr.reason for cr in blocking_results]

            # 3. Compute objective scores
            scores = self.objective_calculator.evaluate_candidate(candidate)

            evaluations.append(
                CandidateEvaluation(
                    candidate=candidate,
                    objective_scores=scores,
                    constraint_results=constraint_results,
                    is_feasible=is_feasible,
                    rejection_reasons=rejection_reasons,
                )
            )

        return evaluations

    def detect_interactions(
        self,
        candidates: List[Candidate],
    ) -> List[CandidateInteraction]:
        """
        Analyze pairs of candidates for attribute collisions, contradictions, and redundancies.
        """
        interactions: List[CandidateInteraction] = []

        # Map resource_id + attribute_path -> list of candidate_ids modifying it
        attribute_map: Dict[Tuple[str, str], List[Candidate]] = {}

        for c in candidates:
            for ch in c.proposed_changes:
                key = (ch.resource_id, ch.attribute_path)
                attribute_map.setdefault(key, []).append(c)

        # Detect conflicting modifications on the exact same resource attribute
        for (res_id, attr), modifying_candidates in attribute_map.items():
            if len(modifying_candidates) > 1:
                cand_ids = [c.candidate_id for c in modifying_candidates]
                # Compare proposed values
                values = [ch.proposed_value for c in modifying_candidates for ch in c.proposed_changes if ch.resource_id == res_id and ch.attribute_path == attr]
                if len(set(str(v) for v in values)) > 1:
                    interactions.append(
                        CandidateInteraction(
                            candidate_ids=cand_ids,
                            interaction_type=InteractionType.CONFLICTING,
                            conflicting_resource_id=res_id,
                            reason=f"Candidates propose contradictory values for '{attr}' on resource '{res_id}'.",
                        )
                    )
                else:
                    interactions.append(
                        CandidateInteraction(
                            candidate_ids=cand_ids,
                            interaction_type=InteractionType.REDUNDANT,
                            conflicting_resource_id=res_id,
                            reason=f"Candidates propose identical changes to '{attr}' on resource '{res_id}'.",
                        )
                    )

        return interactions

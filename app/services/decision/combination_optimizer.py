"""
CloudPilot SwitchOps — Bounded Combination Optimization Engine

Enumerates, validates, and evaluates bounded multi-candidate combinations (k <= 3).
Guarantees:
1. Deterministic enumeration via sorted itertools.combinations.
2. Conflict rejection: no contradictory mutations on the exact same resource attribute.
3. Dependency satisfaction: dependent candidates require parent candidates.
4. Decimal financial aggregation for combined savings and costs.
5. Multi-objective composition: worst-case risk propagation and operational complexity aggregation.
6. Transparent bounded scope tagging: "BOUNDED_COMBINATION (k=3)".
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import hashlib
import itertools
import logging
from typing import Dict, List, Optional, Set, Tuple

from app.domain.candidates import (
    ApplicabilityStatus,
    Candidate,
    CandidateType,
    ImpactLevel,
    OperationalComplexity,
    ProposedChange,
)
from app.domain.decisions import CandidateInteraction, InteractionType

logger = logging.getLogger("cloudpilot.decision.combinations")
TWO_PLACES = Decimal("0.01")


class CombinationOptimizer:
    """
    Bounded combination optimizer exploring multi-candidate change bundles.
    Constrains search space to combinations of size k <= max_combination_size (default k=3).
    """

    def __init__(self, max_combination_size: int = 3) -> None:
        if max_combination_size < 1:
            raise ValueError("max_combination_size must be >= 1")
        self.max_combination_size = max_combination_size

    def generate_valid_combinations(
        self,
        candidates: List[Candidate],
        interactions: Optional[List[CandidateInteraction]] = None,
        max_combinations_to_generate: int = 50,
    ) -> List[Candidate]:
        """
        Enumerates compatible candidate combinations of size 2 <= k <= max_combination_size.
        Returns a list of composite Candidate objects of type COMPOSITE_PLAN.
        """
        if len(candidates) < 2 or self.max_combination_size < 2:
            return []

        # Sort candidates by candidate_id for strictly deterministic enumeration
        sorted_candidates = sorted(candidates, key=lambda c: c.candidate_id)
        candidate_map = {c.candidate_id: c for c in sorted_candidates}

        # Build conflict index: pairs of candidate_ids that cannot co-exist
        conflicts: Set[Tuple[str, str]] = set()
        dependencies: Dict[str, Set[str]] = {}  # dep_id -> set of required parent_ids

        if interactions:
            for inter in interactions:
                if inter.interaction_type in (InteractionType.CONFLICTING, InteractionType.REDUNDANT):
                    ids = sorted(inter.candidate_ids)
                    for i in range(len(ids)):
                        for j in range(i + 1, len(ids)):
                            conflicts.add((ids[i], ids[j]))
                elif inter.interaction_type == InteractionType.DEPENDENT:
                    if len(inter.candidate_ids) >= 2:
                        dep_id = inter.candidate_ids[0]
                        parent_id = inter.candidate_ids[1]
                        dependencies.setdefault(dep_id, set()).add(parent_id)

        # Attribute collision detector: map (resource_id, attribute_path) -> candidate_id -> proposed_value
        attr_values: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for c in sorted_candidates:
            for ch in c.proposed_changes:
                key = (ch.resource_id, ch.attribute_path)
                attr_values.setdefault(key, {})[c.candidate_id] = ch.proposed_value

        # Identify attribute collisions between candidate pairs
        for key, cand_val_map in attr_values.items():
            cand_ids = sorted(cand_val_map.keys())
            for i in range(len(cand_ids)):
                for j in range(i + 1, len(cand_ids)):
                    c1, c2 = cand_ids[i], cand_ids[j]
                    # If proposing different values for same resource attribute, mark conflict
                    if str(cand_val_map[c1]) != str(cand_val_map[c2]):
                        conflicts.add((c1, c2))

        valid_composite_candidates: List[Candidate] = []

        # Enumerate combinations for each size k in [2, max_combination_size]
        for k in range(2, self.max_combination_size + 1):
            if len(sorted_candidates) < k:
                break

            for combo_tuple in itertools.combinations(sorted_candidates, k):
                if len(valid_composite_candidates) >= max_combinations_to_generate:
                    logger.debug("Reached maximum composite plan generation ceiling (%d)", max_combinations_to_generate)
                    break

                combo_ids = [c.candidate_id for c in combo_tuple]

                # Check pairwise conflicts
                has_conflict = False
                for i in range(len(combo_ids)):
                    for j in range(i + 1, len(combo_ids)):
                        pair = (combo_ids[i], combo_ids[j])
                        rev_pair = (combo_ids[j], combo_ids[i])
                        if pair in conflicts or rev_pair in conflicts:
                            has_conflict = True
                            break
                    if has_conflict:
                        break

                if has_conflict:
                    continue

                # Check dependency closure: all dependencies of member candidates must be in combo
                combo_id_set = set(combo_ids)
                dependencies_satisfied = True
                for c_id in combo_ids:
                    required_parents = dependencies.get(c_id, set())
                    if not required_parents.issubset(combo_id_set):
                        dependencies_satisfied = False
                        break

                if not dependencies_satisfied:
                    continue

                # Synthesize valid composite candidate
                composite = self._synthesize_composite_candidate(list(combo_tuple))
                valid_composite_candidates.append(composite)

        logger.info(
            "Bounded combination optimization generated %d valid composite plans (k<=%d)",
            len(valid_composite_candidates),
            self.max_combination_size,
        )
        return valid_composite_candidates

    def _synthesize_composite_candidate(self, members: List[Candidate]) -> Candidate:
        """
        Synthesizes a unified Candidate from a list of compatible member candidates.
        """
        sorted_members = sorted(members, key=lambda c: c.candidate_id)
        member_ids = [c.candidate_id for c in sorted_members]
        hash_seed = ":".join(member_ids).encode("utf-8")
        combo_hash = hashlib.sha256(hash_seed).hexdigest()[:8]
        composite_id = f"comb-{combo_hash}"

        # Combine proposed changes (deduplicating identical changes)
        seen_changes: Set[Tuple[str, str, str]] = set()
        combined_changes: List[ProposedChange] = []
        for m in sorted_members:
            for ch in m.proposed_changes:
                ch_key = (ch.resource_id, ch.attribute_path, str(ch.proposed_value))
                if ch_key not in seen_changes:
                    seen_changes.add(ch_key)
                    combined_changes.append(ch)

        # Financial aggregation using Decimal
        total_savings = Decimal("0.00")
        total_cost_before = Decimal("0.00")
        resource_costs_before: Dict[str, Decimal] = {}
        unassociated_cost_before = Decimal("0.00")
        has_unknown_pricing = False

        for m in sorted_members:
            try:
                savings_dec = Decimal(str(m.estimated_monthly_savings))
                total_savings += savings_dec
            except Exception:
                has_unknown_pricing = True

            try:
                cb_dec = Decimal(str(m.estimated_monthly_cost_before))
                if m.affected_resource_ids:
                    for r_id in m.affected_resource_ids:
                        if r_id not in resource_costs_before:
                            resource_costs_before[r_id] = cb_dec
                        else:
                            resource_costs_before[r_id] = max(resource_costs_before[r_id], cb_dec)
                else:
                    unassociated_cost_before += cb_dec
            except Exception:
                has_unknown_pricing = True

        if resource_costs_before:
            total_cost_before = sum(resource_costs_before.values(), Decimal("0.00")) + unassociated_cost_before
        else:
            for m in sorted_members:
                try:
                    total_cost_before += Decimal(str(m.estimated_monthly_cost_before))
                except Exception:
                    pass

        total_savings = total_savings.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total_cost_before = total_cost_before.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total_cost_after = (total_cost_before - total_savings).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Inherit applicability: if any member is UNSUPPORTED or UNKNOWN, composite inherits it
        combined_applicability = ApplicabilityStatus.APPLICABLE
        if any(m.applicability == ApplicabilityStatus.UNSUPPORTED for m in sorted_members):
            combined_applicability = ApplicabilityStatus.UNSUPPORTED
        elif any(m.applicability == ApplicabilityStatus.UNKNOWN for m in sorted_members):
            combined_applicability = ApplicabilityStatus.UNKNOWN
        elif has_unknown_pricing:
            combined_applicability = ApplicabilityStatus.UNKNOWN

        # Security impact aggregation (pessimistic / monotonic)
        combined_sec = self._aggregate_impact_level([m.security_impact for m in sorted_members])

        # Reliability impact aggregation
        combined_rel = self._aggregate_impact_level([m.reliability_impact for m in sorted_members])

        # Complexity aggregation: maximum complexity among members
        combined_comp = OperationalComplexity.LOW
        if any(m.operational_complexity == OperationalComplexity.HIGH for m in sorted_members):
            combined_comp = OperationalComplexity.HIGH
        elif any(m.operational_complexity == OperationalComplexity.MEDIUM for m in sorted_members):
            combined_comp = OperationalComplexity.MEDIUM

        # Assumptions & findings aggregation
        all_assumptions = list(dict.fromkeys(asm for m in sorted_members for asm in m.assumptions))
        all_findings = list(dict.fromkeys(f for m in sorted_members for f in m.source_finding_ids))
        all_resources = list(dict.fromkeys(r for m in sorted_members for r in m.affected_resource_ids))

        # Reversibility: LOW if any member is LOW, else MEDIUM if any is MEDIUM, else HIGH
        if any(m.reversibility == "LOW" for m in sorted_members):
            reversibility = "LOW"
        elif any(m.reversibility == "MEDIUM" for m in sorted_members):
            reversibility = "MEDIUM"
        else:
            reversibility = "HIGH"

        # Confidence: minimum confidence across members
        combined_confidence = min(m.confidence for m in sorted_members) if sorted_members else 1.0

        title = f"Composite Plan ({len(sorted_members)} changes): " + " + ".join(m.title[:30] for m in sorted_members)
        description = (
            f"Bounded combination of {len(sorted_members)} compatible candidates:\n"
            + "\n".join(f"- {m.title} (${m.estimated_monthly_savings}/mo)" for m in sorted_members)
        )

        return Candidate(
            candidate_id=composite_id,
            title=title[:256],
            description=description[:2048],
            candidate_type=CandidateType.COMPOSITE_PLAN,
            affected_resource_ids=all_resources,
            target_resource_ids=all_resources,
            source_finding_ids=all_findings,
            proposed_changes=combined_changes,
            estimated_monthly_cost_before=str(total_cost_before),
            estimated_monthly_cost_after=str(total_cost_after),
            estimated_monthly_savings=str(total_savings),
            security_impact=combined_sec,
            reliability_impact=combined_rel,
            operational_complexity=combined_comp,
            confidence=combined_confidence,
            assumptions=all_assumptions,
            evidence={
                "member_candidate_ids": member_ids,
                "member_candidate_types": [m.candidate_type.value for m in sorted_members],
                "combination_size": len(member_ids),
                "optimization_scope": "BOUNDED_COMBINATION (k=3)",
                "has_unknown_pricing": has_unknown_pricing,
            },
            applicability=combined_applicability,
            reversibility=reversibility,
            member_candidate_ids=member_ids,
            schema_version="1.1",
        )

    @staticmethod
    def _aggregate_impact_level(impacts: List[ImpactLevel]) -> ImpactLevel:
        """
        Pessimistic aggregation: negative regressions dominate positive improvements.
        If any HIGH_NEGATIVE -> HIGH_NEGATIVE.
        Else if any NEGATIVE -> NEGATIVE.
        Else if any HIGH_POSITIVE -> HIGH_POSITIVE.
        Else if any POSITIVE -> POSITIVE.
        Else NEUTRAL.
        """
        if any(i == ImpactLevel.HIGH_NEGATIVE for i in impacts):
            return ImpactLevel.HIGH_NEGATIVE
        if any(i == ImpactLevel.NEGATIVE for i in impacts):
            return ImpactLevel.NEGATIVE
        if any(i == ImpactLevel.HIGH_POSITIVE for i in impacts):
            return ImpactLevel.HIGH_POSITIVE
        if any(i == ImpactLevel.POSITIVE for i in impacts):
            return ImpactLevel.POSITIVE
        return ImpactLevel.NEUTRAL

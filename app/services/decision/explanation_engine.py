"""
CloudPilot SwitchOps — Decision Explanation & Trade-Off Engine

Generates transparent, engineer-grade explanations of recommendations,
Pareto trade-offs, and constraint rejection reasons.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.domain.candidates import Candidate
from app.domain.decisions import CandidateEvaluation, CandidateInteraction, ParetoStatus
from app.domain.objectives import PreferenceProfile


class ExplanationEngine:
    """
    Constructs deterministic, evidence-backed narrative explanations
    for human operators and technical stakeholders in Switch rooms.
    """

    def explain_recommendation(
        self,
        recommended: Optional[CandidateEvaluation],
        pareto_optimal: List[CandidateEvaluation],
        preference_profile: PreferenceProfile,
    ) -> str:
        """Construct executive recommendation rationale."""
        if not recommended:
            return "No feasible engineering candidate satisfies all active hard constraints."

        c = recommended.candidate
        s = recommended.objective_scores

        w_str = f"Weighted Utility: {recommended.weighted_score:.2f} under `{preference_profile.value}`" if recommended.weighted_score is not None else f"Profile: `{preference_profile.value}`"
        lines = [
            f"**Recommended Option**: `{c.title}` (`{c.candidate_id}`)",
            f"- **Core Value Proposition**: {c.description}",
            f"- **Estimated Monthly Savings**: **${c.estimated_monthly_savings} USD** (Cost after: ${c.estimated_monthly_cost_after}/mo)",
            f"- **Security Impact**: `{c.security_impact.value}` | **Reliability Impact**: `{c.reliability_impact.value}`",
            f"- **Operational Complexity**: `{c.operational_complexity.value}` (Reversibility: `{c.reversibility}`)",
            f"- **Objective Profile**: Cost={s.cost_score:.1f} | Security={s.security_score:.1f} | Reliability={s.reliability_score:.1f} | Simplicity={s.simplicity_score:.1f} ({w_str})",
        ]
        return "\n".join(lines)

    def explain_trade_offs(
        self,
        pareto_optimal: List[CandidateEvaluation],
        recommended: Optional[CandidateEvaluation],
    ) -> str:
        """Explain trade-offs among non-dominated candidates on the Pareto frontier."""
        if not pareto_optimal:
            return "Zero Pareto-optimal candidates identified."

        lines = [
            f"Identified **{len(pareto_optimal)} non-dominated candidate(s)** on the Pareto frontier:",
            "",
        ]

        for ev in pareto_optimal:
            c = ev.candidate
            s = ev.objective_scores
            is_rec = (recommended and c.candidate_id == recommended.candidate.candidate_id)
            tag = " ⭐ **[SELECTED]**" if is_rec else ""

            lines.append(
                f"• `{c.title}`{tag}\n"
                f"  ↳ Savings: **${c.estimated_monthly_savings}/mo** | Scores: Cost={s.cost_score:.0f}, Sec={s.security_score:.0f}, Rel={s.reliability_score:.0f}, Simp={s.simplicity_score:.0f}\n"
                f"  ↳ Trade-off: Complexity `{c.operational_complexity.value}`, Reliability `{c.reliability_impact.value}`"
            )

        return "\n".join(lines)

    def explain_rejections(
        self,
        rejected: List[CandidateEvaluation],
    ) -> List[Dict[str, Any]]:
        """Summarize rejected alternatives and the specific hard constraints that blocked them."""
        summary: List[Dict[str, Any]] = []

        for ev in rejected:
            c = ev.candidate
            failed_constraints = [cr for cr in ev.constraint_results if cr.is_blocking]
            summary.append({
                "candidate_id": c.candidate_id,
                "title": c.title,
                "candidate_type": c.candidate_type.value,
                "failed_constraints": [
                    {
                        "constraint_id": fc.constraint_id,
                        "type": fc.constraint_type.value,
                        "reason": fc.reason,
                    }
                    for fc in failed_constraints
                ],
                "proposed_savings": c.estimated_monthly_savings,
            })

        return summary

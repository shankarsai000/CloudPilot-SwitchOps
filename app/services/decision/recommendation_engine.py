"""
CloudPilot SwitchOps — Recommendation Engine

Synthesizes multi-objective evaluations, Pareto frontiers, and constraint checks
into an authoritative engineering decision report and structured Switch message.
"""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.domain.candidates import Candidate
from app.domain.decisions import (
    CandidateEvaluation,
    CandidateInteraction,
    DecisionReport,
    DecisionRun,
    ParetoStatus,
)
from app.domain.objectives import PreferenceProfile
from app.domain.policies import PolicyConfiguration
from app.services.decision.explanation_engine import ExplanationEngine

logger = logging.getLogger("cloudpilot.decision.recommendation")


def compute_provenance_hash(provenance_data: Dict[str, Any]) -> str:
    """
    Computes a deterministic SHA256 digest over the canonical JSON representation
    of decision inputs, assessment findings, policies, and pricing version.
    """
    # Exclude provenance_hash itself if present to ensure pure idempotent hash computation
    clean_data = {k: v for k, v in provenance_data.items() if k != "provenance_hash"}
    canonical_bytes = json.dumps(clean_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def verify_report_provenance(report: DecisionReport) -> bool:
    """
    Independently verifies evidence provenance integrity.
    Re-computes SHA256 digest from report.evidence_provenance and compares with report.provenance_hash.
    """
    if not report.provenance_hash or not report.evidence_provenance:
        return False
    expected = compute_provenance_hash(report.evidence_provenance)
    return expected == report.provenance_hash


class RecommendationEngine:
    """
    Synthesizes evaluated candidates into decision runs and human-facing reports.
    """

    def __init__(self, explanation_engine: Optional[ExplanationEngine] = None) -> None:
        self.explanation_engine = explanation_engine or ExplanationEngine()

    def build_decision_run(
        self,
        task_id: str,
        assessment_id: str,
        workspace_root: str,
        policy_config: PolicyConfiguration,
        preference_profile: PreferenceProfile,
        pareto_optimal: List[CandidateEvaluation],
        dominated: List[CandidateEvaluation],
        rejected: List[CandidateEvaluation],
        interactions: List[CandidateInteraction],
        z3_status: str = "NOT_RUN",
    ) -> Tuple[DecisionRun, DecisionReport]:
        """
        Builds the persistent DecisionRun and CTO-level DecisionReport.
        """
        decision_id = f"dec-{uuid.uuid4().hex[:10]}"
        total_candidates = len(pareto_optimal) + len(dominated) + len(rejected)

        recommended_eval = pareto_optimal[0] if pareto_optimal else None
        recommended_candidate = recommended_eval.candidate if recommended_eval else None
        recommended_scores = recommended_eval.objective_scores if recommended_eval else None

        executive_summary = self.explanation_engine.explain_recommendation(
            recommended=recommended_eval,
            pareto_optimal=pareto_optimal,
            preference_profile=preference_profile,
        )

        trade_off_analysis = self.explanation_engine.explain_trade_offs(
            pareto_optimal=pareto_optimal,
            recommended=recommended_eval,
        )

        run_status = "COMPLETED" if pareto_optimal else "NO_FEASIBLE_CANDIDATE"

        decision_run = DecisionRun(
            decision_id=decision_id,
            task_id=task_id,
            assessment_id=assessment_id,
            workspace_root=workspace_root,
            policy_config=policy_config,
            preference_profile=preference_profile,
            total_candidates_generated=total_candidates,
            feasible_candidates_count=len(pareto_optimal) + len(dominated),
            rejected_candidates_count=len(rejected),
            pareto_optimal_count=len(pareto_optimal),
            recommended_candidate_id=recommended_candidate.candidate_id if recommended_candidate else None,
            recommended_candidate=recommended_candidate,
            executive_summary=executive_summary,
            trade_off_analysis=trade_off_analysis,
            z3_verification_status=z3_status,
            status=run_status,
        )

        # Collect unique assumptions across feasible candidates
        assumptions = list({
            asm
            for ev in (pareto_optimal + dominated)
            for asm in ev.candidate.assumptions
        })

        # Collect candidate, finding, and resource IDs for tamper-proof provenance hashing
        pareto_ids = sorted([ev.candidate.candidate_id for ev in pareto_optimal])
        all_evals = pareto_optimal + dominated + rejected
        finding_ids = sorted(list(dict.fromkeys(
            f_id for ev in all_evals for f_id in ev.candidate.source_finding_ids
        )))
        resource_ids = sorted(list(dict.fromkeys(
            r_id for ev in all_evals for r_id in ev.candidate.affected_resource_ids
        )))
        source_files = sorted(list(dict.fromkeys(
            ch.source_file for ev in all_evals for ch in ev.candidate.proposed_changes if ch.source_file
        )))

        provenance_data: Dict[str, Any] = {
            "task_id": task_id,
            "assessment_id": assessment_id,
            "workspace_root": workspace_root,
            "pricing_catalog_version": "1.0",
            "policy_version": policy_config.policy_version,
            "objective_model_version": "1.1",
            "optimization_scope": "BOUNDED_COMBINATION (k=3)",
            "z3_verification_status": z3_status,
            "pareto_optimal_candidate_ids": pareto_ids,
            "source_finding_ids": finding_ids,
            "affected_resource_ids": resource_ids,
            "source_files": source_files,
        }
        provenance_hash = compute_provenance_hash(provenance_data)
        provenance_data["provenance_hash"] = provenance_hash

        report = DecisionReport(
            decision_id=decision_id,
            task_id=task_id,
            assessment_id=assessment_id,
            workspace_root=workspace_root,
            preference_profile=preference_profile,
            policy_config=policy_config,
            status=run_status,
            z3_verification_status=z3_status,
            executive_recommendation=recommended_candidate,
            recommended_scores=recommended_scores,
            pareto_optimal_candidates=pareto_optimal,
            feasible_alternatives=dominated,
            rejected_candidates=rejected,
            candidate_interactions=interactions,
            trade_offs_summary=trade_off_analysis,
            assumptions_and_uncertainty=assumptions,
            optimization_scope="BOUNDED_COMBINATION (k=3)",
            objective_model_version="1.1",
            provenance_hash=provenance_hash,
            evidence_provenance=provenance_data,
            evidence_lineage=provenance_data,
        )

        return decision_run, report

    def format_switch_report(
        self,
        decision_run: DecisionRun,
        report: DecisionReport,
    ) -> str:
        """Format an engineering decision report for the Switch room thread."""
        rec = decision_run.recommended_candidate
        rec_title = f"`{rec.title}`" if rec else "_None (No feasible candidate)_"

        lines = [
            f"## 🧠 [CloudPilot SwitchOps] Decision Intelligence & Optimization Report",
            f"- **Decision ID**: `{decision_run.decision_id}` | **Status**: `{decision_run.status}`",
            f"- **Target Workspace**: `{decision_run.workspace_root}`",
            f"- **Preference Profile**: `{decision_run.preference_profile.value}`",
            f"- **Optimization Scope**: `{report.optimization_scope}`",
            f"- **Z3 Formal Constraint Verification**: `{decision_run.z3_verification_status}`",
            f"- **Provenance SHA-256**: `{report.provenance_hash[:16] if report.provenance_hash else 'N/A'}`",
            f"- **Candidate Pool**: {decision_run.total_candidates_generated} generated | **{decision_run.feasible_candidates_count} feasible** | **{decision_run.rejected_candidates_count} rejected** by hard constraints",
            "",
            "### 1. Executive Recommendation",
        ]

        if rec:
            lines.extend([
                f"**{rec.title}** (`{rec.candidate_id}`)",
                f"- **Monthly Impact**: Before: `${rec.estimated_monthly_cost_before}` → After: `${rec.estimated_monthly_cost_after}` (**Savings: ${rec.estimated_monthly_savings}/mo**)",
                f"- **Security**: `{rec.security_impact.value}` | **Reliability**: `{rec.reliability_impact.value}` | **Complexity**: `{rec.operational_complexity.value}`",
                f"- **Key Action**: {rec.description}",
            ])
        else:
            lines.append("_No candidate passed all mandatory security, reliability, and budget constraints._")

        lines.extend([
            "",
            f"### 2. Pareto Frontier & Alternatives ({decision_run.pareto_optimal_count} Non-Dominated)",
        ])

        for ev in report.pareto_optimal_candidates[:4]:
            c = ev.candidate
            s = ev.objective_scores
            tag = " ⭐ [RECOMMENDED]" if rec and c.candidate_id == rec.candidate_id else ""
            lines.append(
                f"- `{c.title}`{tag}: **${c.estimated_monthly_savings}/mo** savings | Scores: Cost={s.cost_score:.0f}, Sec={s.security_score:.0f}, Rel={s.reliability_score:.0f}"
            )

        if report.rejected_candidates:
            lines.extend([
                "",
                f"### 3. Rejected Alternatives ({len(report.rejected_candidates)} Excluded by Hard Constraints)",
            ])
            for ev in report.rejected_candidates[:3]:
                c = ev.candidate
                reason = ev.rejection_reasons[0] if ev.rejection_reasons else "Violated mandatory policy constraint"
                lines.append(f"- ❌ `{c.title}`: **REJECTED** ({reason})")

        lines.extend([
            "",
            "### 4. Next Phase Governance",
            "- Changes are proposed in read-only analysis mode.",
            "- In Phase 4, human approval in this Switch room will be required before applying any change plan.",
            f"\n*Full decision audit trail recorded with evidence provenance referencing Assessment `{decision_run.assessment_id}` (SHA-256: `{report.provenance_hash[:16] if report.provenance_hash else 'N/A'}`).*",
        ])

        return "\n".join(lines)

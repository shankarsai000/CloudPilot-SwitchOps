"""
CloudPilot SwitchOps — Decision Intelligence Domain Models

Represents decision runs, candidate evaluations, Pareto frontiers,
and consolidated engineering decision reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator

from app.domain.candidates import Candidate
from app.domain.constraints import ConstraintResult
from app.domain.objectives import ObjectiveScores, PreferenceProfile
from app.domain.policies import PolicyConfiguration


class ParetoStatus(str, Enum):
    """Pareto classification of an evaluated candidate."""
    PARETO_OPTIMAL = "PARETO_OPTIMAL"  # Non-dominated among feasible candidates
    DOMINATED = "DOMINATED"            # Dominated by at least one feasible candidate
    INFEASIBLE = "INFEASIBLE"          # Violates one or more mandatory hard constraints


class CandidateEvaluation(BaseModel):
    """Evaluation summary for an individual candidate."""
    candidate: Candidate
    objective_scores: ObjectiveScores
    constraint_results: List[ConstraintResult] = Field(default_factory=list)
    is_feasible: bool = True
    rejection_reasons: List[str] = Field(default_factory=list)
    pareto_status: ParetoStatus = ParetoStatus.PARETO_OPTIMAL
    dominated_by: List[str] = Field(default_factory=list, description="IDs of candidates dominating this one")
    preference_rank: Optional[int] = None
    weighted_score: Optional[float] = None


class InteractionType(str, Enum):
    """Type of interaction or conflict between candidate changes."""
    COMPATIBLE = "COMPATIBLE"
    CONFLICTING = "CONFLICTING"
    REDUNDANT = "REDUNDANT"
    DEPENDENT = "DEPENDENT"


class CandidateInteraction(BaseModel):
    """Records an interaction, dependency, or mutual exclusion between candidate changes."""
    candidate_ids: List[str]
    interaction_type: InteractionType
    conflicting_resource_id: Optional[str] = None
    reason: str


class DecisionRun(BaseModel):
    """
    Consolidated record of an autonomous decision intelligence run.
    """
    decision_id: str = Field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:10]}")
    task_id: str
    assessment_id: str
    workspace_root: str
    policy_config: PolicyConfiguration = Field(default_factory=PolicyConfiguration)
    preference_profile: PreferenceProfile = PreferenceProfile.BALANCED
    total_candidates_generated: int = 0
    feasible_candidates_count: int = 0
    rejected_candidates_count: int = 0
    pareto_optimal_count: int = 0
    recommended_candidate_id: Optional[str] = None
    recommended_candidate: Optional[Candidate] = None
    executive_summary: str = ""
    trade_off_analysis: str = ""
    z3_verification_status: str = Field(default="NOT_RUN", description="Z3_VERIFIED_SAT, Z3_VERIFIED_UNSAT, Z3_FALLBACK")
    status: str = Field(default="COMPLETED", description="COMPLETED, NO_FEASIBLE_CANDIDATE, FAILED")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0")

    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class DecisionReport(BaseModel):
    """
    Complete, CTO-grade engineering decision report with full traceability.
    """
    decision_id: str
    task_id: str
    assessment_id: str
    workspace_root: str
    preference_profile: PreferenceProfile
    policy_config: PolicyConfiguration
    status: str
    z3_verification_status: str
    executive_recommendation: Optional[Candidate] = None
    recommended_scores: Optional[ObjectiveScores] = None
    pareto_optimal_candidates: List[CandidateEvaluation] = Field(default_factory=list)
    feasible_alternatives: List[CandidateEvaluation] = Field(default_factory=list)
    rejected_candidates: List[CandidateEvaluation] = Field(default_factory=list)
    candidate_interactions: List[CandidateInteraction] = Field(default_factory=list)
    trade_offs_summary: str = ""
    assumptions_and_uncertainty: List[str] = Field(default_factory=list)
    evidence_lineage: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0")

    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

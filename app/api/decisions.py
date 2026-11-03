"""
CloudPilot SwitchOps — Decision Intelligence API Endpoints

Provides deterministic, read-only multi-objective optimization,
candidate evaluations, constraint satisfiability checks, Pareto frontiers,
and consolidated engineering decision reports.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.errors import NotFoundError, ValidationError
from app.domain.decisions import (
    CandidateEvaluation,
    CandidateInteraction,
    DecisionReport,
    DecisionRun,
    ParetoStatus,
)
from app.domain.objectives import PreferenceProfile
from app.domain.policies import PolicyConfiguration
from app.persistence.repository import TaskRepositoryInterface
from app.services.decision.decision_orchestrator import DecisionOrchestrator
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/v1/decisions", tags=["Decision Intelligence & Optimization"])


def get_repository() -> TaskRepositoryInterface:
    raise NotImplementedError


def get_task_service() -> TaskService:
    raise NotImplementedError


class RunDecisionRequest(BaseModel):
    """Payload to trigger an autonomous decision intelligence optimization run."""
    task_id: Optional[str] = Field(None, description="Existing task ID with completed assessment")
    workspace_root: str = Field(default="samples/staging", description="Workspace directory if task_id not supplied")
    preference_profile: PreferenceProfile = Field(
        default=PreferenceProfile.BALANCED,
        description="Preference profile: BALANCED, COST_FIRST, SECURITY_FIRST, RELIABILITY_FIRST",
    )
    policy_config: Optional[PolicyConfiguration] = Field(
        default=None,
        description="Custom operational constraints and budget ceiling",
    )
    room_id: str = Field(default="cloudpilot-ops", description="Switch room for operational updates")
    requested_by: str = Field(default="@operator:switch", description="Requesting identity")


@router.post("/run", response_model=DecisionRun, summary="Trigger Decision Intelligence Analysis")
async def run_decision_endpoint(
    req: RunDecisionRequest,
    service: TaskService = Depends(get_task_service),
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> DecisionRun:
    """
    Executes autonomous, deterministic candidate generation, hard constraint filtering,
    Z3 SMT verification, and multi-objective Pareto optimization.
    """
    task_id = req.task_id

    # If no task_id provided, find or execute an assessment for this workspace
    if not task_id:
        task = await service.process_task_request(
            title=f"Assessment for Decision on {req.workspace_root}",
            description=f"@cloudpilot-ops-agent assess {req.workspace_root} and prepare for optimization decision.",
            room_id=req.room_id,
            requested_by=req.requested_by,
            task_type="infrastructure_assessment",
            metadata={"workspace_root": req.workspace_root},
        )
        task_id = task.task_id

    # Check if assessment exists
    assessment = repo.get_assessment_for_task(task_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No assessment found for task '{task_id}'. Cannot run decision analysis without an assessment.",
        )

    orchestrator = DecisionOrchestrator(repository=repo)
    decision_run, report = orchestrator.run_decision_analysis(
        task_id=task_id,
        preference_profile=req.preference_profile,
        policy_config=req.policy_config,
    )

    return decision_run


@router.get("/{decision_id}", response_model=DecisionRun, summary="Get Decision Run")
def get_decision_endpoint(
    decision_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> DecisionRun:
    """Retrieve decision run metadata, recommended candidate, and executive summary."""
    run = repo.get_decision_run(decision_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision run '{decision_id}' was not found.",
        )
    return run


@router.get("/task/{task_id}", response_model=DecisionRun, summary="Get Decision Run by Task")
def get_decision_by_task_endpoint(
    task_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> DecisionRun:
    """Retrieve the latest decision run associated with a given assessment task."""
    run = repo.get_decision_run_for_task(task_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No decision run found for task '{task_id}'.",
        )
    return run


@router.get("/{decision_id}/candidates", response_model=List[CandidateEvaluation], summary="Get Evaluated Candidates")
def get_candidates_endpoint(
    decision_id: str,
    feasible_only: bool = Query(False, description="Filter for feasible candidates only"),
    pareto_only: bool = Query(False, description="Filter for Pareto-optimal candidates only"),
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> List[CandidateEvaluation]:
    """Retrieve evaluated candidate changes, objective scores, and feasibility status."""
    evals = repo.get_candidate_evaluations(decision_id)
    if not evals:
        if not repo.get_decision_run(decision_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Decision run '{decision_id}' was not found.",
            )
        return []

    if pareto_only:
        evals = [e for e in evals if e.pareto_status == ParetoStatus.PARETO_OPTIMAL]
    elif feasible_only:
        evals = [e for e in evals if e.is_feasible]

    return evals


@router.get("/{decision_id}/pareto", response_model=List[CandidateEvaluation], summary="Get Pareto Frontier")
def get_pareto_frontier_endpoint(
    decision_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> List[CandidateEvaluation]:
    """Retrieve only the non-dominated, Pareto-optimal candidate changes."""
    evals = repo.get_candidate_evaluations(decision_id)
    if not evals and not repo.get_decision_run(decision_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision run '{decision_id}' was not found.",
        )
    return [e for e in evals if e.pareto_status == ParetoStatus.PARETO_OPTIMAL]


@router.get("/{decision_id}/constraints", summary="Get Constraint Evaluations and Violations")
def get_constraints_endpoint(
    decision_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> Dict[str, Any]:
    """Retrieve detailed constraint evaluations, rejection reasons, and Z3 status."""
    run = repo.get_decision_run(decision_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision run '{decision_id}' was not found.",
        )

    evals = repo.get_candidate_evaluations(decision_id)
    rejected = [e for e in evals if not e.is_feasible]
    feasible = [e for e in evals if e.is_feasible]

    return {
        "decision_id": decision_id,
        "z3_verification_status": run.z3_verification_status,
        "policy_configuration": run.policy_config.model_dump(),
        "total_evaluated": len(evals),
        "feasible_count": len(feasible),
        "rejected_count": len(rejected),
        "rejected_candidates": [
            {
                "candidate_id": e.candidate.candidate_id,
                "title": e.candidate.title,
                "rejection_reasons": e.rejection_reasons,
                "constraint_failures": [
                    c.model_dump() for c in e.constraint_results if not c.passed
                ],
            }
            for e in rejected
        ],
    }


@router.get("/{decision_id}/report", response_model=DecisionReport, summary="Get Full Decision Report")
def get_decision_report_endpoint(
    decision_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> DecisionReport:
    """Retrieve the complete, transparent engineering decision report with full lineage."""
    report = repo.get_decision_report(decision_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision report for '{decision_id}' was not found.",
        )
    return report

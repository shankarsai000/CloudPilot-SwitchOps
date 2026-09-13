"""
FastAPI Router for CloudPilot Intelligence Pipeline.
Mounted under /api/v1/pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from pipeline.models import PipelineEvaluationReport, StageResult, TimelineEvent
from pipeline.orchestrator import get_pipeline_orchestrator

pipeline_router = APIRouter(prefix="/pipeline", tags=["Intelligence Pipeline"])


class PipelineRunRequest(BaseModel):
    """Request payload to initiate a pipeline run."""
    scenario: str = Field(default="SaaS", description="Target scenario: SaaS, Banking, E-commerce, AI Research, Startup, Healthcare, Gaming")
    scale: str = Field(default="small", description="Scale tier: small, medium, large, enterprise")
    seed: int = Field(default=42, description="Deterministic pseudo-random seed")
    timeout_seconds: float = Field(default=120.0, description="Pipeline timeout limit in seconds")
    continue_on_partial_failure: bool = Field(default=True, description="Whether to continue if non-critical stage fails")


class PipelineRunSummaryResponse(BaseModel):
    """Structured response summarizing completed or active pipeline run."""
    run_id: str
    scenario: str
    scale: str
    seed: int
    status: str
    total_duration_ms: float
    stages: Dict[str, StageResult]
    evaluation: Optional[PipelineEvaluationReport] = None


@pipeline_router.post("/run", response_model=PipelineRunSummaryResponse)
def run_pipeline_sync(req: PipelineRunRequest) -> PipelineRunSummaryResponse:
    """
    Execute intelligence pipeline synchronously from end to end (M1 through M9).
    Blocks until all stages and Ground Truth evaluation complete.
    """
    orchestrator = get_pipeline_orchestrator()
    ctx = orchestrator.run(
        scenario_name=req.scenario,
        scale=req.scale,
        seed=req.seed,
        timeout_seconds=req.timeout_seconds,
        continue_on_partial_failure=req.continue_on_partial_failure,
    )
    return PipelineRunSummaryResponse(
        run_id=ctx.run_id,
        scenario=ctx.scenario_name,
        scale=ctx.scale,
        seed=ctx.seed,
        status=ctx.status.value,
        total_duration_ms=round(ctx.total_duration_ms, 2),
        stages=ctx.stage_results,
        evaluation=ctx.ground_truth_evaluation,
    )


@pipeline_router.post("/runs", status_code=202)
def run_pipeline_async(req: PipelineRunRequest) -> Dict[str, Any]:
    """
    Start the intelligence pipeline asynchronously in the background.
    Returns HTTP 202 Accepted with the run_id immediately.
    """
    orchestrator = get_pipeline_orchestrator()
    run_id = orchestrator.start(
        scenario_name=req.scenario,
        scale=req.scale,
        seed=req.seed,
        timeout_seconds=req.timeout_seconds,
        continue_on_partial_failure=req.continue_on_partial_failure,
    )
    return {
        "run_id": run_id,
        "status": "PENDING",
        "scenario": req.scenario,
        "message": "Intelligence pipeline execution queued successfully in the background.",
    }


@pipeline_router.get("/runs")
def list_pipeline_runs() -> List[Dict[str, Any]]:
    """List all recent intelligence pipeline runs with status and duration."""
    orchestrator = get_pipeline_orchestrator()
    return orchestrator.list_runs()


@pipeline_router.get("/runs/{run_id}")
def get_pipeline_run(run_id: str) -> Dict[str, Any]:
    """Inspect status, duration, and stage details of a specific pipeline run."""
    orchestrator = get_pipeline_orchestrator()
    ctx = orchestrator.get_run(run_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")

    decisions_summary = []
    if ctx.decision_state and ctx.decision_state.decisions:
        decisions_summary = [
            {
                "decision_id": d.decision_id,
                "target_id": d.target_id,
                "action": d.action,
                "state": d.state.value if hasattr(d.state, "value") else str(d.state),
                "estimated_savings_usd": d.approval_route.estimated_savings_usd if d.approval_route else 0.0,
            }
            for d in list(ctx.decision_state.decisions.values())[:10]
        ]

    return {
        "run_id": ctx.run_id,
        "scenario": ctx.scenario_name,
        "scale": ctx.scale,
        "seed": ctx.seed,
        "status": ctx.status.value,
        "total_duration_ms": round(ctx.total_duration_ms, 2),
        "created_at": ctx.created_at.isoformat() if ctx.created_at else None,
        "started_at": ctx.started_at.isoformat() if ctx.started_at else None,
        "completed_at": ctx.completed_at.isoformat() if ctx.completed_at else None,
        "stage_statuses": {k: v.status.value for k, v in ctx.stage_results.items()},
        "stage_durations_ms": {k: round(v.duration_ms, 1) for k, v in ctx.stage_results.items()},
        "decisions_count": len(ctx.decision_state.decisions) if ctx.decision_state else 0,
        "decisions_sample": decisions_summary,
        "composite_score": ctx.ground_truth_evaluation.composite_score if ctx.ground_truth_evaluation else None,
    }


@pipeline_router.post("/runs/{run_id}/cancel")
def cancel_pipeline_run(run_id: str) -> Dict[str, Any]:
    """Cancel an active or pending intelligence pipeline execution."""
    orchestrator = get_pipeline_orchestrator()
    cancelled = orchestrator.cancel_run(run_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail=f"Could not cancel run '{run_id}' (not found or already finished)")
    return {"run_id": run_id, "status": "CANCELLED", "message": "Pipeline run cancellation signaled successfully"}


@pipeline_router.get("/runs/{run_id}/timeline", response_model=List[TimelineEvent])
def get_pipeline_timeline(run_id: str) -> List[TimelineEvent]:
    """Retrieve complete auditable timeline event log for a pipeline run."""
    orchestrator = get_pipeline_orchestrator()
    ctx = orchestrator.get_run(run_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")
    return ctx.timeline


@pipeline_router.get("/runs/{run_id}/evaluation", response_model=PipelineEvaluationReport)
def get_pipeline_evaluation(run_id: str) -> PipelineEvaluationReport:
    """Retrieve Ground Truth benchmark evaluation metrics for a completed pipeline run."""
    orchestrator = get_pipeline_orchestrator()
    ctx = orchestrator.get_run(run_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")
    if not ctx.ground_truth_evaluation:
        raise HTTPException(status_code=404, detail=f"Ground Truth evaluation not available for run '{run_id}'")
    return ctx.ground_truth_evaluation

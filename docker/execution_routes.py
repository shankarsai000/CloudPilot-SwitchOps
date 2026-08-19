"""
Execution API Routes

FastAPI router exposing endpoints for starting, pausing, resuming, cancelling,
rolling back, and retrieving metrics and history for executions.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models_execution import ExecutionRecord, RolloutStrategy
from execution_agent import ExecutionAgent

logger = logging.getLogger(__name__)


# --- Request Models ---


class StartExecutionRequest(BaseModel):
    """Payload to start a new execution run."""

    decision_id: str
    target_id: str
    action: str
    approval_metadata: dict[str, Any] = Field(default_factory=dict)
    rollback_plan: dict[str, Any] = Field(default_factory=dict)
    provider: str = "AWS"
    rollout_strategy: RolloutStrategy = RolloutStrategy.DIRECT
    has_violations: bool = False


class PauseResumeRequest(BaseModel):
    """Payload to pause or resume execution."""

    execution_id: str
    reason: str = ""


class ManualRollbackRequest(BaseModel):
    """Payload to manually trigger a rollback."""

    execution_id: str
    trigger_reason: str
    rollback_plan: dict[str, Any] = Field(default_factory=dict)


def create_execution_router(
    agent: Any = None,
    repository: Any = None,
) -> APIRouter:
    """Create FastAPI router for Execution Agent.

    Args:
        agent: ExecutionAgent instance
        repository: ExecutionRepository instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/execution", tags=["execution"])

    @router.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "execution-agent"}

    @router.post("/start", response_model=ExecutionRecord)
    async def start(request: StartExecutionRequest) -> ExecutionRecord:
        """Start a new execution pipeline run."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        try:
            return agent.start_execution(
                decision_id=request.decision_id,
                target_id=request.target_id,
                action=request.action,
                approval_metadata=request.approval_metadata,
                rollback_plan=request.rollback_plan,
                provider=request.provider,
                rollout_strategy=request.rollout_strategy,
                has_violations=request.has_violations,
            )
        except Exception as e:
            logger.error("Failed to start execution: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/pause", response_model=ExecutionRecord)
    async def pause(request: PauseResumeRequest) -> ExecutionRecord:
        """Pause a running execution."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        try:
            return agent.pause_execution(request.execution_id, request.reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/resume", response_model=ExecutionRecord)
    async def resume(request: PauseResumeRequest) -> ExecutionRecord:
        """Resume a paused execution."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        try:
            return agent.resume_execution(request.execution_id, request.reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/cancel", response_model=ExecutionRecord)
    async def cancel(request: PauseResumeRequest) -> ExecutionRecord:
        """Cancel a pending or ready execution."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        try:
            return agent.cancel_execution(request.execution_id, request.reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/rollback", response_model=ExecutionRecord)
    async def rollback(request: ManualRollbackRequest) -> ExecutionRecord:
        """Manually trigger rollback on an execution."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        try:
            return agent.trigger_manual_rollback(
                request.execution_id, request.trigger_reason, request.rollback_plan
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/status")
    async def get_status(execution_id: str = Query(..., description="Execution ID")) -> dict[str, str]:
        """Get the status of an execution run."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        status = agent.get_execution_status(execution_id)
        if not status:
            raise HTTPException(status_code=404, detail="Execution not found")
        return {"execution_id": execution_id, "status": status}

    @router.get("/logs")
    async def get_logs(execution_id: str = Query(..., description="Execution ID")) -> list[dict[str, Any]]:
        """Get logs registered for an execution."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        return agent.get_execution_logs(execution_id)

    @router.get("/metrics")
    async def get_metrics(execution_id: str = Query(..., description="Execution ID")) -> dict[str, Any]:
        """Get live metrics of an execution."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        record = agent.get_execution(execution_id)
        if not record:
            raise HTTPException(status_code=404, detail="Execution not found")
        return {"execution_id": execution_id, "metrics": record.metrics_summary}

    @router.get("/history")
    async def get_history() -> list[dict[str, Any]]:
        """Get execution run history."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        history = agent.get_execution_history()
        return [h.dict() for h in history]

    @router.get("/{execution_id}", response_model=ExecutionRecord)
    async def get_execution(execution_id: str) -> ExecutionRecord:
        """Get full execution record by ID."""
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        record = agent.get_execution(execution_id)
        if not record:
            raise HTTPException(status_code=404, detail="Execution not found")
        return record

    return router

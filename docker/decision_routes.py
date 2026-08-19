"""
Decision API Routes

FastAPI router exposing endpoints for M9 Decision Engine evaluation, overrides,
approvals, audit trails, and history.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from models_decision import (
    AgentVote,
    DecisionRecord,
    DecisionState,
    OverrideAction,
    OverrideRecord,
)
from decision_agent import DecisionAgent

logger = logging.getLogger(__name__)


# --- Request Models ---


class EvaluateRequest(BaseModel):
    """Payload to evaluate a proposal."""

    target_id: str
    action: str
    votes: list[AgentVote]
    estimated_savings_usd: float = 0.0
    risk_category: str = "LOW"
    region: str = "us-east-1"
    is_production: bool = False
    compliance_frameworks: list[str] = Field(default_factory=list)
    score_inputs: Optional[dict[str, float]] = None


class ActionRequest(BaseModel):
    """Payload to approve/reject a pending decision."""

    decision_id: str
    actor: str
    reason: str = ""


class OverrideRequest(BaseModel):
    """Payload to apply manual override."""

    decision_id: str
    action: OverrideAction
    actor: str
    reason: str = ""
    modified_properties: Optional[dict[str, Any]] = None


def create_decision_router(
    agent: Any = None,
    repository: Any = None,
) -> APIRouter:
    """Create FastAPI router for Decision Engine.

    Args:
        agent: DecisionAgent instance
        repository: DecisionRepository instance

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/api/decision", tags=["decision"])

    @router.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Health status
        """
        return {"status": "healthy", "service": "decision-engine"}

    @router.post("/evaluate", response_model=DecisionRecord)
    async def evaluate(request: EvaluateRequest) -> DecisionRecord:
        """Evaluate a proposal through the Decision Council.

        Returns:
            DecisionRecord
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        try:
            return agent.evaluate(
                target_id=request.target_id,
                action=request.action,
                votes=request.votes,
                estimated_savings_usd=request.estimated_savings_usd,
                risk_category=request.risk_category,
                region=request.region,
                is_production=request.is_production,
                compliance_frameworks=request.compliance_frameworks,
                score_inputs=request.score_inputs,
            )
        except Exception as e:
            logger.error("Failed to evaluate proposal: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/pending", response_model=list[DecisionRecord])
    async def get_pending() -> list[DecisionRecord]:
        """List all pending decisions.

        Returns:
            List of pending DecisionRecord instances
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        return agent.get_pending_decisions()

    @router.get("/history")
    async def get_history() -> list[dict[str, Any]]:
        """Get decision history.

        Returns:
            List of decision dicts
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        decisions = agent.get_decision_history()
        return [d.dict() for d in decisions]

    @router.get("/audit")
    async def get_audit() -> list[dict[str, Any]]:
        """Get full decision audit trail.

        Returns:
            List of audit log entries
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        return agent.get_audit_trail()

    @router.get("/{decision_id}", response_model=DecisionRecord)
    async def get_decision(decision_id: str) -> DecisionRecord:
        """Retrieve a specific decision by ID.

        Returns:
            DecisionRecord
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        record = agent.get_decision(decision_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
        return record

    @router.post("/approve", response_model=DecisionRecord)
    async def approve(request: ActionRequest) -> DecisionRecord:
        """Manually approve a pending decision.

        Returns:
            Updated DecisionRecord
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        try:
            return agent.approve(request.decision_id, request.actor, request.reason)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/reject", response_model=DecisionRecord)
    async def reject(request: ActionRequest) -> DecisionRecord:
        """Manually reject a pending decision.

        Returns:
            Updated DecisionRecord
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        try:
            return agent.reject(request.decision_id, request.actor, request.reason)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/override")
    async def override(request: OverrideRequest) -> dict[str, Any]:
        """Apply manual override to a decision.

        Returns:
            Confirmation payload with updated record and override history
        """
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not available")
        try:
            record, override_rec = agent.apply_override(
                decision_id=request.decision_id,
                action=request.action,
                actor=request.actor,
                reason=request.reason,
                modified_properties=request.modified_properties,
            )
            return {
                "status": "applied",
                "decision": record.dict(),
                "override": override_rec.dict(),
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router

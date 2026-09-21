"""
CloudPilot Copilot REST API Endpoints.

Provides conversational chat, multi-turn session tracking, interactive approval
dispatch, and mission status endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from copilot.engine import CloudPilotCopilotEngine, get_copilot_engine
from copilot.models import CopilotConversation, CopilotIntent, CopilotResponse

logger = logging.getLogger("cloudpilot.copilot.routes")

router = APIRouter(prefix="/copilot", tags=["Copilot"])


class ChatRequest(BaseModel):
    """Request payload for conversational chat."""
    message: str = Field(..., min_length=1, description="Natural-language question or command")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID to continue session")
    scenario_name: str = Field("SaaS", description="Simulated or active enterprise environment name")


class ApprovalRequest(BaseModel):
    """Request payload to approve or deny a pending agent execution."""
    conversation_id: str = Field(..., description="Conversation ID holding the pending checkpoint")
    decision: str = Field("APPROVE", description="Decision: 'APPROVE' or 'DENY'")
    reason: str = Field("Approved via Copilot conversational interface", description="Audit reasoning")
    approved_by: str = Field("operator@cloudpilot.ai", description="Operator identity")


class ConversationSummary(BaseModel):
    """Brief metadata for conversation listing."""
    conversation_id: str
    scenario_name: str
    message_count: int
    active_session_id: Optional[str] = None
    has_pending_approval: bool
    created_at: str
    updated_at: str


@router.post("/chat", response_model=CopilotResponse)
def copilot_chat(
    req: ChatRequest,
    engine: CloudPilotCopilotEngine = Depends(get_copilot_engine),
) -> CopilotResponse:
    """
    Process natural-language prompt through Copilot conversational engine.
    Supports billing diagnosis, dependency discovery, 'Fix it' autonomous dispatch,
    and approval interactions.
    """
    try:
        response = engine.chat(
            user_message=req.message,
            conversation_id=req.conversation_id,
            scenario_name=req.scenario_name,
        )
        return response
    except Exception as exc:
        logger.error("Copilot chat processing failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Copilot chat failed: {str(exc)}",
        )


@router.get("/conversations", response_model=List[ConversationSummary])
def list_conversations(
    engine: CloudPilotCopilotEngine = Depends(get_copilot_engine),
) -> List[ConversationSummary]:
    """List all persisted Copilot conversation sessions."""
    summaries = []
    with engine._lock:
        for conv in engine._conversations.values():
            summaries.append(
                ConversationSummary(
                    conversation_id=conv.conversation_id,
                    scenario_name=conv.scenario_name,
                    message_count=len(conv.messages),
                    active_session_id=conv.active_session_id,
                    has_pending_approval=bool(conv.pending_approval_checkpoint_id),
                    created_at=conv.created_at.isoformat(),
                    updated_at=conv.updated_at.isoformat(),
                )
            )
    return summaries


@router.get("/conversations/{conversation_id}", response_model=Dict[str, Any])
def get_conversation(
    conversation_id: str,
    engine: CloudPilotCopilotEngine = Depends(get_copilot_engine),
) -> Dict[str, Any]:
    """Retrieve full history and state for a single conversation session."""
    with engine._lock:
        conv = engine._conversations.get(conversation_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation '{conversation_id}' not found",
            )
        return conv.model_dump(mode="json")


@router.post("/approve", response_model=CopilotResponse)
def approve_or_deny(
    req: ApprovalRequest,
    engine: CloudPilotCopilotEngine = Depends(get_copilot_engine),
) -> CopilotResponse:
    """
    Approve or deny an agent mission awaiting human sign-off in the conversation.
    Resumes or cancels the autonomous agent loop.
    """
    approved = req.decision.strip().upper() in ("APPROVE", "APPROVED", "YES", "TRUE")
    try:
        response = engine.handle_approval_decision(
            conversation_id=req.conversation_id,
            approved=approved,
            approved_by=req.approved_by,
            reason=req.reason,
        )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.error("Copilot approval processing failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Approval dispatch failed: {str(exc)}",
        )

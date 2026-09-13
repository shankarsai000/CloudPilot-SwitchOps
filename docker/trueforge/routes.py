"""
FastAPI REST Routes for TrueForge Agent Harness & TrueFoundry AI Gateway.

Provides standard HTTP & SSE streaming endpoints matching the official
TrueFoundry Agent Harness OpenAPI specification.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from trueforge.gateway import build_cloudpilot_agent_manifest
from trueforge.models import (
    ApprovalAllow,
    ApprovalDeny,
    Session,
    Turn,
    TurnEvent,
    TurnInputItem,
    UserMessage,
    UserToolApprovalEvent,
)
from trueforge.runtime import get_agent_runtime
from trueforge.sandbox import get_sandbox_manager
from trueforge.state import get_agent_state_manager

logger = logging.getLogger("cloudpilot.trueforge.routes")

router = APIRouter()


class CreateSessionRequest(BaseModel):
    agent_name: str = Field("cloudpilot-cost-optimizer", description="Name of agent")
    title: Optional[str] = Field(None, description="Session title")


class CreateTurnRequest(BaseModel):
    input: Optional[List[Dict[str, Any]]] = Field(None, description="Turn input items")
    previous_turn_id: Optional[str] = Field("auto", description="Chain point: auto, none, or turn ID")


class ObjectiveExecutionRequest(BaseModel):
    objective: str = Field(..., description="Operational objective")
    scenario_name: str = Field("SaaS", description="Cloud environment / simulator scenario")
    auto_approve: bool = Field(False, description="If true, immediately approve after validation")


# -----------------------------------------------------------------------------
# Agent Manifest Endpoints
# -----------------------------------------------------------------------------
@router.get("/manifest", tags=["TrueForge Agents"])
@router.post("/manifest", tags=["TrueForge Agents"])
def get_or_register_manifest() -> Dict[str, Any]:
    """Get the official TrueForge AgentManifest for CloudPilot."""
    manifest = build_cloudpilot_agent_manifest()
    return manifest.model_dump(mode="json")


# -----------------------------------------------------------------------------
# Session Lifecycle Endpoints
# -----------------------------------------------------------------------------
@router.post("/sessions", tags=["TrueForge Agents"])
def create_session(req: CreateSessionRequest) -> Dict[str, Any]:
    """Create a new conversation session for CloudPilot."""
    state = get_agent_state_manager()
    session = state.create_session(agent_name=req.agent_name, title=req.title)
    return {"data": session.model_dump(mode="json")}


@router.get("/sessions", tags=["TrueForge Agents"])
def list_sessions(agent_name: Optional[str] = None) -> Dict[str, Any]:
    """List sessions, sorted newest first."""
    state = get_agent_state_manager()
    sessions = state.list_sessions(agent_name=agent_name)
    return {"data": [s.model_dump(mode="json") for s in sessions]}


@router.get("/sessions/{session_id}", tags=["TrueForge Agents"])
def get_session(session_id: str) -> Dict[str, Any]:
    """Get session by ID."""
    state = get_agent_state_manager()
    session = state.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"data": session.model_dump(mode="json")}


@router.post("/sessions/{session_id}/cancel", tags=["TrueForge Agents"])
def cancel_session(session_id: str) -> Dict[str, Any]:
    """Cancel any active turn running in the session."""
    state = get_agent_state_manager()
    cancelled = state.cancel_session(session_id)
    return {"status": "success", "cancelled": cancelled}


# -----------------------------------------------------------------------------
# Turn Execution Endpoints
# -----------------------------------------------------------------------------
@router.post("/sessions/{session_id}/turns", tags=["TrueForge Agents"])
def create_turn(session_id: str, req: CreateTurnRequest) -> Dict[str, Any]:
    """Execute a turn synchronously without live streaming."""
    runtime = get_agent_runtime()
    # Parse turn input
    inputs = []
    for item in req.input or []:
        if item.get("type") == "user.message":
            inputs.append(UserMessage(**item))
        elif item.get("type") == "user.tool_approval":
            inputs.append(UserToolApprovalEvent(**item))
        else:
            inputs.append(item)

    try:
        turn = runtime.create_turn(
            session_id=session_id,
            input_items=inputs,
            previous_turn_id=req.previous_turn_id,
        )
        return {"data": turn.model_dump(mode="json")}
    except Exception as e:
        logger.exception("Error executing turn in session %s", session_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/turns/stream", tags=["TrueForge Agents"])
def create_turn_stream(session_id: str, req: CreateTurnRequest) -> StreamingResponse:
    """Execute a turn with live Server-Sent Events (SSE) streaming."""
    runtime = get_agent_runtime()
    inputs = []
    for item in req.input or []:
        if item.get("type") == "user.message":
            inputs.append(UserMessage(**item))
        elif item.get("type") == "user.tool_approval":
            inputs.append(UserToolApprovalEvent(**item))
        else:
            inputs.append(item)

    def sse_generator():
        try:
            stream = runtime.create_turn_stream(
                session_id=session_id,
                input_items=inputs,
                previous_turn_id=req.previous_turn_id,
            )
            for event in stream:
                data = event.model_dump(mode="json")
                yield f"event: {data.get('type')}\ndata: {json.dumps(data, default=str)}\n\n"
        except Exception as err:
            err_data = {"type": "turn.error", "error": str(err)}
            yield f"event: turn.error\ndata: {json.dumps(err_data, default=str)}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@router.get("/sessions/{session_id}/turns", tags=["TrueForge Agents"])
def list_turns(session_id: str) -> Dict[str, Any]:
    """List turns for a session (newest first)."""
    state = get_agent_state_manager()
    turns = state.list_turns(session_id)
    return {"data": [t.model_dump(mode="json") for t in turns]}


@router.get("/sessions/{session_id}/turns/{turn_id}", tags=["TrueForge Agents"])
def get_turn(session_id: str, turn_id: str) -> Dict[str, Any]:
    """Get a single turn by ID."""
    state = get_agent_state_manager()
    turn = state.get_turn(session_id, turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail=f"Turn {turn_id} not found")
    return {"data": turn.model_dump(mode="json")}


@router.get("/sessions/{session_id}/turns/{turn_id}/events", tags=["TrueForge Agents"])
def list_turn_events(session_id: str, turn_id: str) -> Dict[str, Any]:
    """List recorded events for a turn."""
    state = get_agent_state_manager()
    events = state.list_turn_events(turn_id)
    return {"data": events}


# -----------------------------------------------------------------------------
# Sandbox File Download Endpoint
# -----------------------------------------------------------------------------
@router.get("/sandbox/{sandbox_id}/file", tags=["TrueForge Sandbox"])
def download_sandbox_file(
    sandbox_id: str,
    path: str = Query(..., description="Absolute or relative path inside sandbox"),
) -> Response:
    """Download a file produced by the agent inside the sandbox."""
    sbx = get_sandbox_manager()
    try:
        content = sbx.get_sandbox_file(sandbox_id, path)
        return Response(content=content, media_type="application/octet-stream")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found inside sandbox")
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -----------------------------------------------------------------------------
# Operational Objective Convenience Endpoint
# -----------------------------------------------------------------------------
@router.post("/objective", tags=["TrueForge Agents"])
def execute_objective(req: ObjectiveExecutionRequest) -> Dict[str, Any]:
    """
    Convenience endpoint: Accepts a natural language operational objective,
    opens a session, executes Turn 1 (planning & sandbox validation),
    and optionally auto-approves Turn 2.
    """
    runtime = get_agent_runtime()
    session = runtime.create_session(title=req.objective[:50])

    # Turn 1: Process objective
    turn_1 = runtime.create_turn(
        session_id=session.id,
        input_items=[UserMessage(content=req.objective)],
    )

    t1_state = turn_1.state
    required_actions = getattr(t1_state, "required_actions", [])

    result: Dict[str, Any] = {
        "session_id": session.id,
        "turn_1_id": turn_1.id,
        "turn_1_status": getattr(t1_state, "status", "unknown"),
        "approval_required": len(required_actions) > 0,
        "required_actions": [a.model_dump(mode="json") if hasattr(a, "model_dump") else a for a in required_actions],
    }

    # If auto-approve was requested and approvals are pending, execute Turn 2
    if req.auto_approve and required_actions:
        approvals = []
        for action in required_actions:
            tool_calls = getattr(action, "tool_calls", [])
            thread_id = getattr(action, "thread_id", "main")
            for tc in tool_calls:
                cid = getattr(tc, "id", None) or (tc.get("id") if isinstance(tc, dict) else str(tc))
                approvals.append(UserToolApprovalEvent(
                    thread_id=thread_id,
                    tool_call_id=cid,
                    approval=ApprovalAllow(),
                ))

        turn_2 = runtime.create_turn(
            session_id=session.id,
            input_items=approvals,
            previous_turn_id=turn_1.id,
        )
        t2_state = turn_2.state
        result["turn_2_id"] = turn_2.id
        result["turn_2_status"] = getattr(t2_state, "status", "unknown")
        result["final_output"] = getattr(getattr(t2_state, "output", None), "content", None)

    return result

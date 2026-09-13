"""
Safety & Autonomy Control Plane — FastAPI REST Endpoints.

Exposes governance capabilities:
- Autonomy levels & demotion history
- Emergency stop engagement & status
- 9-factor action evaluation & authorization
- Human-in-the-loop approval workflows
- Action locks & rate limit metrics
- Cryptographic hash-chain integrity verification
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from governance.control_plane import SafetyControlPlane, get_safety_control_plane
from governance.models import (
    ActionEvaluation,
    ApprovalRequest,
    ApprovalRoute,
    ApprovalStatus,
    AuditRecord,
    AutonomyLevel,
    EmergencyStopState,
    ProposedAction,
)

router = APIRouter(prefix="", tags=["Safety & Autonomy Governance"])


# -----------------------------------------------------------------------------
# Request / Response Schemas
# -----------------------------------------------------------------------------

class SetAutonomyRequest(BaseModel):
    level: AutonomyLevel
    actor: str = "operator"
    reason: str = "Operator configuration update"


class EngageEmergencyStopRequest(BaseModel):
    scope: str = "global"
    reason: str = "Operator engaged emergency stop"
    activated_by: str = "operator"


class ReleaseEmergencyStopRequest(BaseModel):
    scope: str = "global"


class EvaluateActionRequest(BaseModel):
    action: ProposedAction
    evidence: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


class AuthorizeActionRequest(BaseModel):
    action: ProposedAction
    approval_request_id: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


class SubmitApprovalDecisionRequest(BaseModel):
    approver: str
    role: str = "engineer"
    approved: bool
    reason: Optional[str] = None


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.get("/autonomy", summary="Get Current Autonomy Level")
def get_autonomy_level() -> Dict[str, Any]:
    cp = get_safety_control_plane()
    level = cp.autonomy.get_level()
    history = cp.autonomy.demotion_controller.get_demotion_history()
    return {
        "current_autonomy_level": level.value,
        "description": {
            AutonomyLevel.L0_OBSERVE: "L0: Observe only — telemetry and inspection",
            AutonomyLevel.L1_RECOMMEND: "L1: Recommend only — optimization proposals",
            AutonomyLevel.L2_SIMULATE: "L2: Simulate only — digital twin impact forecasting",
            AutonomyLevel.L3_APPROVAL: "L3: Execute with human approval gate",
            AutonomyLevel.L4_LIMITED: "L4: Limited autonomous execution (safe, reversible dev/test)",
            AutonomyLevel.L5_FULL: "L5: Full autonomous execution bounded by policy and limits",
        }.get(level, ""),
        "demotion_events_count": len(history),
        "recent_demotions": [h.model_dump(mode="json") for h in history[-5:]],
    }


@router.post("/autonomy/set", summary="Set / Promote Autonomy Level")
def set_autonomy_level(req: SetAutonomyRequest) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    new_level = cp.autonomy.set_level(
        new_level=req.level,
        actor=req.actor,
        reason=req.reason,
    )
    return {
        "status": "UPDATED",
        "new_autonomy_level": new_level.value,
        "updated_by": req.actor,
        "reason": req.reason,
    }


@router.get("/emergency", summary="List Active Emergency Stops")
def list_emergency_stops() -> Dict[str, Any]:
    cp = get_safety_control_plane()
    stops = cp.emergency.list_active_stops()
    return {
        "is_global_stop_active": cp.emergency.is_stopped(),
        "active_stops_count": len(stops),
        "stops": [s.model_dump(mode="json") for s in stops],
    }


@router.post("/emergency/engage", summary="Engage Emergency Stop")
def engage_emergency_stop(req: EngageEmergencyStopRequest) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    state = cp.emergency.engage(
        scope=req.scope,
        reason=req.reason,
        activated_by=req.activated_by,
    )
    return {
        "status": "ENGAGED",
        "scope": state.scope,
        "activated_by": state.activated_by,
        "reason": state.reason,
        "activated_at": state.activated_at.isoformat() if state.activated_at else None,
    }


@router.post("/emergency/release", summary="Release Emergency Stop")
def release_emergency_stop(req: ReleaseEmergencyStopRequest) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    released = cp.emergency.release(scope=req.scope)
    if not released:
        raise HTTPException(status_code=404, detail=f"No active emergency stop found for scope '{req.scope}'")
    return {
        "status": "RELEASED",
        "scope": req.scope,
    }


@router.post("/actions/evaluate", summary="Evaluate Proposed Action Across 9 Dimensions")
def evaluate_action(req: EvaluateActionRequest) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    evaluation = cp.evaluate_action(
        action=req.action,
        evidence=req.evidence,
        context=req.context,
    )
    return evaluation.model_dump(mode="json")


@router.post("/actions/authorize", summary="Pre-Flight Execution Authorization Check")
def authorize_action(req: AuthorizeActionRequest) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    authorized, reason, evaluation = cp.authorize_execution(
        action=req.action,
        approval_request_id=req.approval_request_id,
        evidence=req.evidence,
        context=req.context,
    )
    return {
        "authorized": authorized,
        "verdict_reason": reason,
        "action_id": req.action.action_id,
        "current_autonomy_level": cp.autonomy.get_level().value,
        "required_approval": evaluation.required_approval.value,
        "can_auto_execute": evaluation.can_auto_execute,
        "policy_compliant": evaluation.policy_report.is_compliant,
    }


@router.post("/approvals", summary="Create Approval Request")
def create_approval(req: EvaluateActionRequest) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    evaluation = cp.evaluate_action(req.action, req.evidence, req.context)
    approval_req = cp.request_approval(req.action, evaluation)
    return approval_req.model_dump(mode="json")


@router.get("/approvals", summary="List Approval Requests")
def list_approvals(
    status: Optional[ApprovalStatus] = None,
    route: Optional[ApprovalRoute] = None,
) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    requests = cp.approvals.list_requests(status=status, route=route)
    return {
        "total": len(requests),
        "requests": [r.model_dump(mode="json") for r in requests],
    }


@router.get("/approvals/{request_id}", summary="Get Approval Request Details")
def get_approval_request(request_id: str) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    req = cp.approvals.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Approval request '{request_id}' not found")
    return req.model_dump(mode="json")


@router.post("/approvals/{request_id}/decide", summary="Submit Approval or Rejection Decision")
def decide_approval_request(
    request_id: str,
    req: SubmitApprovalDecisionRequest,
) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    ok, approval_req, msg = cp.decide_approval(
        request_id=request_id,
        approver=req.approver,
        role=req.role,
        approved=req.approved,
        reason=req.reason,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "status": approval_req.status.value,
        "message": msg,
        "request": approval_req.model_dump(mode="json"),
    }


@router.get("/audit", summary="Query Cryptographic Audit Trail")
def list_audit_records(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    cp = get_safety_control_plane()
    records = cp.audit.list_records(limit=limit, offset=offset, actor=actor)
    total = cp.audit.count_records()
    return {
        "total_records": total,
        "limit": limit,
        "offset": offset,
        "records": [r.model_dump(mode="json") for r in records],
    }


@router.post("/audit/verify", summary="Verify SHA-256 Hash-Chain Integrity")
def verify_audit_integrity() -> Dict[str, Any]:
    cp = get_safety_control_plane()
    is_valid, msg, broken_idx = cp.audit.verify_integrity()
    return {
        "is_valid": is_valid,
        "message": msg,
        "broken_block_index": broken_idx,
        "total_blocks_verified": cp.audit.count_records(),
    }


@router.get("/locks", summary="List Active Action Locks")
def list_active_locks() -> Dict[str, Any]:
    cp = get_safety_control_plane()
    active_locks = cp.locks.list_active_locks()
    return {
        "active_locks_count": len(active_locks),
        "locks": [l.model_dump(mode="json") for l in active_locks],
    }

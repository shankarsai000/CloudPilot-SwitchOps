"""
CloudPilot SwitchOps — Human Approval and Proposal API Endpoints (Phase 4)

Provides authenticated proposal generation, cryptographic token issuance,
and human approval/rejection lifecycle management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.errors import NotFoundError, ValidationError
from app.domain.approvals import (
    ApprovalPrincipal,
    ApprovalRecord,
    ApproverRole,
    PERMITTED_APPROVAL_ROLES,
)
from app.domain.proposals import Proposal, ProposalStatus
from app.persistence.repository import TaskRepositoryInterface
from app.services.approval.approval_service import ApprovalSecurityError, ApprovalService

router = APIRouter(prefix="/api/v1", tags=["Human-in-the-Loop Approval"])


def get_repository() -> TaskRepositoryInterface:
    raise NotImplementedError


def get_approval_service(repo: TaskRepositoryInterface = Depends(get_repository)) -> ApprovalService:
    return ApprovalService(repository=repo)


from app.services.approval.auth_provider import ServerSidePrincipalAuthenticator

_authenticator = ServerSidePrincipalAuthenticator()


def get_authenticated_principal(
    x_user_id: Optional[str] = Header(None, description="Authenticated principal user ID"),
    x_user_role: Optional[str] = Header(None, description="Authenticated principal role"),
    authorization: Optional[str] = Header(None, description="Bearer token or auth header"),
) -> ApprovalPrincipal:
    """
    Extracts and authenticates the requesting operator principal using server-side directory.
    Fails closed if authentication headers are missing, spoofed, or role is escalated.
    """
    return _authenticator.authenticate(
        x_user_id=x_user_id,
        x_user_role=x_user_role,
        authorization=authorization,
    )


class CreateProposalRequest(BaseModel):
    """Payload to create an exact change proposal from a decision run."""
    decision_id: str = Field(..., description="Target decision run ID")
    candidate_id: Optional[str] = Field(None, description="Specific candidate ID (defaults to recommended)")
    workspace_root: str = Field(default="samples/staging", description="Target workspace directory")
    ttl_seconds: int = Field(default=3600, description="Proposal validity duration in seconds")


class RequestTokenRequest(BaseModel):
    """Payload to request an approval token."""
    ttl_seconds: int = Field(default=3600, description="Token validity duration in seconds")


class SubmitApprovalRequest(BaseModel):
    """Payload to approve a change proposal."""
    token: str = Field(..., description="Cryptographically signed HMAC-SHA256 approval token")


class SubmitRejectionRequest(BaseModel):
    """Payload to reject a change proposal."""
    reason: str = Field(..., description="Mandatory reason explaining the rejection")


# --- Proposal Endpoints ---

@router.post("/proposals", response_model=Proposal, summary="Generate Change Proposal from DecisionRun")
async def create_proposal_endpoint(
    req: CreateProposalRequest,
    repo: TaskRepositoryInterface = Depends(get_repository),
    approval_svc: ApprovalService = Depends(get_approval_service),
) -> Proposal:
    decision_run = repo.get_decision_run(req.decision_id)
    if not decision_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DecisionRun '{req.decision_id}' not found",
        )

    # Determine candidate
    target_candidate = None
    if req.candidate_id:
        evals = repo.get_candidate_evaluations(req.decision_id)
        for ev in evals:
            if ev.candidate.candidate_id == req.candidate_id:
                target_candidate = ev.candidate
                break
        if not target_candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate '{req.candidate_id}' not found in decision '{req.decision_id}'",
            )
    else:
        target_candidate = decision_run.recommended_candidate

    if not target_candidate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"DecisionRun '{req.decision_id}' has no feasible recommended candidate",
        )

    decision_report = repo.get_decision_report(req.decision_id)

    try:
        proposal = approval_svc.generate_proposal_from_decision(
            decision_run=decision_run,
            candidate=target_candidate,
            workspace_root=req.workspace_root,
            ttl_seconds=req.ttl_seconds,
            decision_report=decision_report,
        )
        return proposal
    except ApprovalSecurityError as sec_err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=sec_err.message)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/proposals/{proposal_id}", response_model=Proposal, summary="Retrieve Proposal by ID")
async def get_proposal_endpoint(
    proposal_id: str,
    approval_svc: ApprovalService = Depends(get_approval_service),
) -> Proposal:
    prop = approval_svc.get_proposal(proposal_id)
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found",
        )
    return prop


@router.get("/proposals", response_model=List[Proposal], summary="List Proposals")
async def list_proposals_endpoint(
    decision_id: Optional[str] = Query(None, description="Filter by decision ID"),
    proposal_status: Optional[ProposalStatus] = Query(None, description="Filter by status"),
    approval_svc: ApprovalService = Depends(get_approval_service),
) -> List[Proposal]:
    return approval_svc.list_proposals(decision_id=decision_id, status=proposal_status)


# --- Approval Endpoints ---

@router.post("/approvals/{proposal_id}/token", summary="Request Signed Approval Token")
async def request_approval_token_endpoint(
    proposal_id: str,
    req: RequestTokenRequest,
    principal: ApprovalPrincipal = Depends(get_authenticated_principal),
    approval_svc: ApprovalService = Depends(get_approval_service),
) -> Dict[str, Any]:
    if not principal.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Principal '{principal.principal_id}' is not authorized to request approval tokens.",
        )

    try:
        token_str, payload = approval_svc.request_approval_token(
            proposal_id=proposal_id,
            principal=principal,
            ttl_seconds=req.ttl_seconds,
        )
        return {
            "token": token_str,
            "token_id": payload.token_id,
            "proposal_id": payload.proposal_id,
            "proposal_hash": payload.proposal_hash,
            "approver_id": payload.approver_id,
            "expires_at": payload.expires_at,
        }
    except ApprovalSecurityError as sec_err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=sec_err.message)
    except NotFoundError as nf_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=nf_err.message)


@router.post("/approvals/{proposal_id}/approve", response_model=ApprovalRecord, summary="Approve Proposal")
async def approve_proposal_endpoint(
    proposal_id: str,
    req: SubmitApprovalRequest,
    principal: ApprovalPrincipal = Depends(get_authenticated_principal),
    approval_svc: ApprovalService = Depends(get_approval_service),
) -> ApprovalRecord:
    if not principal.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unauthorized: Principal '{principal.principal_id}' lacks required approval role.",
        )

    try:
        record = approval_svc.submit_approval(
            proposal_id=proposal_id,
            token_string=req.token,
            principal=principal,
        )
        return record
    except ApprovalSecurityError as sec_err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=sec_err.message)
    except NotFoundError as nf_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=nf_err.message)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/approvals/{proposal_id}/reject", response_model=ApprovalRecord, summary="Reject Proposal")
async def reject_proposal_endpoint(
    proposal_id: str,
    req: SubmitRejectionRequest,
    principal: ApprovalPrincipal = Depends(get_authenticated_principal),
    approval_svc: ApprovalService = Depends(get_approval_service),
) -> ApprovalRecord:
    if not principal.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unauthorized: Principal '{principal.principal_id}' lacks required approval role.",
        )

    try:
        record = approval_svc.submit_rejection(
            proposal_id=proposal_id,
            principal=principal,
            reason=req.reason,
        )
        return record
    except ApprovalSecurityError as sec_err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=sec_err.message)
    except NotFoundError as nf_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=nf_err.message)


@router.get("/approvals/{proposal_id}", response_model=ApprovalRecord, summary="Get Approval Record by Proposal ID")
async def get_approval_endpoint(
    proposal_id: str,
    approval_svc: ApprovalService = Depends(get_approval_service),
) -> ApprovalRecord:
    record = approval_svc.get_approval(proposal_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No approval record found for proposal '{proposal_id}'",
        )
    return record


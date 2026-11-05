"""
CloudPilot SwitchOps — Bounded Execution API Endpoints (Phase 4)

Provides human-authorized, isolated workspace execution endpoints,
execution status queries, and cryptographic audit trail retrieval.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.core.errors import NotFoundError
from app.domain.approvals import (
    ApprovalPrincipal,
    ApproverRole,
)
from app.domain.execution import (
    AuditLogEvent,
    ExecutionRecord,
)
from app.domain.policies import PolicyConfiguration
from app.persistence.repository import TaskRepositoryInterface
from app.services.approval.approval_service import ApprovalSecurityError
from app.services.execution.execution_orchestrator import ExecutionOrchestrator
from app.services.execution.execution_policy import PreExecutionCheckError

router = APIRouter(prefix="/api/v1/executions", tags=["Bounded Execution & Recovery"])


def get_repository() -> TaskRepositoryInterface:
    raise NotImplementedError


def get_execution_orchestrator(repo: TaskRepositoryInterface = Depends(get_repository)) -> ExecutionOrchestrator:
    return ExecutionOrchestrator(repository=repo)


def get_authenticated_principal(
    x_user_id: Optional[str] = Header(None, description="Authenticated principal user ID"),
    x_user_role: Optional[str] = Header(None, description="Authenticated principal role"),
    authorization: Optional[str] = Header(None, description="Bearer token or auth header"),
) -> ApprovalPrincipal:
    if not x_user_id:
        return ApprovalPrincipal(
            principal_id="anonymous",
            display_name="Anonymous Operator",
            role=ApproverRole.OPERATOR,
            authenticated=False,
            auth_mechanism="UNAUTHENTICATED",
        )

    try:
        role = ApproverRole(x_user_role.upper()) if x_user_role else ApproverRole.OPERATOR
    except ValueError:
        role = ApproverRole.OPERATOR

    is_authenticated = bool(authorization and authorization.startswith("Bearer ")) or bool(x_user_id and x_user_role)

    return ApprovalPrincipal(
        principal_id=x_user_id,
        display_name=x_user_id,
        role=role,
        authenticated=is_authenticated,
        auth_mechanism="API_AUTHENTICATED_SESSION" if is_authenticated else "UNAUTHENTICATED",
    )


class ExecuteProposalRequest(BaseModel):
    """Payload to trigger human-authorized proposal execution."""
    token: str = Field(..., description="Cryptographically signed HMAC-SHA256 approval token")
    target_workspace_root: Optional[str] = Field(None, description="Optional override for target workspace directory")
    policy_config: Optional[PolicyConfiguration] = Field(None, description="Optional active policy configuration")


@router.post("/{proposal_id}/execute", response_model=ExecutionRecord, summary="Execute Approved Proposal")
async def execute_proposal_endpoint(
    proposal_id: str,
    req: ExecuteProposalRequest,
    principal: ApprovalPrincipal = Depends(get_authenticated_principal),
    orchestrator: ExecutionOrchestrator = Depends(get_execution_orchestrator),
) -> ExecutionRecord:
    """
    Executes an approved proposal inside an isolated sandbox workspace.
    Requires an authenticated operator holding an authorized approval role
    and a valid, unconsumed, cryptographically signed approval token.
    """
    if not principal.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unauthorized: Principal '{principal.principal_id}' lacks required execution authorization.",
        )

    try:
        execution = orchestrator.execute_approved_proposal(
            proposal_id=proposal_id,
            token_string=req.token,
            approver=principal,
            target_workspace_root=req.target_workspace_root,
            policy=req.policy_config,
        )
        return execution
    except ApprovalSecurityError as sec_err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=sec_err.message)
    except PreExecutionCheckError as pre_err:
        raise HTTPException(status_code=status.HTTP_412_PRECONDITION_FAILED, detail=str(pre_err))
    except NotFoundError as nf_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=nf_err.message)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{execution_id}", response_model=ExecutionRecord, summary="Get Execution Status by ID")
async def get_execution_endpoint(
    execution_id: str,
    orchestrator: ExecutionOrchestrator = Depends(get_execution_orchestrator),
) -> ExecutionRecord:
    rec = orchestrator.get_execution(execution_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution '{execution_id}' not found",
        )
    return rec


@router.get("/{execution_id}/audit", response_model=List[AuditLogEvent], summary="Get Cryptographic Audit Trail")
async def get_execution_audit_trail_endpoint(
    execution_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> List[AuditLogEvent]:
    events = repo.get_audit_events_for_execution(execution_id)
    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No audit records found for execution '{execution_id}'",
        )
    return events

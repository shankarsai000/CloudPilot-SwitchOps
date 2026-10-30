"""
CloudPilot SwitchOps — Assessment & Cloud Intelligence API Endpoints

Provides read-only queries for discovered infrastructure inventories,
versioned evidence-backed findings (FinOps, SecOps, Reliability),
and consolidated assessment reports.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.errors import NotFoundError, ValidationError
from app.domain.finding import (
    AssessmentSummary,
    Finding,
    FindingCategory,
    FindingSeverity,
)
from app.domain.inventory import InfrastructureInventory
from app.persistence.repository import TaskRepositoryInterface
from app.services.finops.engine import FinOpsEngine
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/v1/assessments", tags=["Assessments & Cloud Intelligence"])


def get_repository() -> TaskRepositoryInterface:
    raise NotImplementedError


def get_task_service() -> TaskService:
    raise NotImplementedError


class RunAssessmentRequest(BaseModel):
    """Payload to trigger an autonomous infrastructure assessment."""
    workspace_root: str = Field(default="samples/staging", description="Target workspace directory")
    room_id: str = Field(default="cloudpilot-ops", description="Switch room for operational updates")
    requested_by: str = Field(default="@operator:switch", description="Requesting identity")


@router.post("/run", response_model=AssessmentSummary, summary="Trigger Infrastructure Assessment")
async def run_assessment_endpoint(
    req: RunAssessmentRequest,
    service: TaskService = Depends(get_task_service),
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> AssessmentSummary:
    """
    Initiate an autonomous, read-only multi-specialist assessment
    (Discovery + FinOps + SecOps + SRE) for a specified workspace directory.
    """
    task = await service.process_task_request(
        title=f"Assessment of {req.workspace_root}",
        description=f"@cloudpilot-ops-agent assess {req.workspace_root} for cost, security and reliability.",
        room_id=req.room_id,
        requested_by=req.requested_by,
        task_type="infrastructure_assessment",
        metadata={"workspace_root": req.workspace_root},
    )

    assessment = repo.get_assessment_for_task(task.task_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Assessment processing failed to produce a summary record.",
        )
    return assessment


@router.get("/{task_id}", response_model=AssessmentSummary, summary="Get Consolidated Assessment")
def get_assessment_endpoint(
    task_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> AssessmentSummary:
    """Retrieve consolidated operational assessment summary for a specific task."""
    assessment = repo.get_assessment_for_task(task_id)
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment summary for task '{task_id}' was not found.",
        )
    return assessment


@router.get("/{task_id}/inventory", response_model=InfrastructureInventory, summary="Get Discovered Inventory")
def get_inventory_endpoint(
    task_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> InfrastructureInventory:
    """Retrieve normalized discovered infrastructure inventory for a specific task."""
    inventory = repo.get_inventory_for_task(task_id)
    if not inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Discovered inventory for task '{task_id}' was not found.",
        )
    return inventory


@router.get("/{task_id}/findings", response_model=List[Finding], summary="Get Assessment Findings")
def get_findings_endpoint(
    task_id: str,
    category: Optional[FindingCategory] = Query(None, description="Filter by finding category"),
    severity: Optional[FindingSeverity] = Query(None, description="Filter by finding severity"),
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> List[Finding]:
    """Retrieve specialist findings (FinOps, SecOps, SRE) with optional category/severity filtering."""
    findings = repo.get_findings_for_task(task_id, category=category)
    if severity:
        findings = [f for f in findings if f.severity == severity]
    return findings


@router.get("/{task_id}/findings/{finding_id}", response_model=Finding, summary="Get Single Finding")
def get_finding_detail_endpoint(
    task_id: str,
    finding_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> Finding:
    """Retrieve a single finding by finding identifier."""
    finding = repo.get_finding(finding_id)
    if not finding or finding.task_id != task_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding '{finding_id}' was not found for task '{task_id}'.",
        )
    return finding


@router.get("/{task_id}/cost-breakdown", summary="Get FinOps Cost Breakdown")
def get_cost_breakdown_endpoint(
    task_id: str,
    repo: TaskRepositoryInterface = Depends(get_repository),
) -> Dict[str, Any]:
    """Retrieve itemized monthly cost calculations and FinOps findings."""
    inventory = repo.get_inventory_for_task(task_id)
    if not inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No discovered inventory found for task '{task_id}' to compute cost breakdown.",
        )

    engine = FinOpsEngine()
    result = engine.analyze(inventory=inventory, task_id=task_id)

    return {
        "task_id": task_id,
        "workspace_root": inventory.workspace_root,
        "total_monthly_cost": result.total_monthly_cost,
        "currency": result.currency,
        "monthly_hours": result.monthly_hours,
        "items": [item.model_dump() for item in result.items],
        "findings_count": len(result.findings),
        "summary": result.summary_text,
    }

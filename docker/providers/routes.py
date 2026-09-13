"""
FastAPI Routes for Production Multi-Cloud Providers, Capability Discovery, and GitOps Lifecycle.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from providers.credentials import get_credential_vault
from providers.gitops_terraform import get_gitops_engine
from providers.models import (
    Capability,
    CloudProvider,
    HealthCheckResult,
    ProviderError,
    ProviderSummary,
)
from providers.registry import get_production_provider_registry

logger = logging.getLogger("cloudpilot.providers.routes")

router = APIRouter(prefix="/providers", tags=["Production Providers"])


class CredentialRotateRequest(BaseModel):
    """Payload for rotating provider credentials."""
    operator: str = "cloudpilot-operator"
    new_credentials: dict[str, Any] = Field(..., description="New credential key-value pairs")


class GitOpsPipelineRequest(BaseModel):
    """Payload to initiate or progress a GitOps/Terraform lifecycle run."""
    stage: str = Field("plan", description="GitOps stage: plan, review, approval, apply, verify, rollback")
    plan_id: Optional[str] = None
    workspace: str = "production-default"
    provider: CloudProvider = CloudProvider.AWS
    target_resource: str = "payment-service-primary"
    action: str = "SCALE_DOWN"
    estimated_cost_delta: float = -50.0
    operator: str = "cloudpilot-admin"


class GitOpsDecisionRequest(BaseModel):
    """Payload for operator decision on gated GitOps plan."""
    plan_id: str
    decision: str = Field(..., description="APPROVED or REJECTED")
    operator: str = "security-lead"
    reason: str = "Approved after reviewing diff and risk rating"


@router.get("", response_model=list[ProviderSummary])
async def list_providers() -> list[ProviderSummary]:
    """Capability discovery endpoint: lists all configured providers and capabilities."""
    registry = get_production_provider_registry()
    return registry.list_providers()


@router.get("/{provider}/capabilities")
async def get_provider_capabilities(provider: CloudProvider) -> dict[str, Any]:
    """Get explicit capability matrix and mode for a specific provider."""
    registry = get_production_provider_registry()
    adapter = registry.get_adapter(provider)
    return {
        "provider": provider.value,
        "mode": adapter.mode.value,
        "is_read_only": adapter.mode.value == "read_only",
        "supported_capabilities": [c.value for c in adapter.supported_capabilities],
    }


@router.get("/{provider}/health", response_model=HealthCheckResult)
async def get_provider_health(provider: CloudProvider) -> HealthCheckResult:
    """Run active connectivity and credential health check for a provider."""
    registry = get_production_provider_registry()
    adapter = registry.get_adapter(provider)
    return adapter.health_check()


@router.post("/{provider}/credentials/rotate")
async def rotate_credentials(
    provider: CloudProvider,
    payload: CredentialRotateRequest,
) -> dict[str, Any]:
    """Rotate credentials for a provider with pre-rotation verification and zero downtime."""
    vault = get_credential_vault()
    try:
        success = vault.rotate_credentials(
            provider=provider,
            new_credentials=payload.new_credentials,
            operator=payload.operator,
        )
        return {
            "status": "SUCCESS" if success else "FAILED",
            "provider": provider.value,
            "operator": payload.operator,
            "message": f"Credentials rotated successfully for {provider.value}",
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/gitops/pipeline")
async def execute_gitops_pipeline(payload: GitOpsPipelineRequest) -> dict[str, Any]:
    """Execute or advance a stage in the 6-stage GitOps/Terraform lifecycle."""
    engine = get_gitops_engine()
    stage = payload.stage.lower()

    try:
        if stage == "plan":
            record = engine.stage_plan(
                workspace=payload.workspace,
                provider=payload.provider,
                target_resource=payload.target_resource,
                action=payload.action,
                estimated_cost_delta=payload.estimated_cost_delta,
            )
            return record.to_dict()

        if not payload.plan_id:
            raise HTTPException(status_code=400, detail="plan_id is required for stages after 'plan'")

        if stage == "review":
            record = engine.stage_review(payload.plan_id)
        elif stage == "approval":
            record = engine.stage_approval(payload.plan_id, operator=payload.operator)
        elif stage == "apply":
            record = engine.stage_apply(payload.plan_id, operator=payload.operator)
        elif stage == "verify":
            record = engine.stage_verify(payload.plan_id)
        elif stage == "rollback":
            record = engine.stage_rollback(payload.plan_id)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid GitOps stage: {stage}")

        return record.to_dict()

    except ProviderError as pe:
        raise HTTPException(status_code=400, detail={"error_code": pe.error_code, "message": pe.message})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/gitops/decide")
async def decide_gitops_plan(payload: GitOpsDecisionRequest) -> dict[str, Any]:
    """Submit human approval or rejection decision for a gated GitOps plan."""
    engine = get_gitops_engine()
    try:
        record = engine.record_human_decision(
            plan_id=payload.plan_id,
            decision=payload.decision,
            operator=payload.operator,
            reason=payload.reason,
        )
        return record.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/gitops/runs")
async def list_gitops_runs() -> list[dict[str, Any]]:
    """List all recorded GitOps runs."""
    engine = get_gitops_engine()
    return engine.list_runs()


@router.get("/resilience/metrics")
async def get_resilience_metrics() -> dict[str, Any]:
    """Retrieve rate limiting and circuit breaker metrics across all providers."""
    registry = get_production_provider_registry()
    metrics: dict[str, Any] = {}
    for provider, adapter in registry._adapters.items():
        metrics[provider.value] = {
            "rate_limiter": adapter.rate_limiter.get_metrics(),
            "circuit_breaker": adapter.circuit_breaker.get_metrics(),
        }
    return metrics

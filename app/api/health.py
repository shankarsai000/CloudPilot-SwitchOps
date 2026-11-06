"""
CloudPilot SwitchOps — Health & Readiness Probes

Provides standard operational endpoints:
- `GET /health/live`: Kubernetes/Docker liveness probe
- `GET /health/ready`: Readiness probe verifying database and Switch connection
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.integrations.switch.client import SwitchAdapterInterface
from app.integrations.switch.connection_manager import SwitchConnectionManager
from app.persistence.repository import TaskRepositoryInterface

router = APIRouter(tags=["Health & Diagnostics"])

START_TIME = datetime.now(timezone.utc)


class LivenessResponse(BaseModel):
    status: str
    app_name: str
    app_version: str
    uptime_seconds: float
    timestamp: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    switch_integration: dict[str, Any]
    timestamp: str


class SwitchStatusResponse(BaseModel):
    configured: bool
    state: str
    healthy: bool
    truthful_report: dict[str, Any]
    capabilities: dict[str, Any]
    timestamp: str


# Module-level dependency providers to be overridden or bound in main.py
def get_repository() -> TaskRepositoryInterface:
    raise NotImplementedError


def get_switch_adapter() -> SwitchAdapterInterface:
    raise NotImplementedError


def get_switch_connection_manager() -> Optional[SwitchConnectionManager]:
    return None


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Liveness Probe",
    description="Returns 200 OK if the application process is running and alive.",
)
def liveness_probe(settings: Settings = Depends(get_settings)) -> LivenessResponse:
    uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()
    return LivenessResponse(
        status="healthy",
        app_name=settings.app_name,
        app_version=settings.app_version,
        uptime_seconds=round(uptime, 2),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness Probe",
    description="Validates that database persistence and Switch integration boundaries are operational.",
)
async def readiness_probe(
    settings: Settings = Depends(get_settings),
    repo: TaskRepositoryInterface = Depends(get_repository),
    adapter: SwitchAdapterInterface = Depends(get_switch_adapter),
    manager: Optional[SwitchConnectionManager] = Depends(get_switch_connection_manager),
) -> ReadinessResponse:
    # 1. Validate Database Persistence
    db_status = "healthy"
    try:
        # Perform read probe on task repository
        repo.list_tasks(limit=1)
    except Exception as exc:
        db_status = f"unhealthy: {exc!s}"

    # 2. Validate Switch Bridge Connection
    switch_report: dict[str, Any] = {
        "configured": settings.is_switch_configured(),
        "bridge_url": settings.switch_bridge_url,
    }
    try:
        health_res = await adapter.check_health()
        switch_report["status"] = health_res.get("status", "healthy")
    except Exception as exc:
        switch_report["status"] = "degraded"
        switch_report["error"] = str(exc)

    if manager is not None:
        health_obj = manager.get_health()
        switch_report["connection_health"] = health_obj.to_status_dict()
        switch_report["capabilities"] = health_obj.protocol_capabilities.model_dump()
        switch_report["truthful_state"] = health_obj.state.value

    # Calculate overall readiness
    is_ready = db_status == "healthy" and switch_report["status"] == "healthy"

    resp = ReadinessResponse(
        status="ready" if is_ready else "degraded",
        database=db_status,
        switch_integration=switch_report,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    if not is_ready and db_status != "healthy":
        # Database failure is a hard unready state
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=resp.model_dump(),
        )

    return resp


@router.get(
    "/health/switch",
    response_model=SwitchStatusResponse,
    summary="Switch Status and Capabilities",
    description="Exposes the truthful connectivity state and capability matrix for Switch integration.",
)
@router.get(
    "/api/v1/switch/status",
    response_model=SwitchStatusResponse,
    summary="Switch Diagnostic Status (API alias)",
    include_in_schema=False,
)
async def switch_status(
    settings: Settings = Depends(get_settings),
    adapter: SwitchAdapterInterface = Depends(get_switch_adapter),
    manager: Optional[SwitchConnectionManager] = Depends(get_switch_connection_manager),
) -> SwitchStatusResponse:
    configured = settings.is_switch_configured()
    if manager is not None:
        health_obj = manager.get_health()
        return SwitchStatusResponse(
            configured=configured,
            state=health_obj.state.value,
            healthy=health_obj.is_operational(),
            truthful_report=health_obj.to_status_dict(),
            capabilities=health_obj.protocol_capabilities.model_dump(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # Fallback if connection manager is not bound
    return SwitchStatusResponse(
        configured=configured,
        state="UNKNOWN",
        healthy=False,
        truthful_report={"error": "Connection manager not initialized"},
        capabilities={},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

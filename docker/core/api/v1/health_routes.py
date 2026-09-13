"""
Health, readiness, and metrics REST endpoints (v1).
"""

from typing import Any, Dict
from fastapi import APIRouter, Response, status
from fastapi.responses import PlainTextResponse

from core.observability.health import (
    HealthCheckReport,
    ReadinessReport,
    get_health_status,
    get_readiness_status,
)
from core.observability.metrics import get_metrics_collector

health_router = APIRouter(tags=["Observability"])


@health_router.get("/health", response_model=HealthCheckReport)
async def health_endpoint() -> HealthCheckReport:
    """Liveness probe: verifies the service process is alive."""
    return get_health_status()


@health_router.get("/ready", response_model=ReadinessReport)
async def readiness_endpoint(response: Response) -> ReadinessReport:
    """Readiness probe: verifies database, redis, and module subsystems."""
    report = get_readiness_status()
    if report.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report


@health_router.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint() -> PlainTextResponse:
    """Expose Prometheus formatted metrics for scrapers."""
    collector = get_metrics_collector()
    return PlainTextResponse(content=collector.render_prometheus(), media_type="text/plain; version=0.0.4")


@health_router.get("/metrics/summary", response_model=Dict[str, Any])
async def metrics_summary_endpoint() -> Dict[str, Any]:
    """Expose metrics in JSON format for dashboards and health checks."""
    collector = get_metrics_collector()
    return collector.get_summary()

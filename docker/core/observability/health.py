"""
Health and readiness evaluation probes.
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict
from pydantic import BaseModel, Field

from core.config import get_settings
from core.database.connection import DatabaseHealthStatus, check_database_health
from core.redis.client import RedisHealthStatus, check_redis_health

_START_TIME = time.time()


class HealthCheckReport(BaseModel):
    """Liveness probe response model."""
    status: str = Field(default="healthy", description="Overall liveness status")
    version: str = Field(description="Application version")
    environment: str = Field(description="Runtime environment")
    uptime_seconds: float = Field(description="Uptime in seconds")
    timestamp: str = Field(description="ISO timestamp")


class ReadinessReport(BaseModel):
    """Readiness probe response model."""
    status: str = Field(description="'ready' or 'not_ready'")
    database: DatabaseHealthStatus
    redis: RedisHealthStatus
    modules: Dict[str, str] = Field(default_factory=dict)
    timestamp: str = Field(description="ISO timestamp")


def get_health_status() -> HealthCheckReport:
    """Return process liveness status and uptime."""
    settings = get_settings()
    uptime = time.time() - _START_TIME
    return HealthCheckReport(
        status="healthy",
        version=settings.app_version,
        environment=settings.environment.value,
        uptime_seconds=round(uptime, 2),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def get_readiness_status() -> ReadinessReport:
    """Check connectivity to PostgreSQL and Redis to determine readiness."""
    db_health = check_database_health()
    redis_health = check_redis_health()

    # Determine readiness: if database is connected and redis is operational
    is_ready = db_health.connected and redis_health.connected

    module_statuses = {
        "M1_discovery": "ready",
        "M2_cost": "ready",
        "M3_application": "ready",
        "M4_risk": "ready",
        "M5_strategy": "ready",
        "M6_digital_twin": "ready",
        "M7_explainability": "ready",
        "M8_learning": "ready",
        "M9_decision": "ready",
        "M10_execution": "ready",
        "M11_demo": "ready",
    }

    return ReadinessReport(
        status="ready" if is_ready else "not_ready",
        database=db_health,
        redis=redis_health,
        modules=module_statuses,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

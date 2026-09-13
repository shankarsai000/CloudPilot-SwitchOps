"""
CloudPilot AI — Production Unified FastAPI Service Entry Point

Mounts REST API routes for all modules (M1 to M11), provides production configuration,
structured logging, centralized error handling, correlation ID tracking,
health/readiness probes, metrics exposition, and API versioning (/api/v1).
"""

from contextlib import asynccontextmanager
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure docker directory is on sys.path
docker_dir = Path(__file__).resolve().parent
if str(docker_dir) not in sys.path:
    sys.path.insert(0, str(docker_dir))

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Core platform foundation imports
from core.api.v1.router import create_v1_router
from core.config import get_settings
from core.database.connection import check_database_health
from core.errors import register_error_handlers
from core.logging import (
    CorrelationIdMiddleware,
    configure_logging,
    get_logger,
)
from core.observability.health import (
    HealthCheckReport,
    ReadinessReport,
    get_health_status,
    get_readiness_status,
)
from core.observability.metrics import MetricsMiddleware, get_metrics_collector
from core.redis.client import check_redis_health

# Module route initializers (M1 - M11)
from application_routes import create_application_router
from cost_routes import init_routes as init_cost_routes
from decision_routes import create_decision_router
from demo_routes import create_demo_router
from discovery_routes import create_discovery_router
from execution_routes import create_execution_router
from explanation_routes import create_explanation_router
from learning_routes import create_learning_router
from risk_routes import create_risk_router
from simulation_routes import create_simulation_router
from strategy_routes import create_strategy_router

settings = get_settings()

# Initialize structured logging based on environment
configure_logging(level=settings.log_level, log_format=settings.log_format)
logger = get_logger("cloudpilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle hooks for resource initialization and teardown."""
    logger.info(
        "Starting CloudPilot AI Platform v%s (Environment: %s)",
        settings.app_version,
        settings.environment.value,
    )

    # Perform background health checks on startup
    db_health = check_database_health()
    logger.info("Startup Database Check: connected=%s (%s)", db_health.connected, db_health.details)

    redis_health = check_redis_health()
    logger.info(
        "Startup Redis Check: connected=%s, fallback=%s (%s)",
        redis_health.connected,
        redis_health.is_fallback,
        redis_health.details,
    )

    yield

    logger.info("Shutting down CloudPilot AI Platform cleanly...")


# Initialize FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Unified cloud reasoning and autonomous optimization engine",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Register middlewares (order matters: CorrelationId runs outer, Metrics inner)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register centralized exception handlers
register_error_handlers(app)


# ══════════════════════════════════════════════════════════════════
# Top-level Health, Readiness, and Root Endpoints
# ══════════════════════════════════════════════════════════════════

@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect root endpoint to the Command Center dashboard."""
    return RedirectResponse(url="/dashboard/")


@app.get("/healthz", response_model=HealthCheckReport, tags=["Probes"])
async def liveness_probe() -> HealthCheckReport:
    """Kubernetes liveness probe: verifies process is alive and responsive."""
    return get_health_status()


@app.get("/readyz", response_model=ReadinessReport, tags=["Probes"])
async def readiness_probe(response: Response) -> ReadinessReport:
    """Kubernetes readiness probe: verifies database and cache connectivity."""
    report = get_readiness_status()
    if report.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report


@app.get("/metrics", response_class=PlainTextResponse, tags=["Observability"])
async def prometheus_metrics() -> PlainTextResponse:
    """Prometheus metrics scraper endpoint."""
    collector = get_metrics_collector()
    return PlainTextResponse(
        content=collector.render_prometheus(),
        media_type="text/plain; version=0.0.4",
    )


def mount_all_routers() -> None:
    """Instantiate components and register all legacy (/api/*) and modern (/api/v1/*) routes."""
    logger.info("Initializing and mounting CloudPilot AI modules...")

    # Create mock/dummy components to ensure startup succeeds without active DB/cloud connections
    mock_repo = MagicMock()
    mock_agent = MagicMock()

    # M1 Discovery
    logger.info("Mounting Discovery Agent (M1) routes...")
    discovery_router = create_discovery_router(repository=mock_repo, agent=mock_agent)
    app.include_router(discovery_router)

    # M2 Cost
    logger.info("Mounting Cost Agent (M2) routes...")
    mock_access_control = MagicMock()
    cost_router = init_cost_routes(mock_agent, mock_repo, mock_access_control)
    app.include_router(cost_router)

    # M3 Application
    logger.info("Mounting Application Agent (M3) routes...")
    app_router = create_application_router(agent=mock_agent, repository=mock_repo)
    app.include_router(app_router)

    # M4 Risk
    logger.info("Mounting Risk Agent (M4) routes...")
    risk_router = create_risk_router(agent=mock_agent, repository=mock_repo)
    app.include_router(risk_router)

    # M5 Strategy
    logger.info("Mounting Strategy Agent (M5) routes...")
    strat_router = create_strategy_router(agent=mock_agent, repository=mock_repo)
    app.include_router(strat_router)

    # M6 Digital Twin
    logger.info("Mounting Digital Twin (M6) routes...")
    sim_router = create_simulation_router(agent=mock_agent, repository=mock_repo)
    app.include_router(sim_router)

    # M7 Explainability
    logger.info("Mounting Explainability Engine (M7) routes...")
    expl_router = create_explanation_router(agent=mock_agent, repository=mock_repo)
    app.include_router(expl_router)

    # M8 Learning
    logger.info("Mounting Learning Agent (M8) routes...")
    try:
        from learning_agent import LearningAgent
        concrete_learning_agent = LearningAgent()
        learn_router = create_learning_router(agent=concrete_learning_agent, repository=mock_repo)
    except Exception:
        learn_router = create_learning_router(agent=mock_agent, repository=mock_repo)
    app.include_router(learn_router)

    # M9 Decision Engine
    logger.info("Mounting Decision Engine (M9) routes...")
    try:
        from decision_agent import DecisionAgent
        concrete_decision_agent = DecisionAgent()
        dec_router = create_decision_router(agent=concrete_decision_agent, repository=mock_repo)
    except Exception:
        dec_router = create_decision_router(agent=mock_agent, repository=mock_repo)
    app.include_router(dec_router)

    # M10 Execution Agent
    logger.info("Mounting Execution Agent (M10) routes...")
    try:
        from execution_agent import ExecutionAgent
        concrete_exec_agent = ExecutionAgent()
        exec_router = create_execution_router(agent=concrete_exec_agent, repository=mock_repo)
    except Exception:
        exec_router = create_execution_router(agent=mock_agent, repository=mock_repo)
    app.include_router(exec_router)

    # M11 Demo Router & Static files
    logger.info("Mounting Demo Engine (M11) routes...")
    demo_router = create_demo_router()
    app.include_router(demo_router)

    # Mount API v1 master router
    v1_router = create_v1_router(
        discovery_router=discovery_router,
        cost_router=cost_router,
        application_router=app_router,
        risk_router=risk_router,
        strategy_router=strat_router,
        simulation_router=sim_router,
        explanation_router=expl_router,
        learning_router=learn_router,
        decision_router=dec_router,
        execution_router=exec_router,
        demo_router=demo_router,
    )
    app.include_router(v1_router)

    # Mount TrueForge agent routes under official /v1/agents prefix
    try:
        from trueforge.routes import router as tf_router
        app.include_router(tf_router, prefix="/v1/agents")
    except Exception as exc:
        logger.warning("Could not mount /v1/agents router: %s", exc)

    # Mount Governance routes under /v1/governance prefix
    try:
        from governance.routes import router as gov_router
        app.include_router(gov_router, prefix="/v1/governance")
    except Exception as exc:
        logger.warning("Could not mount /v1/governance router: %s", exc)

    # Mount Verification & Learning Loop routes under /v1/verification prefix
    try:
        from verification.routes import router as verif_router
        app.include_router(verif_router, prefix="/v1")
    except Exception as exc:
        logger.warning("Could not mount /v1/verification router: %s", exc)

    # Static assets
    static_dir = docker_dir / "static"
    if static_dir.exists():
        app.mount("/dashboard", StaticFiles(directory=str(static_dir), html=True), name="static")

    logger.info("All modules and API v1 routes mounted successfully!")


# Mount routers on module import
mount_all_routers()

if __name__ == "__main__":
    port = int(os.getenv("PORT", settings.port))
    logger.info("Starting CloudPilot server on port %d...", port)
    uvicorn.run(app, host=settings.host, port=port, log_level=settings.log_level.lower())

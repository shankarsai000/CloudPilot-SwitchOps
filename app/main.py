"""
CloudPilot SwitchOps — Main FastAPI Application Entrypoint

Initializes the modular monolith:
- Enforces environment validation via Pydantic Settings
- Configures structured JSON logging
- Sets up SQLite persistence repository
- Configures Switch wire adapter / emulated bridge
- Exposes health probes and task lifecycle API
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import (
    get_repository as health_get_repo,
)
from app.api.health import (
    get_switch_adapter as health_get_adapter,
)
from app.api.health import (
    router as health_router,
)
from app.api.tasks import (
    get_task_service as tasks_get_service,
)
from app.api.tasks import (
    router as tasks_router,
)
from app.api.assessments import (
    get_repository as assessments_get_repo,
    get_task_service as assessments_get_service,
    router as assessments_router,
)
from app.core.config import Settings, get_settings
from app.core.errors import CloudPilotError
from app.core.logging import (
    configure_logging,
    get_logger,
    set_correlation_id,
)
from app.integrations.switch.client import SwitchAdapterInterface, SwitchWireClient
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.persistence.repository import (
    SQLiteTaskRepository,
    TaskRepositoryInterface,
)
from app.services.task_service import TaskService

logger = get_logger("cloudpilot.main")

# Global application dependencies
_repository: TaskRepositoryInterface | None = None
_switch_adapter: SwitchAdapterInterface | None = None
_task_service: TaskService | None = None
_switch_listener_task: asyncio.Task | None = None


def get_repository() -> TaskRepositoryInterface:
    assert _repository is not None, "Repository has not been initialized."
    return _repository


def get_switch_adapter() -> SwitchAdapterInterface:
    assert _switch_adapter is not None, "Switch adapter has not been initialized."
    return _switch_adapter


def get_task_service() -> TaskService:
    assert _task_service is not None, "Task service has not been initialized."
    return _task_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: setup database, initialize adapters, start listeners."""
    global _repository, _switch_adapter, _task_service, _switch_listener_task
    settings = get_settings()

    logger.info("Initializing CloudPilot SwitchOps v%s...", settings.app_version)

    # 1. Initialize SQLite persistence
    db_path = settings.database_url
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    _repository = SQLiteTaskRepository(db_path=db_path)

    # 2. Initialize Switch adapter
    # If explicitly running in testing or mock mode, use EmulatedSwitchBridge
    if settings.is_testing or settings.environment == "development" and not settings.switch_agent_api_key:
        logger.info("Using EmulatedSwitchBridge for local development/testing.")
        mock_bridge = EmulatedSwitchBridge()
        _switch_adapter = mock_bridge
    else:
        logger.info("Connecting to Switch Agent Bridge at %s", settings.switch_bridge_url)
        _switch_adapter = SwitchWireClient(
            bridge_url=settings.switch_bridge_url or "http://localhost:8080",
            agent_id=settings.switch_agent_id,
            agent_api_key=settings.switch_agent_api_key.get_secret_value() if settings.switch_agent_api_key else None,
        )

    # 3. Initialize Task Service
    _task_service = TaskService(repository=_repository, switch_adapter=_switch_adapter)

    # 4. Bind dependency overrides to API routers
    app.dependency_overrides[health_get_repo] = get_repository
    app.dependency_overrides[health_get_adapter] = get_switch_adapter
    app.dependency_overrides[tasks_get_service] = get_task_service
    app.dependency_overrides[assessments_get_repo] = get_repository
    app.dependency_overrides[assessments_get_service] = get_task_service

    # 5. Start background listener if live Switch connection is available
    if isinstance(_switch_adapter, SwitchWireClient) and settings.switch_agent_api_key:
        logger.info("Starting background Switch WebSocket listener for room: %s", settings.switch_room_id)
        _switch_listener_task = asyncio.create_task(
            _switch_adapter.listen_events(
                room_id=settings.switch_room_id,
                on_event=_task_service.handle_switch_event,
            )
        )

    logger.info("CloudPilot SwitchOps startup complete.")
    yield

    # Shutdown
    logger.info("Shutting down CloudPilot SwitchOps...")
    if _switch_listener_task:
        _switch_listener_task.cancel()
        try:
            await _switch_listener_task
        except asyncio.CancelledError:
            pass
    logger.info("CloudPilot SwitchOps shutdown complete.")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI application instance."""
    app_settings = settings or get_settings()

    # Configure structured logging
    configure_logging(level=app_settings.log_level, log_format=app_settings.log_format)

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description="CloudPilot SwitchOps — Autonomous Cloud Operations Control Room for Switch AI",
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Correlation ID & Request Logging Middleware
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        corr_id = request.headers.get("X-Correlation-ID") or request.headers.get("x-request-id")
        if not corr_id:
            import uuid
            corr_id = f"req-{uuid.uuid4().hex[:12]}"
        set_correlation_id(corr_id)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        return response

    # Global Exception Handler for CloudPilotError
    @app.exception_handler(CloudPilotError)
    async def cloudpilot_exception_handler(request: Request, exc: CloudPilotError) -> JSONResponse:
        logger.error("CloudPilotError encountered: %s (code=%s)", exc.message, exc.code)
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    # Mount API routers
    app.include_router(health_router)
    app.include_router(tasks_router)
    app.include_router(assessments_router)

    return app


app = create_app()

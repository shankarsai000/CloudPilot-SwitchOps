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
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.health import (
    get_repository as health_get_repo,
    get_switch_adapter as health_get_adapter,
    get_switch_connection_manager as health_get_conn_manager,
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
from app.api.decisions import (
    get_repository as decisions_get_repo,
    get_task_service as decisions_get_service,
    router as decisions_router,
)
from app.api.approvals import (
    get_repository as approvals_get_repo,
    router as approvals_router,
)
from app.api.executions import (
    get_repository as executions_get_repo,
    router as executions_router,
)
from app.core.config import Settings, get_settings
from app.core.errors import CloudPilotError
from app.core.logging import (
    configure_logging,
    get_logger,
    set_correlation_id,
)
from app.integrations.switch.adapter import create_switch_integration
from app.integrations.switch.client import SwitchAdapterInterface, SwitchWireClient
from app.integrations.switch.connection_manager import SwitchConnectionManager
from app.integrations.switch.event_handler import SwitchEventHandler
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
_switch_connection_manager: SwitchConnectionManager | None = None
_switch_event_handler: SwitchEventHandler | None = None
_task_service: TaskService | None = None
_switch_listener_task: asyncio.Task | None = None


def get_repository() -> TaskRepositoryInterface:
    assert _repository is not None, "Repository has not been initialized."
    return _repository


def get_switch_adapter() -> SwitchAdapterInterface:
    assert _switch_adapter is not None, "Switch adapter has not been initialized."
    return _switch_adapter


def get_switch_connection_manager() -> SwitchConnectionManager | None:
    return _switch_connection_manager


def get_task_service() -> TaskService:
    assert _task_service is not None, "Task service has not been initialized."
    return _task_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: setup database, initialize adapters, start listeners."""
    global _repository, _switch_adapter, _switch_connection_manager, _switch_event_handler, _task_service, _switch_listener_task
    settings = get_settings()

    logger.info("Initializing CloudPilot SwitchOps v%s...", settings.app_version)

    # 1. Initialize SQLite persistence
    db_path = settings.database_url
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    _repository = SQLiteTaskRepository(db_path=db_path)

    # 2. Initialize Switch adapter, connection manager, and event handler
    _switch_adapter, _switch_connection_manager = create_switch_integration(settings)
    _switch_event_handler = SwitchEventHandler()

    # 3. Initialize Task Service
    _task_service = TaskService(
        repository=_repository,
        switch_adapter=_switch_adapter,
        connection_manager=_switch_connection_manager,
        event_handler=_switch_event_handler,
    )

    # 4. Bind dependency overrides to API routers
    app.dependency_overrides[health_get_repo] = get_repository
    app.dependency_overrides[health_get_adapter] = get_switch_adapter
    app.dependency_overrides[health_get_conn_manager] = get_switch_connection_manager
    app.dependency_overrides[tasks_get_service] = get_task_service
    app.dependency_overrides[assessments_get_repo] = get_repository
    app.dependency_overrides[assessments_get_service] = get_task_service
    app.dependency_overrides[decisions_get_repo] = get_repository
    app.dependency_overrides[decisions_get_service] = get_task_service
    app.dependency_overrides[approvals_get_repo] = get_repository
    app.dependency_overrides[executions_get_repo] = get_repository

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
    app.include_router(decisions_router)
    app.include_router(approvals_router)
    app.include_router(executions_router)

    # Mount unified frontend dashboard
    static_dir = Path(__file__).resolve().parent.parent / "docker" / "static"
    if static_dir.exists():
        app.mount("/dashboard", StaticFiles(directory=str(static_dir), html=True), name="dashboard")

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/dashboard")

    return app


app = create_app()

if __name__ == "__main__":
    import socket
    import uvicorn

    settings = get_settings()
    port = settings.port

    def is_port_in_use(p: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((settings.host, p))
                return False
            except OSError:
                return True

    if is_port_in_use(port):
        for candidate_port in range(port + 1, port + 20):
            if not is_port_in_use(candidate_port):
                logger.warning(
                    "Port %d is already in use by another process. Falling back to port %d.",
                    port,
                    candidate_port,
                )
                port = candidate_port
                break

    print(f"\n==================================================================")
    print(f"  CLOUDPILOT SWITCHOPS CONTROL ROOM ACTIVE")
    print(f"  Dashboard: http://localhost:{port}/dashboard")
    print(f"  API Docs:  http://localhost:{port}/docs")
    print(f"==================================================================\n")

    uvicorn.run("app.main:app", host=settings.host, port=port, reload=settings.debug)



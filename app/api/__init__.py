"""CloudPilot SwitchOps API package."""

from app.api.health import router as health_router
from app.api.tasks import router as tasks_router

__all__ = ["health_router", "tasks_router"]

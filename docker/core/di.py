"""
Centralized FastAPI Dependency Injection providers.
"""

from typing import Any, Generator
from fastapi import Depends
from sqlalchemy.orm import Session

from core.config import Settings, get_settings
from core.database.connection import get_db
from core.events.bus import EventBus, get_event_bus
from core.observability.metrics import MetricsCollector, get_metrics_collector
from core.redis.client import get_redis


def get_settings_dependency() -> Settings:
    """Dependency provider for cached platform settings."""
    return get_settings()


def get_db_session(session: Session = Depends(get_db)) -> Generator[Session, None, None]:
    """Dependency provider for transactional SQLAlchemy database session."""
    yield session


def get_redis_instance(client: Any = Depends(get_redis)) -> Any:
    """Dependency provider for Redis client / in-memory fallback."""
    return client


def get_event_bus_instance() -> EventBus:
    """Dependency provider for platform EventBus."""
    return get_event_bus()


def get_metrics_instance() -> MetricsCollector:
    """Dependency provider for platform metrics collector."""
    return get_metrics_collector()

"""
Database connection, session management, and health checking.
"""

import time
import logging
from typing import Generator, Optional
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

from core.config import get_settings

logger = logging.getLogger("cloudpilot.database")

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


class DatabaseHealthStatus(BaseModel):
    """Database connectivity and readiness status."""
    connected: bool
    latency_ms: Optional[float] = None
    database_type: str
    details: Optional[str] = None


def get_engine() -> Engine:
    """Initialize or return the cached SQLAlchemy Engine instance."""
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    db_url = settings.database_url

    connect_args = {}
    if db_url.startswith("sqlite"):
        # SQLite in-memory or file configuration for test / dev
        connect_args["check_same_thread"] = False
        poolclass = StaticPool if ":memory:" in db_url else NullPool
        _engine = create_engine(
            db_url,
            connect_args=connect_args,
            poolclass=poolclass,
            echo=settings.debug,
        )
    else:
        # PostgreSQL with production QueuePool
        _engine = create_engine(
            db_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=True,  # Test connections before checkout
            echo=settings.debug,
        )

    logger.info("Initialized SQLAlchemy engine for: %s", db_url.split("@")[-1] if "@" in db_url else db_url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return configured SQLAlchemy sessionmaker instance."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    engine = get_engine()
    _session_factory = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a transactional database session.
    Automatically commits on success or rolls back on exceptions.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Database session rolled back due to error: %s", exc)
        raise
    finally:
        session.close()


def check_database_health() -> DatabaseHealthStatus:
    """
    Perform an active health check ping (SELECT 1) against the database.
    Measures latency and catches connectivity issues.
    """
    settings = get_settings()
    db_type = "sqlite" if settings.database_url.startswith("sqlite") else "postgresql"
    start_time = time.perf_counter()

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start_time) * 1000.0
        return DatabaseHealthStatus(
            connected=True,
            latency_ms=round(latency, 2),
            database_type=db_type,
            details="Database operational",
        )
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return DatabaseHealthStatus(
            connected=False,
            latency_ms=None,
            database_type=db_type,
            details=str(exc),
        )

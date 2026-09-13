"""
Redis client management, caching, in-memory fallback, and idempotency locking.
"""

import time
import logging
from contextlib import contextmanager
from typing import Any, Generator, Optional
from pydantic import BaseModel

from core.config import get_settings

logger = logging.getLogger("cloudpilot.redis")

_redis_client = None


class RedisHealthStatus(BaseModel):
    """Status report for Redis connectivity."""
    connected: bool
    latency_ms: Optional[float] = None
    is_fallback: bool = False
    details: Optional[str] = None


class InMemoryRedisFallback:
    """
    Transparent in-memory key-value fallback when live Redis server is unavailable.
    Guarantees that test suites and local development work out-of-the-box.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._expires: dict[str, float] = {}

    def get(self, name: str) -> Optional[str]:
        self._cleanup(name)
        val = self._store.get(name)
        return str(val) if val is not None else None

    def set(self, name: str, value: Any, ex: Optional[int] = None) -> bool:
        self._store[name] = value
        if ex:
            self._expires[name] = time.time() + ex
        else:
            self._expires.pop(name, None)
        return True

    def delete(self, *names: str) -> int:
        count = 0
        for name in names:
            if name in self._store:
                del self._store[name]
                self._expires.pop(name, None)
                count += 1
        return count

    def exists(self, *names: str) -> int:
        count = 0
        for name in names:
            self._cleanup(name)
            if name in self._store:
                count += 1
        return count

    def expire(self, name: str, time_sec: int) -> bool:
        if name in self._store:
            self._expires[name] = time.time() + time_sec
            return True
        return False

    def ping(self) -> bool:
        return True

    def flushdb(self) -> bool:
        self._store.clear()
        self._expires.clear()
        return True

    def _cleanup(self, name: str) -> None:
        exp = self._expires.get(name)
        if exp and time.time() > exp:
            self._store.pop(name, None)
            self._expires.pop(name, None)


def get_redis_client() -> Any:
    """
    Initialize or return the cached Redis client.
    Falls back to InMemoryRedisFallback if Redis cannot be reached.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    settings = get_settings()

    try:
        import redis
        client = redis.Redis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            decode_responses=True,
        )
        # Verify connection with quick ping
        client.ping()
        logger.info("Connected to Redis at: %s", settings.redis_url)
        _redis_client = client
        return _redis_client
    except Exception as exc:
        logger.warning(
            "Live Redis unavailable at %s (%s). Engaging InMemoryRedisFallback.",
            settings.redis_url,
            exc,
        )
        _redis_client = InMemoryRedisFallback()
        return _redis_client


def get_redis() -> Generator[Any, None, None]:
    """FastAPI dependency for accessing Redis client."""
    client = get_redis_client()
    yield client


def check_redis_health() -> RedisHealthStatus:
    """
    Perform active ping against Redis and compute round-trip latency.
    """
    start_time = time.perf_counter()
    try:
        client = get_redis_client()
        is_fallback = isinstance(client, InMemoryRedisFallback)
        client.ping()
        latency = (time.perf_counter() - start_time) * 1000.0
        return RedisHealthStatus(
            connected=True,
            latency_ms=round(latency, 2),
            is_fallback=is_fallback,
            details="Operational (Fallback Mode)" if is_fallback else "Operational",
        )
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return RedisHealthStatus(
            connected=False,
            latency_ms=None,
            is_fallback=False,
            details=str(exc),
        )


@contextmanager
def idempotency_lock(key: str, ttl_seconds: int = 60) -> Generator[bool, None, None]:
    """
    Distributed lock context manager to guarantee idempotent operations.
    Yields True if lock was acquired, False if concurrent operation in progress.
    """
    client = get_redis_client()
    lock_key = f"lock:{key}"
    token = str(time.time())

    acquired = False
    try:
        # Simple atomic lock via SET NX
        if hasattr(client, "set"):
            if isinstance(client, InMemoryRedisFallback):
                if not client.exists(lock_key):
                    client.set(lock_key, token, ex=ttl_seconds)
                    acquired = True
            else:
                acquired = bool(client.set(lock_key, token, nx=True, ex=ttl_seconds))
        yield acquired
    finally:
        if acquired:
            try:
                client.delete(lock_key)
            except Exception as e:
                logger.warning("Failed to release lock %s: %s", lock_key, e)

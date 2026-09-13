"""
Action Locks & Idempotency Management.

Ensures:
- Mutual exclusion on cloud resources during operations (ActionLockManager)
- Elimination of duplicate/replay executions (IdempotencyManager)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import threading
from typing import Any, Dict, List, Optional
import uuid

from governance.models import ActionLock, IdempotencyRecord


class ActionLockManager:
    """
    Thread-safe resource-level locking system.
    Prevents concurrent modifications on the same target resource.
    """

    def __init__(self, default_ttl_seconds: int = 300) -> None:
        self._default_ttl_seconds = default_ttl_seconds
        self._locks: Dict[str, ActionLock] = {}
        self._mutex = threading.Lock()

    def acquire_lock(
        self,
        resource_id: str,
        action_type: str,
        held_by: str,
        ttl_seconds: Optional[int] = None,
    ) -> Optional[ActionLock]:
        """
        Attempt to acquire an exclusive lock on a resource.
        Returns ActionLock if successful, None if resource is already locked.
        """
        ttl = ttl_seconds or self._default_ttl_seconds
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)

        with self._mutex:
            self._purge_expired_locks_locked(now)

            existing = self._locks.get(resource_id)
            if existing and existing.expires_at > now:
                if existing.held_by == held_by:
                    # Re-entrant: extend lock
                    existing.expires_at = expires_at
                    return existing
                return None

            lock = ActionLock(
                lock_id=f"lck-{uuid.uuid4().hex[:8]}",
                resource_id=resource_id,
                action_type=action_type,
                held_by=held_by,
                acquired_at=now,
                expires_at=expires_at,
            )
            self._locks[resource_id] = lock
            return lock

    def release_lock(self, resource_id: str, held_by: Optional[str] = None) -> bool:
        """Release an acquired lock on a resource."""
        with self._mutex:
            existing = self._locks.get(resource_id)
            if not existing:
                return False
            if held_by and existing.held_by != held_by:
                return False
            del self._locks[resource_id]
            return True

    def is_locked(self, resource_id: str) -> bool:
        """Check if a resource currently has an active, unexpired lock."""
        now = datetime.now(timezone.utc)
        with self._mutex:
            self._purge_expired_locks_locked(now)
            return resource_id in self._locks

    def get_lock(self, resource_id: str) -> Optional[ActionLock]:
        """Get active lock details for a resource."""
        now = datetime.now(timezone.utc)
        with self._mutex:
            self._purge_expired_locks_locked(now)
            return self._locks.get(resource_id)

    def list_active_locks(self) -> List[ActionLock]:
        """Return all active, unexpired locks."""
        now = datetime.now(timezone.utc)
        with self._mutex:
            self._purge_expired_locks_locked(now)
            return list(self._locks.values())

    def clear_all(self) -> None:
        """Clear all locks (used in tests or emergency reset)."""
        with self._mutex:
            self._locks.clear()

    def _purge_expired_locks_locked(self, now: datetime) -> None:
        expired = [rid for rid, lck in self._locks.items() if lck.expires_at <= now]
        for rid in expired:
            del self._locks[rid]


class IdempotencyManager:
    """
    Idempotency registry to prevent duplicate executions of identical actions.
    Generates deterministic SHA-256 keys and caches execution results.
    """

    def __init__(self, default_ttl_seconds: int = 3600) -> None:
        self._default_ttl_seconds = default_ttl_seconds
        self._cache: Dict[str, IdempotencyRecord] = {}
        self._mutex = threading.Lock()

    def generate_key(
        self,
        action_type: str,
        target_resource_id: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate deterministic idempotency key for an action."""
        params_serialized = json.dumps(parameters or {}, sort_keys=True, default=str)
        raw = f"{action_type}:{target_resource_id}:{params_serialized}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def check_idempotency(self, idempotency_key: str) -> Optional[IdempotencyRecord]:
        """
        Check if an action with this key has already been executed.
        Returns cached IdempotencyRecord if valid and unexpired, else None.
        """
        now = datetime.now(timezone.utc)
        with self._mutex:
            self._purge_expired_locked(now)
            record = self._cache.get(idempotency_key)
            if record and record.expires_at > now:
                return record
            return None

    def record_execution(
        self,
        idempotency_key: str,
        action_id: str,
        status: str,
        result_data: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> IdempotencyRecord:
        """Cache execution result under the idempotency key."""
        ttl = ttl_seconds or self._default_ttl_seconds
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)

        record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            action_id=action_id,
            status=status,
            result_data=result_data,
            created_at=now,
            expires_at=expires_at,
        )
        with self._mutex:
            self._cache[idempotency_key] = record
        return record

    def clear_all(self) -> None:
        with self._mutex:
            self._cache.clear()

    def _purge_expired_locked(self, now: datetime) -> None:
        expired = [k for k, r in self._cache.items() if r.expires_at <= now]
        for k in expired:
            del self._cache[k]


_lock_manager_instance: Optional[ActionLockManager] = None
_idempotency_manager_instance: Optional[IdempotencyManager] = None


def get_action_lock_manager() -> ActionLockManager:
    global _lock_manager_instance
    if _lock_manager_instance is None:
        _lock_manager_instance = ActionLockManager()
    return _lock_manager_instance


def get_idempotency_manager() -> IdempotencyManager:
    global _idempotency_manager_instance
    if _idempotency_manager_instance is None:
        _idempotency_manager_instance = IdempotencyManager()
    return _idempotency_manager_instance

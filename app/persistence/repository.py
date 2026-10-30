"""
CloudPilot SwitchOps — Persistence Layer & Repository Interfaces

Provides abstract repository contracts and clean, thread-safe SQLite and
in-memory implementations for task metadata, append-only events, and evidence.
"""

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.core.errors import TaskConflictError, TaskNotFoundError
from app.domain.models import (
    ActorType,
    Evidence,
    EvidenceSeverity,
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
)


class TaskRepositoryInterface(ABC):
    """Abstract contract for persisting CloudPilot task metadata and audit events."""

    @abstractmethod
    def save_task(self, task: Task) -> Task:
        """Create a new task. Raises TaskConflictError if task_id already exists."""

    @abstractmethod
    def get_task(self, task_id: str) -> Task | None:
        """Retrieve task by task_id."""

    @abstractmethod
    def update_task(self, task: Task) -> Task:
        """Update existing task state. Raises TaskNotFoundError if task does not exist."""

    @abstractmethod
    def list_tasks(
        self,
        status: TaskStatus | None = None,
        room_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks with optional status and room filtering."""

    @abstractmethod
    def append_event(self, event: TaskEvent) -> TaskEvent:
        """Append an immutable audit event to the task log."""

    @abstractmethod
    def get_events_for_task(self, task_id: str) -> list[TaskEvent]:
        """Retrieve full chronological event history for a task."""

    @abstractmethod
    def save_evidence(self, evidence: Evidence) -> Evidence:
        """Persist an evidence finding."""

    @abstractmethod
    def get_evidence_for_task(self, task_id: str) -> list[Evidence]:
        """Retrieve all evidence associated with a task."""


class InMemoryTaskRepository(TaskRepositoryInterface):
    """Fast, thread-safe in-memory repository for unit testing."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, Task] = {}
        self._events: dict[str, list[TaskEvent]] = {}
        self._evidence: dict[str, list[Evidence]] = {}

    def save_task(self, task: Task) -> Task:
        with self._lock:
            if task.task_id in self._tasks:
                raise TaskConflictError(task.task_id)
            self._tasks[task.task_id] = task.model_copy(deep=True)
            if task.task_id not in self._events:
                self._events[task.task_id] = []
            return task.model_copy(deep=True)

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.model_copy(deep=True) if task else None

    def update_task(self, task: Task) -> Task:
        with self._lock:
            if task.task_id not in self._tasks:
                raise TaskNotFoundError(task.task_id)
            self._tasks[task.task_id] = task.model_copy(deep=True)
            return task.model_copy(deep=True)

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        room_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        with self._lock:
            results = list(self._tasks.values())
            if status:
                results = [t for t in results if t.status == status]
            if room_id:
                results = [t for t in results if t.room_id == room_id]
            results.sort(key=lambda t: t.created_at, reverse=True)
            return [t.model_copy(deep=True) for t in results[offset : offset + limit]]

    def append_event(self, event: TaskEvent) -> TaskEvent:
        with self._lock:
            if event.task_id not in self._events:
                self._events[event.task_id] = []
            self._events[event.task_id].append(event.model_copy(deep=True))
            return event.model_copy(deep=True)

    def get_events_for_task(self, task_id: str) -> list[TaskEvent]:
        with self._lock:
            events = self._events.get(task_id, [])
            return [e.model_copy(deep=True) for e in events]

    def save_evidence(self, evidence: Evidence) -> Evidence:
        with self._lock:
            tid = evidence.task_id or "unassigned"
            if tid not in self._evidence:
                self._evidence[tid] = []
            self._evidence[tid].append(evidence.model_copy(deep=True))
            return evidence.model_copy(deep=True)

    def get_evidence_for_task(self, task_id: str) -> list[Evidence]:
        with self._lock:
            items = self._evidence.get(task_id, [])
            return [e.model_copy(deep=True) for e in items]


class SQLiteTaskRepository(TaskRepositoryInterface):
    """
    Robust SQLite-backed persistence repository with connection synchronization,
    schema initialization, and strict transactional boundaries.
    """

    def __init__(self, db_path: str = "cloudpilot_tasks.db") -> None:
        if db_path.startswith("sqlite:///"):
            self.db_path = db_path.replace("sqlite:///", "", 1)
        else:
            self.db_path = db_path

        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._init_db()

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON;")
        return self._conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    room_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_room_id ON tasks(room_id);

                CREATE TABLE IF NOT EXISTS task_events (
                    event_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_events_task_id ON task_events(task_id);

                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    source_type TEXT NOT NULL,
                    source_reference TEXT NOT NULL,
                    finding_category TEXT NOT NULL,
                    observed_value_json TEXT NOT NULL,
                    expected_value_json TEXT,
                    severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    confidence REAL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_task_id ON evidence(task_id);
                """
            )
            conn.commit()

    def save_task(self, task: Task) -> Task:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO tasks (
                        task_id, task_type, title, description, room_id,
                        requested_by, status, created_at, updated_at,
                        correlation_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.task_type,
                        task.title,
                        task.description,
                        task.room_id,
                        task.requested_by,
                        task.status.value,
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                        task.correlation_id,
                        json.dumps(task.metadata),
                    ),
                )
                conn.commit()
                return task
            except sqlite3.IntegrityError:
                raise TaskConflictError(task.task_id)

    def get_task(self, task_id: str) -> Task | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def update_task(self, task: Task) -> Task:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tasks
                SET task_type = ?, title = ?, description = ?, room_id = ?,
                    requested_by = ?, status = ?, updated_at = ?,
                    correlation_id = ?, metadata_json = ?
                WHERE task_id = ?
                """,
                (
                    task.task_type,
                    task.title,
                    task.description,
                    task.room_id,
                    task.requested_by,
                    task.status.value,
                    task.updated_at.isoformat(),
                    task.correlation_id,
                    json.dumps(task.metadata),
                    task.task_id,
                ),
            )
            if cursor.rowcount == 0:
                raise TaskNotFoundError(task.task_id)
            conn.commit()
            return task

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        room_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        with self._lock, self._get_connection() as conn:
            query = "SELECT * FROM tasks WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status.value)
            if room_id:
                query += " AND room_id = ?"
                params.append(room_id)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def append_event(self, event: TaskEvent) -> TaskEvent:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO task_events (
                    event_id, task_id, event_type, actor_id, actor_type,
                    timestamp, correlation_id, payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.task_id,
                    event.event_type.value,
                    event.actor_id,
                    event.actor_type.value,
                    event.timestamp.isoformat(),
                    event.correlation_id,
                    json.dumps(event.payload),
                    event.schema_version,
                ),
            )
            conn.commit()
            return event

    def get_events_for_task(self, task_id: str) -> list[TaskEvent]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM task_events WHERE task_id = ? ORDER BY timestamp ASC",
                (task_id,),
            ).fetchall()
            return [self._row_to_event(row) for row in rows]

    def save_evidence(self, evidence: Evidence) -> Evidence:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO evidence (
                    evidence_id, task_id, source_type, source_reference,
                    finding_category, observed_value_json, expected_value_json,
                    severity, timestamp, provenance_json, confidence, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.evidence_id,
                    evidence.task_id,
                    evidence.source_type,
                    evidence.source_reference,
                    evidence.finding_category,
                    json.dumps(evidence.observed_value),
                    json.dumps(evidence.expected_value) if evidence.expected_value is not None else None,
                    evidence.severity.value,
                    evidence.timestamp.isoformat(),
                    json.dumps(evidence.provenance),
                    evidence.confidence,
                    evidence.schema_version,
                ),
            )
            conn.commit()
            return evidence

    def get_evidence_for_task(self, task_id: str) -> list[Evidence]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE task_id = ? ORDER BY timestamp ASC",
                (task_id,),
            ).fetchall()
            return [self._row_to_evidence(row) for row in rows]

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            task_id=row["task_id"],
            task_type=row["task_type"],
            title=row["title"],
            description=row["description"],
            room_id=row["room_id"],
            requested_by=row["requested_by"],
            status=TaskStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            correlation_id=row["correlation_id"],
            metadata=json.loads(row["metadata_json"]),
        )

    def _row_to_event(self, row: sqlite3.Row) -> TaskEvent:
        return TaskEvent(
            event_id=row["event_id"],
            task_id=row["task_id"],
            event_type=TaskEventType(row["event_type"]),
            actor_id=row["actor_id"],
            actor_type=ActorType(row["actor_type"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            correlation_id=row["correlation_id"],
            payload=json.loads(row["payload_json"]),
            schema_version=row["schema_version"],
        )

    def _row_to_evidence(self, row: sqlite3.Row) -> Evidence:
        return Evidence(
            evidence_id=row["evidence_id"],
            task_id=row["task_id"],
            source_type=row["source_type"],
            source_reference=row["source_reference"],
            finding_category=row["finding_category"],
            observed_value=json.loads(row["observed_value_json"]),
            expected_value=json.loads(row["expected_value_json"]) if row["expected_value_json"] else None,
            severity=EvidenceSeverity(row["severity"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            provenance=json.loads(row["provenance_json"]),
            confidence=row["confidence"],
            schema_version=row["schema_version"],
        )

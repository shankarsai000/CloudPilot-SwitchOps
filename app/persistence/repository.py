"""
CloudPilot SwitchOps — Persistence Layer & Repository Interfaces

Provides abstract repository contracts and clean, thread-safe SQLite and
in-memory implementations for task metadata, append-only events, evidence,
discovered inventory, findings, and consolidated assessments.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from app.core.errors import TaskConflictError, TaskNotFoundError
from app.domain.candidates import Candidate
from app.domain.decisions import (
    CandidateEvaluation,
    CandidateInteraction,
    DecisionReport,
    DecisionRun,
    InteractionType,
    ParetoStatus,
)
from app.domain.objectives import PreferenceProfile
from app.domain.policies import PolicyConfiguration
from app.domain.finding import (
    AssessmentSummary,
    Finding,
    FindingCategory,
    FindingSeverity,
)
from app.domain.inventory import (
    DiscoveredResource,
    InfrastructureInventory,
    ResourceCategory,
)
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
    """Abstract contract for persisting CloudPilot task metadata, audit events, findings, and assessments."""

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

    @abstractmethod
    def save_finding(self, finding: Finding) -> Finding:
        """Persist a specialist finding."""

    @abstractmethod
    def get_findings_for_task(
        self,
        task_id: str,
        category: Optional[FindingCategory] = None,
    ) -> list[Finding]:
        """Retrieve findings associated with a task, optionally filtered by category."""

    @abstractmethod
    def get_finding(self, finding_id: str) -> Finding | None:
        """Retrieve finding by unique finding identifier."""

    @abstractmethod
    def save_inventory(self, inventory: InfrastructureInventory) -> InfrastructureInventory:
        """Persist a discovered infrastructure inventory."""

    @abstractmethod
    def get_inventory_for_task(self, task_id: str) -> InfrastructureInventory | None:
        """Retrieve discovered infrastructure inventory for a task."""

    @abstractmethod
    def save_assessment(self, assessment: AssessmentSummary) -> AssessmentSummary:
        """Persist a consolidated assessment summary."""

    @abstractmethod
    def get_assessment_for_task(self, task_id: str) -> AssessmentSummary | None:
        """Retrieve consolidated assessment summary for a task."""

    @abstractmethod
    def save_decision_run(self, decision: DecisionRun) -> DecisionRun:
        """Persist a decision intelligence run."""

    @abstractmethod
    def get_decision_run(self, decision_id: str) -> DecisionRun | None:
        """Retrieve a decision run by its decision_id."""

    @abstractmethod
    def get_decision_run_for_task(self, task_id: str) -> DecisionRun | None:
        """Retrieve a decision run associated with a task."""

    @abstractmethod
    def save_candidate_evaluations(
        self, decision_id: str, evaluations: list[CandidateEvaluation]
    ) -> None:
        """Persist candidate evaluations for a decision run."""

    @abstractmethod
    def get_candidate_evaluations(
        self, decision_id: str
    ) -> list[CandidateEvaluation]:
        """Retrieve all candidate evaluations for a decision run."""

    @abstractmethod
    def save_interactions(
        self, decision_id: str, interactions: list[CandidateInteraction]
    ) -> None:
        """Persist candidate interactions/conflicts for a decision run."""

    @abstractmethod
    def get_interactions(
        self, decision_id: str
    ) -> list[CandidateInteraction]:
        """Retrieve candidate interactions/conflicts for a decision run."""

    @abstractmethod
    def save_decision_report(self, report: DecisionReport) -> DecisionReport:
        """Persist a consolidated engineering decision report."""

    @abstractmethod
    def get_decision_report(self, decision_id: str) -> DecisionReport | None:
        """Retrieve a decision report by its decision_id."""


class InMemoryTaskRepository(TaskRepositoryInterface):
    """Fast, thread-safe in-memory repository for unit testing."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, Task] = {}
        self._events: dict[str, list[TaskEvent]] = {}
        self._evidence: dict[str, list[Evidence]] = {}
        self._findings: dict[str, list[Finding]] = {}
        self._findings_by_id: dict[str, Finding] = {}
        self._inventories: dict[str, InfrastructureInventory] = {}
        self._assessments: dict[str, AssessmentSummary] = {}
        self._decision_runs: dict[str, DecisionRun] = {}
        self._decision_runs_by_task: dict[str, str] = {}
        self._evaluations_by_decision: dict[str, list[CandidateEvaluation]] = {}
        self._interactions_by_decision: dict[str, list[CandidateInteraction]] = {}
        self._decision_reports: dict[str, DecisionReport] = {}

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
            res: list[Task] = []
            for t in self._tasks.values():
                if status and t.status != status:
                    continue
                if room_id and t.room_id != room_id:
                    continue
                res.append(t.model_copy(deep=True))
            res.sort(key=lambda x: x.created_at)
            return res[offset : offset + limit]

    def append_event(self, event: TaskEvent) -> TaskEvent:
        with self._lock:
            if event.task_id not in self._events:
                self._events[event.task_id] = []
            self._events[event.task_id].append(event.model_copy(deep=True))
            return event.model_copy(deep=True)

    def get_events_for_task(self, task_id: str) -> list[TaskEvent]:
        with self._lock:
            evts = self._events.get(task_id, [])
            return [e.model_copy(deep=True) for e in evts]

    def save_evidence(self, evidence: Evidence) -> Evidence:
        with self._lock:
            tid = evidence.task_id or "unassigned"
            if tid not in self._evidence:
                self._evidence[tid] = []
            self._evidence[tid].append(evidence.model_copy(deep=True))
            return evidence.model_copy(deep=True)

    def get_evidence_for_task(self, task_id: str) -> list[Evidence]:
        with self._lock:
            evs = self._evidence.get(task_id, [])
            return [e.model_copy(deep=True) for e in evs]

    def save_finding(self, finding: Finding) -> Finding:
        with self._lock:
            tid = finding.task_id
            if tid not in self._findings:
                self._findings[tid] = []
            self._findings[tid].append(finding.model_copy(deep=True))
            self._findings_by_id[finding.finding_id] = finding.model_copy(deep=True)
            return finding.model_copy(deep=True)

    def get_findings_for_task(
        self,
        task_id: str,
        category: Optional[FindingCategory] = None,
    ) -> list[Finding]:
        with self._lock:
            fnds = self._findings.get(task_id, [])
            if category:
                fnds = [f for f in fnds if f.category == category]
            return [f.model_copy(deep=True) for f in fnds]

    def get_finding(self, finding_id: str) -> Finding | None:
        with self._lock:
            fnd = self._findings_by_id.get(finding_id)
            return fnd.model_copy(deep=True) if fnd else None

    def save_inventory(self, inventory: InfrastructureInventory) -> InfrastructureInventory:
        with self._lock:
            tid = inventory.task_id or "unassigned"
            self._inventories[tid] = inventory.model_copy(deep=True)
            return inventory.model_copy(deep=True)

    def get_inventory_for_task(self, task_id: str) -> InfrastructureInventory | None:
        with self._lock:
            inv = self._inventories.get(task_id)
            return inv.model_copy(deep=True) if inv else None

    def save_assessment(self, assessment: AssessmentSummary) -> AssessmentSummary:
        with self._lock:
            self._assessments[assessment.task_id] = assessment.model_copy(deep=True)
            return assessment.model_copy(deep=True)

    def get_assessment_for_task(self, task_id: str) -> AssessmentSummary | None:
        with self._lock:
            asm = self._assessments.get(task_id)
            return asm.model_copy(deep=True) if asm else None

    def save_decision_run(self, decision: DecisionRun) -> DecisionRun:
        with self._lock:
            self._decision_runs[decision.decision_id] = decision.model_copy(deep=True)
            self._decision_runs_by_task[decision.task_id] = decision.decision_id
            return decision.model_copy(deep=True)

    def get_decision_run(self, decision_id: str) -> DecisionRun | None:
        with self._lock:
            run = self._decision_runs.get(decision_id)
            return run.model_copy(deep=True) if run else None

    def get_decision_run_for_task(self, task_id: str) -> DecisionRun | None:
        with self._lock:
            dec_id = self._decision_runs_by_task.get(task_id)
            if not dec_id:
                return None
            return self.get_decision_run(dec_id)

    def save_candidate_evaluations(
        self, decision_id: str, evaluations: list[CandidateEvaluation]
    ) -> None:
        with self._lock:
            self._evaluations_by_decision[decision_id] = [
                e.model_copy(deep=True) for e in evaluations
            ]

    def get_candidate_evaluations(
        self, decision_id: str
    ) -> list[CandidateEvaluation]:
        with self._lock:
            evals = self._evaluations_by_decision.get(decision_id, [])
            return [e.model_copy(deep=True) for e in evals]

    def save_interactions(
        self, decision_id: str, interactions: list[CandidateInteraction]
    ) -> None:
        with self._lock:
            self._interactions_by_decision[decision_id] = [
                i.model_copy(deep=True) for i in interactions
            ]

    def get_interactions(
        self, decision_id: str
    ) -> list[CandidateInteraction]:
        with self._lock:
            ints = self._interactions_by_decision.get(decision_id, [])
            return [i.model_copy(deep=True) for i in ints]

    def save_decision_report(self, report: DecisionReport) -> DecisionReport:
        with self._lock:
            self._decision_reports[report.decision_id] = report.model_copy(deep=True)
            return report.model_copy(deep=True)

    def get_decision_report(self, decision_id: str) -> DecisionReport | None:
        with self._lock:
            rep = self._decision_reports.get(decision_id)
            return rep.model_copy(deep=True) if rep else None

    def close(self) -> None:
        pass


class SQLiteTaskRepository(TaskRepositoryInterface):
    """Production-grade, thread-safe SQLite implementation of TaskRepositoryInterface."""

    def __init__(self, db_path: str = "cloudpilot_tasks.db") -> None:
        clean_path = db_path
        if clean_path.startswith("sqlite:///"):
            clean_path = clean_path.replace("sqlite:///", "")
        self.db_path = clean_path
        self._lock = threading.RLock()
        self._local = threading.local()
        self._all_conns: list[sqlite3.Connection] = []
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            self._local.conn = conn
            with self._lock:
                self._all_conns.append(conn)
        return conn

    def close(self) -> None:
        with self._lock:
            for conn in self._all_conns:
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_conns.clear()
            if hasattr(self._local, "conn"):
                self._local.conn = None

    def _init_schema(self) -> None:
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

                CREATE TABLE IF NOT EXISTS findings (
                    finding_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    source_location TEXT,
                    observed_value_json TEXT NOT NULL,
                    expected_value_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    confidence REAL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_findings_task_id ON findings(task_id);
                CREATE INDEX IF NOT EXISTS idx_findings_category ON findings(category);
                CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);

                CREATE TABLE IF NOT EXISTS inventories (
                    inventory_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    workspace_root TEXT NOT NULL,
                    resources_json TEXT NOT NULL,
                    discovered_files_json TEXT NOT NULL,
                    discovery_duration_ms REAL,
                    created_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_inventories_task_id ON inventories(task_id);

                CREATE TABLE IF NOT EXISTS assessments (
                    assessment_id TEXT PRIMARY KEY,
                    task_id TEXT UNIQUE NOT NULL,
                    workspace_root TEXT NOT NULL,
                    total_resources INTEGER NOT NULL,
                    total_findings INTEGER NOT NULL,
                    critical_findings_count INTEGER NOT NULL,
                    high_findings_count INTEGER NOT NULL,
                    medium_findings_count INTEGER NOT NULL,
                    low_findings_count INTEGER NOT NULL,
                    estimated_monthly_cost TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    finops_summary TEXT,
                    secops_summary TEXT,
                    reliability_summary TEXT,
                    next_phase_recommendations_json TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_assessments_task_id ON assessments(task_id);

                CREATE TABLE IF NOT EXISTS decision_runs (
                    decision_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    assessment_id TEXT NOT NULL,
                    workspace_root TEXT NOT NULL,
                    policy_config_json TEXT NOT NULL,
                    preference_profile TEXT NOT NULL,
                    total_candidates_generated INTEGER NOT NULL,
                    feasible_candidates_count INTEGER NOT NULL,
                    rejected_candidates_count INTEGER NOT NULL,
                    pareto_optimal_count INTEGER NOT NULL,
                    recommended_candidate_id TEXT,
                    recommended_candidate_json TEXT,
                    executive_summary TEXT NOT NULL,
                    trade_off_analysis TEXT NOT NULL,
                    z3_verification_status TEXT NOT NULL,
                    optimization_scope TEXT DEFAULT 'BOUNDED_COMBINATION (k=3)',
                    objective_model_version TEXT DEFAULT '1.1',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_decisions_task_id ON decision_runs(task_id);

                CREATE TABLE IF NOT EXISTS candidate_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    evaluation_json TEXT NOT NULL,
                    is_feasible INTEGER NOT NULL,
                    pareto_status TEXT NOT NULL,
                    FOREIGN KEY(decision_id) REFERENCES decision_runs(decision_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_evals_decision_id ON candidate_evaluations(decision_id);

                CREATE TABLE IF NOT EXISTS candidate_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_id TEXT NOT NULL,
                    candidate_ids_json TEXT NOT NULL,
                    interaction_type TEXT NOT NULL,
                    conflicting_resource_id TEXT,
                    reason TEXT NOT NULL,
                    FOREIGN KEY(decision_id) REFERENCES decision_runs(decision_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_interactions_decision_id ON candidate_interactions(decision_id);

                CREATE TABLE IF NOT EXISTS decision_reports (
                    decision_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    assessment_id TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY(decision_id) REFERENCES decision_runs(decision_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_reports_decision_id ON decision_reports(decision_id);
                """
            )
            conn.commit()

            # Ensure Phase 3.1 columns exist for backward-compatible databases
            for col_sql in (
                "ALTER TABLE decision_runs ADD COLUMN optimization_scope TEXT DEFAULT 'BOUNDED_COMBINATION (k=3)'",
                "ALTER TABLE decision_runs ADD COLUMN objective_model_version TEXT DEFAULT '1.1'",
            ):
                try:
                    conn.execute(col_sql)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

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
            query += " ORDER BY created_at ASC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, tuple(params)).fetchall()
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

    def save_finding(self, finding: Finding) -> Finding:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO findings (
                    finding_id, task_id, agent_id, category, rule_id, severity,
                    title, description, source_file, source_location,
                    observed_value_json, expected_value_json, evidence_json,
                    recommendation, confidence, status, created_at, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(finding_id) DO UPDATE SET
                    status = excluded.status,
                    recommendation = excluded.recommendation
                """,
                (
                    finding.finding_id,
                    finding.task_id,
                    finding.agent_id,
                    finding.category.value,
                    finding.rule_id,
                    finding.severity.value,
                    finding.title,
                    finding.description,
                    finding.source_file,
                    finding.source_location,
                    json.dumps(finding.observed_value),
                    json.dumps(finding.expected_value),
                    json.dumps(finding.evidence),
                    finding.recommendation,
                    finding.confidence,
                    finding.status,
                    finding.created_at.isoformat(),
                    finding.schema_version,
                ),
            )
            conn.commit()
            return finding

    def get_findings_for_task(
        self,
        task_id: str,
        category: Optional[FindingCategory] = None,
    ) -> list[Finding]:
        with self._lock, self._get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM findings WHERE task_id = ? AND category = ? ORDER BY created_at ASC",
                    (task_id, category.value),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM findings WHERE task_id = ? ORDER BY created_at ASC",
                    (task_id,),
                ).fetchall()
            return [self._row_to_finding(row) for row in rows]

    def get_finding(self, finding_id: str) -> Finding | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM findings WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_finding(row)

    def save_inventory(self, inventory: InfrastructureInventory) -> InfrastructureInventory:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO inventories (
                    inventory_id, task_id, workspace_root, resources_json,
                    discovered_files_json, discovery_duration_ms, created_at, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(inventory_id) DO UPDATE SET
                    resources_json = excluded.resources_json,
                    discovery_duration_ms = excluded.discovery_duration_ms
                """,
                (
                    inventory.inventory_id,
                    inventory.task_id or "unassigned",
                    inventory.workspace_root,
                    json.dumps([r.model_dump(mode="json") for r in inventory.resources]),
                    json.dumps(inventory.discovered_files),
                    inventory.discovery_duration_ms,
                    inventory.created_at.isoformat(),
                    inventory.schema_version,
                ),
            )
            conn.commit()
            return inventory

    def get_inventory_for_task(self, task_id: str) -> InfrastructureInventory | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM inventories WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_inventory(row)

    def save_assessment(self, assessment: AssessmentSummary) -> AssessmentSummary:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO assessments (
                    assessment_id, task_id, workspace_root, total_resources,
                    total_findings, critical_findings_count, high_findings_count,
                    medium_findings_count, low_findings_count, estimated_monthly_cost,
                    currency, finops_summary, secops_summary, reliability_summary,
                    next_phase_recommendations_json, status, created_at, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    total_resources = excluded.total_resources,
                    total_findings = excluded.total_findings,
                    critical_findings_count = excluded.critical_findings_count,
                    high_findings_count = excluded.high_findings_count,
                    medium_findings_count = excluded.medium_findings_count,
                    low_findings_count = excluded.low_findings_count,
                    estimated_monthly_cost = excluded.estimated_monthly_cost,
                    finops_summary = excluded.finops_summary,
                    secops_summary = excluded.secops_summary,
                    reliability_summary = excluded.reliability_summary,
                    next_phase_recommendations_json = excluded.next_phase_recommendations_json,
                    status = excluded.status
                """,
                (
                    assessment.assessment_id,
                    assessment.task_id,
                    assessment.workspace_root,
                    assessment.total_resources,
                    assessment.total_findings,
                    assessment.critical_findings_count,
                    assessment.high_findings_count,
                    assessment.medium_findings_count,
                    assessment.low_findings_count,
                    assessment.estimated_monthly_cost,
                    assessment.currency,
                    assessment.finops_summary,
                    assessment.secops_summary,
                    assessment.reliability_summary,
                    json.dumps(assessment.next_phase_recommendations),
                    assessment.status,
                    assessment.created_at.isoformat(),
                    assessment.schema_version,
                ),
            )
            conn.commit()
            return assessment

    def get_assessment_for_task(self, task_id: str) -> AssessmentSummary | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM assessments WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_assessment(row)

    def save_decision_run(self, decision: DecisionRun) -> DecisionRun:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO decision_runs (
                    decision_id, task_id, assessment_id, workspace_root,
                    policy_config_json, preference_profile,
                    total_candidates_generated, feasible_candidates_count,
                    rejected_candidates_count, pareto_optimal_count,
                    recommended_candidate_id, recommended_candidate_json,
                    executive_summary, trade_off_analysis,
                    z3_verification_status, optimization_scope, objective_model_version,
                    status, created_at, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.decision_id,
                    decision.task_id,
                    decision.assessment_id,
                    decision.workspace_root,
                    decision.policy_config.model_dump_json(),
                    decision.preference_profile.value,
                    decision.total_candidates_generated,
                    decision.feasible_candidates_count,
                    decision.rejected_candidates_count,
                    decision.pareto_optimal_count,
                    decision.recommended_candidate_id,
                    decision.recommended_candidate.model_dump_json() if decision.recommended_candidate else None,
                    decision.executive_summary,
                    decision.trade_off_analysis,
                    decision.z3_verification_status,
                    getattr(decision, "optimization_scope", "BOUNDED_COMBINATION (k=3)"),
                    getattr(decision, "objective_model_version", "1.1"),
                    decision.status,
                    decision.created_at.isoformat(),
                    decision.schema_version,
                ),
            )
            conn.commit()
            return decision

    def get_decision_run(self, decision_id: str) -> DecisionRun | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM decision_runs WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_decision_run(row)

    def get_decision_run_for_task(self, task_id: str) -> DecisionRun | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM decision_runs WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_decision_run(row)

    def save_candidate_evaluations(
        self, decision_id: str, evaluations: list[CandidateEvaluation]
    ) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM candidate_evaluations WHERE decision_id = ?", (decision_id,))
            for ev in evaluations:
                cursor.execute(
                    """
                    INSERT INTO candidate_evaluations (
                        decision_id, candidate_id, evaluation_json, is_feasible, pareto_status
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        decision_id,
                        ev.candidate.candidate_id,
                        ev.model_dump_json(),
                        1 if ev.is_feasible else 0,
                        ev.pareto_status.value,
                    ),
                )
            conn.commit()

    def get_candidate_evaluations(
        self, decision_id: str
    ) -> list[CandidateEvaluation]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM candidate_evaluations WHERE decision_id = ?",
                (decision_id,),
            ).fetchall()
            return [self._row_to_candidate_evaluation(r) for r in rows]

    def save_interactions(
        self, decision_id: str, interactions: list[CandidateInteraction]
    ) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM candidate_interactions WHERE decision_id = ?", (decision_id,))
            for inter in interactions:
                cursor.execute(
                    """
                    INSERT INTO candidate_interactions (
                        decision_id, candidate_ids_json, interaction_type,
                        conflicting_resource_id, reason
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        decision_id,
                        json.dumps(inter.candidate_ids),
                        inter.interaction_type.value,
                        inter.conflicting_resource_id,
                        inter.reason,
                    ),
                )
            conn.commit()

    def get_interactions(
        self, decision_id: str
    ) -> list[CandidateInteraction]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM candidate_interactions WHERE decision_id = ?",
                (decision_id,),
            ).fetchall()
            return [self._row_to_candidate_interaction(r) for r in rows]

    def save_decision_report(self, report: DecisionReport) -> DecisionReport:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO decision_reports (
                    decision_id, task_id, assessment_id, report_json,
                    created_at, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.decision_id,
                    report.task_id,
                    report.assessment_id,
                    report.model_dump_json(),
                    report.created_at.isoformat(),
                    report.schema_version,
                ),
            )
            conn.commit()
            return report

    def get_decision_report(self, decision_id: str) -> DecisionReport | None:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM decision_reports WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_decision_report(row)

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

    def _row_to_finding(self, row: sqlite3.Row) -> Finding:
        return Finding(
            finding_id=row["finding_id"],
            task_id=row["task_id"],
            agent_id=row["agent_id"],
            category=FindingCategory(row["category"]),
            rule_id=row["rule_id"],
            severity=FindingSeverity(row["severity"]),
            title=row["title"],
            description=row["description"],
            source_file=row["source_file"],
            source_location=row["source_location"],
            observed_value=json.loads(row["observed_value_json"]),
            expected_value=json.loads(row["expected_value_json"]),
            evidence=json.loads(row["evidence_json"]),
            recommendation=row["recommendation"],
            confidence=row["confidence"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            schema_version=row["schema_version"],
        )

    def _row_to_inventory(self, row: sqlite3.Row) -> InfrastructureInventory:
        res_list = [DiscoveredResource.model_validate(r) for r in json.loads(row["resources_json"])]
        return InfrastructureInventory(
            inventory_id=row["inventory_id"],
            task_id=row["task_id"],
            workspace_root=row["workspace_root"],
            resources=res_list,
            discovered_files=json.loads(row["discovered_files_json"]),
            discovery_duration_ms=row["discovery_duration_ms"],
            created_at=datetime.fromisoformat(row["created_at"]),
            schema_version=row["schema_version"],
        )

    def _row_to_assessment(self, row: sqlite3.Row) -> AssessmentSummary:
        return AssessmentSummary(
            assessment_id=row["assessment_id"],
            task_id=row["task_id"],
            workspace_root=row["workspace_root"],
            total_resources=row["total_resources"],
            total_findings=row["total_findings"],
            critical_findings_count=row["critical_findings_count"],
            high_findings_count=row["high_findings_count"],
            medium_findings_count=row["medium_findings_count"],
            low_findings_count=row["low_findings_count"],
            estimated_monthly_cost=row["estimated_monthly_cost"],
            currency=row["currency"],
            finops_summary=row["finops_summary"] or "",
            secops_summary=row["secops_summary"] or "",
            reliability_summary=row["reliability_summary"] or "",
            next_phase_recommendations=json.loads(row["next_phase_recommendations_json"] or "[]"),
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            schema_version=row["schema_version"],
        )

    def _row_to_decision_run(self, row: sqlite3.Row) -> DecisionRun:
        rec_cand = None
        if row["recommended_candidate_json"]:
            rec_cand = Candidate.model_validate_json(row["recommended_candidate_json"])
        opt_scope = row["optimization_scope"] if "optimization_scope" in row.keys() else "BOUNDED_COMBINATION (k=3)"
        obj_version = row["objective_model_version"] if "objective_model_version" in row.keys() else "1.1"
        return DecisionRun(
            decision_id=row["decision_id"],
            task_id=row["task_id"],
            assessment_id=row["assessment_id"],
            workspace_root=row["workspace_root"],
            policy_config=PolicyConfiguration.model_validate_json(row["policy_config_json"]),
            preference_profile=PreferenceProfile(row["preference_profile"]),
            total_candidates_generated=row["total_candidates_generated"],
            feasible_candidates_count=row["feasible_candidates_count"],
            rejected_candidates_count=row["rejected_candidates_count"],
            pareto_optimal_count=row["pareto_optimal_count"],
            recommended_candidate_id=row["recommended_candidate_id"],
            recommended_candidate=rec_cand,
            executive_summary=row["executive_summary"],
            trade_off_analysis=row["trade_off_analysis"],
            z3_verification_status=row["z3_verification_status"],
            optimization_scope=opt_scope,
            objective_model_version=obj_version,
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            schema_version=row["schema_version"],
        )

    def _row_to_candidate_evaluation(self, row: sqlite3.Row) -> CandidateEvaluation:
        return CandidateEvaluation.model_validate_json(row["evaluation_json"])

    def _row_to_candidate_interaction(self, row: sqlite3.Row) -> CandidateInteraction:
        return CandidateInteraction(
            candidate_ids=json.loads(row["candidate_ids_json"]),
            interaction_type=InteractionType(row["interaction_type"]),
            conflicting_resource_id=row["conflicting_resource_id"],
            reason=row["reason"],
        )

    def _row_to_decision_report(self, row: sqlite3.Row) -> DecisionReport:
        return DecisionReport.model_validate_json(row["report_json"])

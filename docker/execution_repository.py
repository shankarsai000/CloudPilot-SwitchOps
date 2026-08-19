"""
Execution Repository — PostgreSQL persistence for M10 entities.

Stores execution records, rollback records, and logs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from models_execution import ExecutionRecord, RollbackRecord

logger = logging.getLogger(__name__)


class ExecutionRepositoryError(Exception):
    """Raised when execution repository operations fail."""

    pass


class ExecutionRepository:
    """PostgreSQL repository for execution records and audits."""

    def __init__(self, connection_string: str) -> None:
        """Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            ExecutionRepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise ExecutionRepositoryError(
                "psycopg2 required for PostgreSQL support"
            ) from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("ExecutionRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_records (
                    execution_id VARCHAR(255) PRIMARY KEY,
                    decision_id VARCHAR(255) NOT NULL,
                    target_id VARCHAR(255) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    state VARCHAR(100) NOT NULL,
                    rollout JSONB,
                    lock_acquired BOOLEAN DEFAULT FALSE,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT,
                    metrics_summary JSONB,
                    audit_trail JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS execution_rollback_records (
                    rollback_id VARCHAR(255) PRIMARY KEY,
                    execution_id VARCHAR(255) NOT NULL,
                    trigger_reason TEXT NOT NULL,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    status VARCHAR(100) NOT NULL,
                    details JSONB
                );

                CREATE TABLE IF NOT EXISTS execution_events (
                    event_id VARCHAR(255) PRIMARY KEY,
                    execution_id VARCHAR(255) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    level VARCHAR(50) NOT NULL,
                    message TEXT NOT NULL,
                    details JSONB
                );

                CREATE INDEX IF NOT EXISTS idx_exec_target ON execution_records(target_id);
                CREATE INDEX IF NOT EXISTS idx_exec_state ON execution_records(state);
                CREATE INDEX IF NOT EXISTS idx_rollback_exec ON execution_rollback_records(execution_id);
                CREATE INDEX IF NOT EXISTS idx_event_exec ON execution_events(execution_id);
            """)

            self.connection.commit()
            logger.info("Execution database schema initialized")
        except Exception as e:
            raise ExecutionRepositoryError(
                f"Database initialization failed: {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def save_execution(self, record: ExecutionRecord) -> None:
        """Save or update an execution record.

        Args:
            record: ExecutionRecord to save

        Raises:
            ExecutionRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO execution_records (
                    execution_id, decision_id, target_id, action, state, rollout,
                    lock_acquired, started_at, completed_at, error_message,
                    metrics_summary, audit_trail, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (execution_id) DO UPDATE SET
                    state = EXCLUDED.state,
                    rollout = EXCLUDED.rollout,
                    lock_acquired = EXCLUDED.lock_acquired,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at,
                    error_message = EXCLUDED.error_message,
                    metrics_summary = EXCLUDED.metrics_summary,
                    audit_trail = EXCLUDED.audit_trail
            """, (
                record.execution_id,
                record.decision_id,
                record.target_id,
                record.action,
                record.state.value,
                json.dumps(record.rollout.dict()) if record.rollout else None,
                record.lock_acquired,
                record.started_at,
                record.completed_at,
                record.error_message,
                json.dumps(record.metrics_summary),
                json.dumps(record.audit_trail),
                record.created_at,
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise ExecutionRepositoryError(f"Failed to save execution: {e}") from e
        finally:
            cursor.close()

    def save_rollback(self, record: RollbackRecord) -> None:
        """Save a rollback record.

        Args:
            record: RollbackRecord to save

        Raises:
            ExecutionRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO execution_rollback_records (
                    rollback_id, execution_id, trigger_reason, started_at,
                    completed_at, status, details
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (rollback_id) DO NOTHING
            """, (
                record.rollback_id,
                record.execution_id,
                record.trigger_reason,
                record.started_at,
                record.completed_at,
                record.status,
                json.dumps(record.details),
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise ExecutionRepositoryError(f"Failed to save rollback record: {e}") from e
        finally:
            cursor.close()

    def get_executions(self, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve recent executions.

        Args:
            limit: Maximum records to return

        Returns:
            List of execution dicts
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM execution_records ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            raise ExecutionRepositoryError(f"Failed to get executions: {e}") from e
        finally:
            cursor.close()

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Execution database connection closed")

    def __enter__(self) -> "ExecutionRepository":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type, exc_val: Exception, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

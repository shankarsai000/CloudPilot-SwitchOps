"""
Decision Repository — PostgreSQL persistence for M9 entities.

Stores decision records, override records, and audit logs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from models_decision import DecisionRecord, OverrideRecord

logger = logging.getLogger(__name__)


class DecisionRepositoryError(Exception):
    """Raised when decision repository operations fail."""

    pass


class DecisionRepository:
    """PostgreSQL repository for decision records and audits."""

    def __init__(self, connection_string: str) -> None:
        """Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            DecisionRepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise DecisionRepositoryError(
                "psycopg2 required for PostgreSQL support"
            ) from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("DecisionRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decision_records (
                    decision_id VARCHAR(255) PRIMARY KEY,
                    target_id VARCHAR(255) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    state VARCHAR(100) NOT NULL,
                    consensus JSONB,
                    score JSONB,
                    approval_route JSONB,
                    policy_report JSONB,
                    execution_package JSONB,
                    decision_confidence NUMERIC(6, 2),
                    explanation TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    decided_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS override_records (
                    override_id VARCHAR(255) PRIMARY KEY,
                    decision_id VARCHAR(255) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    actor VARCHAR(255) NOT NULL,
                    reason TEXT,
                    original_state VARCHAR(100) NOT NULL,
                    new_state VARCHAR(100) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS decision_audit_logs (
                    id SERIAL PRIMARY KEY,
                    decision_id VARCHAR(255) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    state VARCHAR(100) NOT NULL,
                    status VARCHAR(100) NOT NULL,
                    log_data JSONB
                );

                CREATE INDEX IF NOT EXISTS idx_decision_target ON decision_records(target_id);
                CREATE INDEX IF NOT EXISTS idx_decision_state ON decision_records(state);
                CREATE INDEX IF NOT EXISTS idx_override_decision ON override_records(decision_id);
                CREATE INDEX IF NOT EXISTS idx_audit_decision ON decision_audit_logs(decision_id);
            """)

            self.connection.commit()
            logger.info("Decision database schema initialized")
        except Exception as e:
            raise DecisionRepositoryError(
                f"Database initialization failed: {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def save_decision(self, record: DecisionRecord) -> None:
        """Save or update a decision record.

        Args:
            record: DecisionRecord to save

        Raises:
            DecisionRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO decision_records (
                    decision_id, target_id, action, state, consensus,
                    score, approval_route, policy_report, execution_package,
                    decision_confidence, explanation, created_at, decided_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_id) DO UPDATE SET
                    state = EXCLUDED.state,
                    consensus = EXCLUDED.consensus,
                    score = EXCLUDED.score,
                    approval_route = EXCLUDED.approval_route,
                    policy_report = EXCLUDED.policy_report,
                    execution_package = EXCLUDED.execution_package,
                    decision_confidence = EXCLUDED.decision_confidence,
                    explanation = EXCLUDED.explanation,
                    decided_at = EXCLUDED.decided_at
            """, (
                record.decision_id,
                record.target_id,
                record.action,
                record.state.value,
                json.dumps(record.consensus.dict()) if record.consensus else None,
                json.dumps(record.score.dict()) if record.score else None,
                json.dumps(record.approval_route.dict()) if record.approval_route else None,
                json.dumps(record.policy_report.dict()) if record.policy_report else None,
                json.dumps(record.execution_package.dict()) if record.execution_package else None,
                record.decision_confidence,
                record.explanation,
                record.created_at,
                record.decided_at,
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise DecisionRepositoryError(f"Failed to save decision: {e}") from e
        finally:
            cursor.close()

    def save_override(self, record: OverrideRecord) -> None:
        """Save a human override record.

        Args:
            record: OverrideRecord to save

        Raises:
            DecisionRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO override_records (
                    override_id, decision_id, action, actor,
                    reason, original_state, new_state, timestamp
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (override_id) DO NOTHING
            """, (
                record.override_id,
                record.decision_id,
                record.action.value,
                record.actor,
                record.reason,
                record.original_state.value,
                record.new_state.value,
                record.timestamp,
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise DecisionRepositoryError(f"Failed to save override: {e}") from e
        finally:
            cursor.close()

    def save_audit_log(self, decision_id: str, state: str, status: str, log_data: dict[str, Any]) -> None:
        """Save an audit log entry.

        Args:
            decision_id: Decision identifier
            state: Decision state
            status: Evaluation status
            log_data: Additional audit metadata

        Raises:
            DecisionRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO decision_audit_logs (decision_id, state, status, log_data)
                VALUES (%s, %s, %s, %s)
            """, (
                decision_id,
                state,
                status,
                json.dumps(log_data),
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise DecisionRepositoryError(f"Failed to save audit log: {e}") from e
        finally:
            cursor.close()

    def get_decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve recent decision records.

        Args:
            limit: Maximum records to return

        Returns:
            List of decision dicts
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM decision_records ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            raise DecisionRepositoryError(f"Failed to get decisions: {e}") from e
        finally:
            cursor.close()

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Decision database connection closed")

    def __enter__(self) -> "DecisionRepository":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type, exc_val: Exception, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

"""
Explanation Repository — PostgreSQL persistence for M7 entities.

Stores decision explanations, confidence breakdowns, and audit trails.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from models_explanation import ExplanationReport, AuditTrail

logger = logging.getLogger(__name__)


class ExplanationRepositoryError(Exception):
    """Raised when explanation repository operations fail."""

    pass


class ExplanationRepository:
    """PostgreSQL repository for Trust & Explainable AI data."""

    def __init__(self, connection_string: str) -> None:
        """Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            ExplanationRepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise ExplanationRepositoryError(
                "psycopg2 required for PostgreSQL support"
            ) from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("ExplanationRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS explanation_reports (
                    decision_id VARCHAR(255) PRIMARY KEY,
                    why_explanation TEXT NOT NULL,
                    why_now_explanation TEXT NOT NULL,
                    why_strategy_explanation TEXT NOT NULL,
                    why_not_alternatives TEXT,
                    evidence_summary JSONB,
                    supporting_metrics JSONB,
                    confidence JSONB,
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS audit_trails (
                    audit_id VARCHAR(255) PRIMARY KEY,
                    decision_id VARCHAR(255) NOT NULL,
                    requested_by VARCHAR(255) NOT NULL,
                    approved_by VARCHAR(255),
                    executed_by VARCHAR(255),
                    action VARCHAR(255) NOT NULL,
                    timestamp TIMESTAMP,
                    outcome VARCHAR(50) NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_audit_decision ON audit_trails(decision_id);
            """)

            self.connection.commit()
            logger.info("Explanation database schema initialized")
        except Exception as e:
            raise ExplanationRepositoryError(
                f"Database initialization failed: {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def save_explanation(self, report: ExplanationReport) -> None:
        """Save an explanation report.

        Args:
            report: ExplanationReport instance to save

        Raises:
            ExplanationRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO explanation_reports (
                    decision_id, why_explanation, why_now_explanation,
                    why_strategy_explanation, why_not_alternatives,
                    evidence_summary, supporting_metrics, confidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_id) DO UPDATE SET
                    why_explanation = EXCLUDED.why_explanation,
                    why_now_explanation = EXCLUDED.why_now_explanation,
                    why_strategy_explanation = EXCLUDED.why_strategy_explanation,
                    why_not_alternatives = EXCLUDED.why_not_alternatives,
                    evidence_summary = EXCLUDED.evidence_summary,
                    supporting_metrics = EXCLUDED.supporting_metrics,
                    confidence = EXCLUDED.confidence
            """, (
                report.decision_id,
                report.why_explanation,
                report.why_now_explanation,
                report.why_strategy_explanation,
                report.why_not_alternatives,
                json.dumps(report.evidence_summary),
                json.dumps(report.supporting_metrics),
                json.dumps(report.confidence.dict())
            ))

            self.connection.commit()
            logger.debug("Saved explanation report %s", report.decision_id)
        except Exception as e:
            self.connection.rollback()
            raise ExplanationRepositoryError(
                f"Failed to save explanation report {report.decision_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def save_audit(self, audit: AuditTrail) -> None:
        """Save an audit log entry.

        Args:
            audit: AuditTrail to save

        Raises:
            ExplanationRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO audit_trails (
                    audit_id, decision_id, requested_by, approved_by,
                    executed_by, action, timestamp, outcome
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (audit_id) DO UPDATE SET
                    approved_by = EXCLUDED.approved_by,
                    executed_by = EXCLUDED.executed_by,
                    outcome = EXCLUDED.outcome
            """, (
                audit.audit_id,
                audit.decision_id,
                audit.requested_by,
                audit.approved_by,
                audit.executed_by,
                audit.action,
                audit.timestamp,
                audit.outcome
            ))

            self.connection.commit()
            logger.debug("Saved audit log %s", audit.audit_id)
        except Exception as e:
            self.connection.rollback()
            raise ExplanationRepositoryError(
                f"Failed to save audit log {audit.audit_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def get_explanation(self, decision_id: str) -> Optional[ExplanationReport]:
        """Retrieve explanation report by decision ID.

        Args:
            decision_id: Decision identifier

        Returns:
            ExplanationReport or None if not found
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM explanation_reports WHERE decision_id = %s",
                (decision_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_explanation(row)
        except Exception as e:
            raise ExplanationRepositoryError(
                f"Failed to get explanation report {decision_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def get_audit_trail(self, limit: int = 50) -> list[AuditTrail]:
        """Get history of audit logs.

        Args:
            limit: Maximum records to return

        Returns:
            List of AuditTrail objects
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM audit_trails ORDER BY timestamp DESC LIMIT %s",
                (limit,)
            )
            rows = cursor.fetchall()
            return [
                AuditTrail(
                    audit_id=row["audit_id"],
                    decision_id=row["decision_id"],
                    requested_by=row["requested_by"],
                    approved_by=row["approved_by"],
                    executed_by=row["executed_by"],
                    action=row["action"],
                    timestamp=row["timestamp"],
                    outcome=row["outcome"]
                )
                for row in rows
            ]
        except Exception as e:
            raise ExplanationRepositoryError(f"Failed to fetch audit trail: {e}") from e
        finally:
            cursor.close()

    def _row_to_explanation(self, row: dict[str, Any]) -> ExplanationReport:
        """Convert database row to ExplanationReport model."""
        from models_explanation import ConfidenceBreakdown

        conf_raw = row["confidence"]
        conf = ConfidenceBreakdown(
            infrastructure=float(conf_raw["infrastructure"]),
            application=float(conf_raw["application"]),
            simulation=float(conf_raw["simulation"]),
            history=float(conf_raw["history"]),
            policies=float(conf_raw["policies"]),
            final_score=float(conf_raw["final_score"])
        )

        return ExplanationReport(
            decision_id=row["decision_id"],
            why_explanation=row["why_explanation"],
            why_now_explanation=row["why_now_explanation"],
            why_strategy_explanation=row["why_strategy_explanation"],
            why_not_alternatives=row["why_not_alternatives"] or "",
            evidence_summary=row["evidence_summary"] or [],
            supporting_metrics=row["supporting_metrics"] or {},
            confidence=conf
        )

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Explanation database connection closed")

    def __enter__(self) -> "ExplanationRepository":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type, exc_val: Exception, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

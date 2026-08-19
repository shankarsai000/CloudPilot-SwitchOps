"""
Risk Repository - PostgreSQL data layer

Stores risk assessments, policy violations, simulations, and history records.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from models_risk import RiskAssessment, RiskHistoryRecord, RiskCategory

logger = logging.getLogger(__name__)


class RiskRepositoryError(Exception):
    """Raised when repository operations fail."""

    pass


class RiskRepository:
    """PostgreSQL repository for operational risk intelligence data."""

    def __init__(self, connection_string: str) -> None:
        """Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            RiskRepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise RiskRepositoryError(
                "psycopg2 required for PostgreSQL support"
            ) from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("RiskRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS risk_assessments (
                    assessment_id VARCHAR(255) PRIMARY KEY,
                    target_id VARCHAR(255) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    risk_score NUMERIC(5, 2) NOT NULL,
                    risk_category VARCHAR(50) NOT NULL,
                    confidence_score NUMERIC(5, 2) NOT NULL,
                    explanation JSONB,
                    policy_violations JSONB,
                    mitigations JSONB,
                    metadata JSONB,
                    assessed_at TIMESTAMP,
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS policy_violations_log (
                    violation_id SERIAL PRIMARY KEY,
                    assessment_id VARCHAR(255),
                    policy_id VARCHAR(100),
                    target_id VARCHAR(255),
                    violation_detail TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (assessment_id)
                        REFERENCES risk_assessments(assessment_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_risk_target ON risk_assessments(target_id);
                CREATE INDEX IF NOT EXISTS idx_risk_category ON risk_assessments(risk_category);
                CREATE INDEX IF NOT EXISTS idx_risk_assessed ON risk_assessments(assessed_at);
            """)

            self.connection.commit()
            logger.info("Risk database schema initialized")
        except Exception as e:
            raise RiskRepositoryError(
                f"Database initialization failed: {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def save_assessment(self, assessment: RiskAssessment) -> None:
        """Save a risk assessment report.

        Args:
            assessment: RiskAssessment instance to save

        Raises:
            RiskRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO risk_assessments (
                    assessment_id, target_id, action, risk_score,
                    risk_category, confidence_score, explanation,
                    policy_violations, mitigations, metadata, assessed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (assessment_id) DO UPDATE SET
                    risk_score = EXCLUDED.risk_score,
                    risk_category = EXCLUDED.risk_category,
                    confidence_score = EXCLUDED.confidence_score,
                    explanation = EXCLUDED.explanation,
                    policy_violations = EXCLUDED.policy_violations,
                    mitigations = EXCLUDED.mitigations,
                    metadata = EXCLUDED.metadata,
                    assessed_at = EXCLUDED.assessed_at
            """, (
                assessment.assessment_id,
                assessment.target_id,
                assessment.action.value if hasattr(assessment.action, "value") else str(assessment.action),
                assessment.risk_score,
                assessment.risk_category.value if hasattr(assessment.risk_category, "value") else str(assessment.risk_category),
                assessment.confidence_score,
                json.dumps(assessment.explanation),
                json.dumps(assessment.policy_violations),
                json.dumps(assessment.mitigations),
                json.dumps(assessment.metadata),
                assessment.assessed_at
            ))

            # Log policy violations separately for auditing
            for violation in assessment.policy_violations:
                policy_id = "UNKNOWN"
                if "POL-" in violation:
                    policy_id = violation.split("[")[0].strip()
                
                cursor.execute("""
                    INSERT INTO policy_violations_log (
                        assessment_id, policy_id, target_id, violation_detail
                    ) VALUES (%s, %s, %s, %s)
                """, (
                    assessment.assessment_id,
                    policy_id,
                    assessment.target_id,
                    violation
                ))

            self.connection.commit()
            logger.debug("Saved risk assessment %s", assessment.assessment_id)
        except Exception as e:
            self.connection.rollback()
            raise RiskRepositoryError(
                f"Failed to save risk assessment {assessment.assessment_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def get_assessment(self, assessment_id: str) -> Optional[RiskAssessment]:
        """Retrieve risk assessment by ID.

        Args:
            assessment_id: Assessment identifier

        Returns:
            RiskAssessment or None if not found
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM risk_assessments WHERE assessment_id = %s",
                (assessment_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_assessment(row)
        except Exception as e:
            raise RiskRepositoryError(
                f"Failed to get risk assessment {assessment_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def get_history(self, limit: int = 50) -> list[RiskHistoryRecord]:
        """Get history of assessments.

        Args:
            limit: Maximum records to return

        Returns:
            List of RiskHistoryRecord objects
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT assessment_id, target_id, action, risk_score, "
                "risk_category, confidence_score, policy_violations, assessed_at "
                "FROM risk_assessments ORDER BY assessed_at DESC LIMIT %s",
                (limit,)
            )
            rows = cursor.fetchall()
            return [
                RiskHistoryRecord(
                    assessment_id=row["assessment_id"],
                    target_id=row["target_id"],
                    action=row["action"],
                    risk_score=float(row["risk_score"]),
                    risk_category=row["risk_category"],
                    confidence_score=float(row["confidence_score"]),
                    policy_violations=row["policy_violations"] or [],
                    created_at=row["assessed_at"]
                )
                for row in rows
            ]
        except Exception as e:
            raise RiskRepositoryError(f"Failed to fetch history: {e}") from e
        finally:
            cursor.close()

    def _row_to_assessment(self, row: dict[str, Any]) -> RiskAssessment:
        """Convert database row to RiskAssessment model."""
        return RiskAssessment(
            assessment_id=row["assessment_id"],
            target_id=row["target_id"],
            action=ActionType(row["action"]),
            risk_score=float(row["risk_score"]),
            risk_category=RiskCategory(row["risk_category"]),
            confidence_score=float(row["confidence_score"]),
            explanation=row["explanation"] or [],
            policy_violations=row["policy_violations"] or [],
            mitigations=row["mitigations"] or [],
            metadata=row["metadata"] or {},
            assessed_at=row["assessed_at"]
        )

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Risk database connection closed")

    def __enter__(self) -> "RiskRepository":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type, exc_val: Exception, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

"""
Learning Repository — PostgreSQL persistence for M8 entities.

Stores learning events, Cloud DNA profiles, feedback records, and experience records.
Event sourcing: append-only inserts with timestamp ordering.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from models_learning import (
    CloudDNAProfile,
    ExperienceRecord,
    FeedbackRecord,
    LearningEvent,
)

logger = logging.getLogger(__name__)


class LearningRepositoryError(Exception):
    """Raised when learning repository operations fail."""

    pass


class LearningRepository:
    """PostgreSQL repository for organizational intelligence data."""

    def __init__(self, connection_string: str) -> None:
        """Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            LearningRepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise LearningRepositoryError(
                "psycopg2 required for PostgreSQL support"
            ) from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("LearningRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_events (
                    event_id VARCHAR(255) PRIMARY KEY,
                    event_type VARCHAR(100) NOT NULL,
                    target_id VARCHAR(255) NOT NULL,
                    action VARCHAR(255) NOT NULL,
                    outcome VARCHAR(50) NOT NULL,
                    actor VARCHAR(255),
                    metadata JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS cloud_dna_profiles (
                    organization_id VARCHAR(255) PRIMARY KEY,
                    deployment_style VARCHAR(50),
                    risk_tolerance VARCHAR(50),
                    scaling_pattern VARCHAR(50),
                    peak_hours VARCHAR(50),
                    preferred_regions JSONB,
                    average_approval_time_hours NUMERIC(8, 2),
                    rollback_frequency_percentage NUMERIC(8, 2),
                    automation_level_percentage NUMERIC(8, 2),
                    deployment_frequency_per_week NUMERIC(8, 2),
                    total_events_analyzed INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS feedback_records (
                    feedback_id VARCHAR(255) PRIMARY KEY,
                    decision_id VARCHAR(255) NOT NULL,
                    source VARCHAR(255) NOT NULL,
                    verdict VARCHAR(50) NOT NULL,
                    reason TEXT,
                    tags JSONB,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS experience_records (
                    experience_id VARCHAR(255) PRIMARY KEY,
                    context JSONB,
                    decision VARCHAR(255),
                    action VARCHAR(255),
                    outcome VARCHAR(50),
                    confidence_at_decision NUMERIC(8, 2),
                    actual_savings_usd NUMERIC(12, 2),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_event_type ON learning_events(event_type);
                CREATE INDEX IF NOT EXISTS idx_event_target ON learning_events(target_id);
                CREATE INDEX IF NOT EXISTS idx_event_timestamp ON learning_events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_feedback_decision ON feedback_records(decision_id);
            """)

            self.connection.commit()
            logger.info("Learning database schema initialized")
        except Exception as e:
            raise LearningRepositoryError(
                f"Database initialization failed: {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def save_event(self, event: LearningEvent) -> None:
        """Save a learning event (append-only).

        Args:
            event: LearningEvent to save

        Raises:
            LearningRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO learning_events (
                    event_id, event_type, target_id, action,
                    outcome, actor, metadata, timestamp
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
            """, (
                event.event_id,
                event.event_type.value,
                event.target_id,
                event.action,
                event.outcome.value,
                event.actor,
                json.dumps(event.metadata),
                event.timestamp,
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise LearningRepositoryError(f"Failed to save event: {e}") from e
        finally:
            cursor.close()

    def save_dna_profile(self, profile: CloudDNAProfile) -> None:
        """Save or update Cloud DNA profile.

        Args:
            profile: CloudDNAProfile to save

        Raises:
            LearningRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO cloud_dna_profiles (
                    organization_id, deployment_style, risk_tolerance,
                    scaling_pattern, peak_hours, preferred_regions,
                    average_approval_time_hours, rollback_frequency_percentage,
                    automation_level_percentage, deployment_frequency_per_week,
                    total_events_analyzed, last_updated
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (organization_id) DO UPDATE SET
                    deployment_style = EXCLUDED.deployment_style,
                    risk_tolerance = EXCLUDED.risk_tolerance,
                    scaling_pattern = EXCLUDED.scaling_pattern,
                    peak_hours = EXCLUDED.peak_hours,
                    preferred_regions = EXCLUDED.preferred_regions,
                    average_approval_time_hours = EXCLUDED.average_approval_time_hours,
                    rollback_frequency_percentage = EXCLUDED.rollback_frequency_percentage,
                    automation_level_percentage = EXCLUDED.automation_level_percentage,
                    deployment_frequency_per_week = EXCLUDED.deployment_frequency_per_week,
                    total_events_analyzed = EXCLUDED.total_events_analyzed,
                    last_updated = EXCLUDED.last_updated
            """, (
                profile.organization_id,
                profile.deployment_style.value,
                profile.risk_tolerance.value,
                profile.scaling_pattern.value,
                profile.peak_hours,
                json.dumps(profile.preferred_regions),
                profile.average_approval_time_hours,
                profile.rollback_frequency_percentage,
                profile.automation_level_percentage,
                profile.deployment_frequency_per_week,
                profile.total_events_analyzed,
                profile.last_updated,
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise LearningRepositoryError(f"Failed to save DNA profile: {e}") from e
        finally:
            cursor.close()

    def save_feedback(self, feedback: FeedbackRecord) -> None:
        """Save a feedback record.

        Args:
            feedback: FeedbackRecord to save

        Raises:
            LearningRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO feedback_records (
                    feedback_id, decision_id, source, verdict,
                    reason, tags, timestamp
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (feedback_id) DO NOTHING
            """, (
                feedback.feedback_id,
                feedback.decision_id,
                feedback.source,
                feedback.verdict.value,
                feedback.reason,
                json.dumps(feedback.tags),
                feedback.timestamp,
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise LearningRepositoryError(f"Failed to save feedback: {e}") from e
        finally:
            cursor.close()

    def get_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """Retrieve recent events.

        Args:
            limit: Maximum events to return

        Returns:
            List of event dicts
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM learning_events ORDER BY timestamp DESC LIMIT %s",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            raise LearningRepositoryError(f"Failed to get events: {e}") from e
        finally:
            cursor.close()

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Learning database connection closed")

    def __enter__(self) -> "LearningRepository":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type, exc_val: Exception, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

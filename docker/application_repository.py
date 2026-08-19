"""
Application Repository — PostgreSQL persistence for M3 entities.

Implements the Repository pattern for persistent storage of
applications, services, dependencies, ownership, deployments,
and topology data. Mirrors the design of resource_repository.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from models_application import (
    Application,
    ApplicationGraph,
    ApplicationType,
    BusinessCriticality,
    CriticalityLevel,
    DeploymentRecord,
    DeploymentStatus,
    DeploymentStrategy,
    EnvironmentType,
    OwnershipInfo,
    ServiceTier,
)

logger = logging.getLogger(__name__)


class ApplicationRepositoryError(Exception):
    """Raised when application repository operations fail."""

    pass


class ApplicationRepository:
    """PostgreSQL repository for M3 application entities.

    Manages persistent storage and querying of discovered applications,
    services, dependencies, ownership, deployments, and criticality data.
    """

    def __init__(self, connection_string: str) -> None:
        """Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            ApplicationRepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise ApplicationRepositoryError(
                "psycopg2 required for PostgreSQL support"
            ) from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("ApplicationRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    application_id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(500),
                    description TEXT,
                    application_type VARCHAR(50),
                    environment VARCHAR(50),
                    tier VARCHAR(50),
                    resource_ids JSONB,
                    tags JSONB,
                    metadata JSONB,
                    total_monthly_cost NUMERIC(12, 2),
                    discovery_source VARCHAR(100),
                    discovered_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS application_ownership (
                    application_id VARCHAR(255) PRIMARY KEY,
                    owner VARCHAR(255),
                    team VARCHAR(255),
                    team_id VARCHAR(255),
                    slack_channel VARCHAR(255),
                    email VARCHAR(255),
                    repository TEXT,
                    business_unit VARCHAR(255),
                    cost_center VARCHAR(100),
                    pagerduty_service VARCHAR(255),
                    documentation_url TEXT,
                    runbook_url TEXT,
                    confidence NUMERIC(5, 4),
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (application_id)
                        REFERENCES applications(application_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS application_criticality (
                    application_id VARCHAR(255) PRIMARY KEY,
                    revenue_impact NUMERIC(4, 1),
                    compliance_impact NUMERIC(4, 1),
                    availability_target NUMERIC(6, 3),
                    rto_minutes INTEGER,
                    rpo_minutes INTEGER,
                    risk_level VARCHAR(50),
                    criticality_score NUMERIC(5, 1),
                    compliance_frameworks JSONB,
                    customer_facing BOOLEAN,
                    data_classification VARCHAR(50),
                    calculated_at TIMESTAMP,
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (application_id)
                        REFERENCES applications(application_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS application_deployments (
                    deployment_id VARCHAR(255) PRIMARY KEY,
                    application_id VARCHAR(255),
                    version VARCHAR(255),
                    previous_version VARCHAR(255),
                    strategy VARCHAR(50),
                    status VARCHAR(50),
                    deployed_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    duration_seconds INTEGER,
                    deployed_by VARCHAR(255),
                    commit_sha VARCHAR(255),
                    is_rollback BOOLEAN DEFAULT FALSE,
                    change_summary TEXT,
                    metadata JSONB,
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (application_id)
                        REFERENCES applications(application_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_app_type
                    ON applications(application_type);
                CREATE INDEX IF NOT EXISTS idx_app_env
                    ON applications(environment);
                CREATE INDEX IF NOT EXISTS idx_app_tier
                    ON applications(tier);
                CREATE INDEX IF NOT EXISTS idx_deploy_app
                    ON application_deployments(application_id);
                CREATE INDEX IF NOT EXISTS idx_deploy_time
                    ON application_deployments(deployed_at);
            """)

            self.connection.commit()
            logger.info("Application database schema initialized")
        except Exception as e:
            raise ApplicationRepositoryError(
                f"Database initialization failed: {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def save_application(self, application: Application) -> None:
        """Save or update an application.

        Args:
            application: Application to save

        Raises:
            ApplicationRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO applications (
                    application_id, name, description, application_type,
                    environment, tier, resource_ids, tags, metadata,
                    total_monthly_cost, discovery_source, discovered_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (application_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    application_type = EXCLUDED.application_type,
                    environment = EXCLUDED.environment,
                    tier = EXCLUDED.tier,
                    resource_ids = EXCLUDED.resource_ids,
                    tags = EXCLUDED.tags,
                    metadata = EXCLUDED.metadata,
                    total_monthly_cost = EXCLUDED.total_monthly_cost,
                    updated_at = EXCLUDED.updated_at
            """, (
                application.application_id,
                application.name,
                application.description,
                application.application_type.value,
                application.environment.value,
                application.tier.value,
                json.dumps(application.resource_ids),
                json.dumps(application.tags),
                json.dumps(application.metadata),
                application.total_monthly_cost,
                application.discovery_source,
                application.discovered_at,
                application.updated_at,
            ))

            # Save ownership
            if application.ownership:
                self._save_ownership(cursor, application)

            # Save criticality
            if application.criticality:
                self._save_criticality(cursor, application)

            # Save deployments
            for deployment in application.deployments:
                self._save_deployment(cursor, deployment)

            self.connection.commit()
            logger.debug("Saved application %s", application.application_id)
        except Exception as e:
            self.connection.rollback()
            raise ApplicationRepositoryError(
                f"Failed to save application {application.application_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def save_applications(self, applications: list[Application]) -> None:
        """Save multiple applications in batch.

        Args:
            applications: List of applications to save
        """
        for application in applications:
            self.save_application(application)
        logger.info("Saved %d applications", len(applications))

    def get_application(self, application_id: str) -> Optional[Application]:
        """Retrieve application by ID.

        Args:
            application_id: Application identifier

        Returns:
            Application or None if not found
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM applications WHERE application_id = %s",
                (application_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_application(row)
        except Exception as e:
            raise ApplicationRepositoryError(
                f"Failed to get application {application_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def get_all_applications(self) -> list[Application]:
        """Get all applications.

        Returns:
            List of all Application objects
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM applications ORDER BY discovered_at DESC"
            )
            rows = cursor.fetchall()
            return [self._row_to_application(row) for row in rows]
        except Exception as e:
            raise ApplicationRepositoryError(
                f"Failed to get all applications: {e}"
            ) from e
        finally:
            cursor.close()

    def get_applications_by_type(
        self, app_type: ApplicationType
    ) -> list[Application]:
        """Get applications by type.

        Args:
            app_type: ApplicationType filter

        Returns:
            Filtered applications
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM applications WHERE application_type = %s ORDER BY discovered_at DESC",
                (app_type.value,),
            )
            rows = cursor.fetchall()
            return [self._row_to_application(row) for row in rows]
        except Exception as e:
            raise ApplicationRepositoryError(
                f"Failed to get applications by type: {e}"
            ) from e
        finally:
            cursor.close()

    def get_applications_by_environment(
        self, environment: EnvironmentType
    ) -> list[Application]:
        """Get applications by environment.

        Args:
            environment: EnvironmentType filter

        Returns:
            Filtered applications
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM applications WHERE environment = %s ORDER BY discovered_at DESC",
                (environment.value,),
            )
            rows = cursor.fetchall()
            return [self._row_to_application(row) for row in rows]
        except Exception as e:
            raise ApplicationRepositoryError(
                f"Failed to get applications by environment: {e}"
            ) from e
        finally:
            cursor.close()

    def get_statistics(self) -> dict[str, Any]:
        """Get application repository statistics.

        Returns:
            Statistics dictionary
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)

            cursor.execute("SELECT COUNT(*) as total FROM applications")
            total = cursor.fetchone()["total"]

            cursor.execute(
                "SELECT application_type, COUNT(*) as count "
                "FROM applications GROUP BY application_type"
            )
            by_type = {row["application_type"]: row["count"] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT environment, COUNT(*) as count "
                "FROM applications GROUP BY environment"
            )
            by_env = {row["environment"]: row["count"] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT tier, COUNT(*) as count "
                "FROM applications GROUP BY tier"
            )
            by_tier = {row["tier"]: row["count"] for row in cursor.fetchall()}

            return {
                "total_applications": total,
                "by_type": by_type,
                "by_environment": by_env,
                "by_tier": by_tier,
            }
        except Exception as e:
            raise ApplicationRepositoryError(
                f"Failed to get statistics: {e}"
            ) from e
        finally:
            cursor.close()

    def _save_ownership(self, cursor: Any, app: Application) -> None:
        """Save ownership data for an application."""
        ownership = app.ownership
        cursor.execute("""
            INSERT INTO application_ownership (
                application_id, owner, team, team_id, slack_channel,
                email, repository, business_unit, cost_center,
                pagerduty_service, documentation_url, runbook_url, confidence
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (application_id) DO UPDATE SET
                owner = EXCLUDED.owner,
                team = EXCLUDED.team,
                team_id = EXCLUDED.team_id,
                slack_channel = EXCLUDED.slack_channel,
                email = EXCLUDED.email,
                repository = EXCLUDED.repository,
                business_unit = EXCLUDED.business_unit,
                confidence = EXCLUDED.confidence
        """, (
            app.application_id,
            ownership.owner,
            ownership.team,
            ownership.team_id,
            ownership.slack_channel,
            ownership.email,
            ownership.repository,
            ownership.business_unit,
            ownership.cost_center,
            ownership.pagerduty_service,
            ownership.documentation_url,
            ownership.runbook_url,
            ownership.confidence,
        ))

    def _save_criticality(self, cursor: Any, app: Application) -> None:
        """Save criticality data for an application."""
        crit = app.criticality
        cursor.execute("""
            INSERT INTO application_criticality (
                application_id, revenue_impact, compliance_impact,
                availability_target, rto_minutes, rpo_minutes,
                risk_level, criticality_score, compliance_frameworks,
                customer_facing, data_classification, calculated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (application_id) DO UPDATE SET
                revenue_impact = EXCLUDED.revenue_impact,
                compliance_impact = EXCLUDED.compliance_impact,
                criticality_score = EXCLUDED.criticality_score,
                risk_level = EXCLUDED.risk_level,
                calculated_at = EXCLUDED.calculated_at
        """, (
            app.application_id,
            crit.revenue_impact,
            crit.compliance_impact,
            crit.availability_target,
            crit.recovery_time_objective_minutes,
            crit.recovery_point_objective_minutes,
            crit.risk_level.value,
            crit.criticality_score,
            json.dumps(crit.compliance_frameworks),
            crit.customer_facing,
            crit.data_classification,
            crit.calculated_at,
        ))

    def _save_deployment(self, cursor: Any, deploy: DeploymentRecord) -> None:
        """Save a deployment record."""
        cursor.execute("""
            INSERT INTO application_deployments (
                deployment_id, application_id, version, previous_version,
                strategy, status, deployed_at, completed_at, duration_seconds,
                deployed_by, commit_sha, is_rollback, change_summary, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (deployment_id) DO NOTHING
        """, (
            deploy.deployment_id,
            deploy.application_id,
            deploy.version,
            deploy.previous_version,
            deploy.strategy.value,
            deploy.status.value,
            deploy.deployed_at,
            deploy.completed_at,
            deploy.duration_seconds,
            deploy.deployed_by,
            deploy.commit_sha,
            deploy.is_rollback,
            deploy.change_summary,
            json.dumps(deploy.metadata),
        ))

    @staticmethod
    def _row_to_application(row: dict[str, Any]) -> Application:
        """Convert database row to Application model.

        Args:
            row: Database row dictionary

        Returns:
            Application model
        """
        return Application(
            application_id=row["application_id"],
            name=row["name"],
            description=row.get("description"),
            application_type=ApplicationType(row["application_type"]),
            environment=EnvironmentType(row["environment"]),
            tier=ServiceTier(row["tier"]),
            resource_ids=row.get("resource_ids") or [],
            tags=row.get("tags") or {},
            metadata=row.get("metadata") or {},
            total_monthly_cost=(
                float(row["total_monthly_cost"])
                if row.get("total_monthly_cost")
                else None
            ),
            discovery_source=row.get("discovery_source", "unknown"),
            discovered_at=row.get("discovered_at", datetime.utcnow()),
            updated_at=row.get("updated_at", datetime.utcnow()),
        )

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Application database connection closed")

    def __enter__(self) -> "ApplicationRepository":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type, exc_val: Exception, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

"""
PostgreSQL repository for discovered resources.

Implements Repository pattern for persistent storage of:
- CloudResource objects
- DependencyEdge relationships
- Discovery metadata and timestamps

Supports querying, historization, and dependency graph traversal.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from models_resource import CloudResource, DependencyEdge, ResourceGraph, ResourceType

logger = logging.getLogger(__name__)


class RepositoryError(Exception):
    """Raised when repository operations fail."""

    pass


class ResourceRepository:
    """
    PostgreSQL repository for cloud resources.

    Manages persistent storage and querying of discovered resources.
    Supports dependency graph queries and resource historization.
    """

    def __init__(self, connection_string: str) -> None:
        """
        Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            RepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise RepositoryError("psycopg2 required for PostgreSQL support") from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("ResourceRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resources (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(500),
                    type VARCHAR(50),
                    provider VARCHAR(50),
                    region VARCHAR(100),
                    state VARCHAR(50),
                    owner VARCHAR(255),
                    cost_monthly NUMERIC(10, 2),
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    discovered_at TIMESTAMP,
                    tags JSONB,
                    metadata JSONB,
                    discovered_run_id VARCHAR(255),
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS dependencies (
                    id SERIAL PRIMARY KEY,
                    source_id VARCHAR(255),
                    target_id VARCHAR(255),
                    relationship_type VARCHAR(50),
                    created_at TIMESTAMP,
                    metadata JSONB,
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES resources(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES resources(id) ON DELETE CASCADE,
                    UNIQUE(source_id, target_id, relationship_type)
                );

                CREATE INDEX IF NOT EXISTS idx_resources_provider ON resources(provider);
                CREATE INDEX IF NOT EXISTS idx_resources_type ON resources(type);
                CREATE INDEX IF NOT EXISTS idx_resources_region ON resources(region);
                CREATE INDEX IF NOT EXISTS idx_dependencies_source ON dependencies(source_id);
                CREATE INDEX IF NOT EXISTS idx_dependencies_target ON dependencies(target_id);
            """)

            self.connection.commit()
            logger.info("Database schema initialized")
        except Exception as e:
            raise RepositoryError(f"Database initialization failed: {e}") from e
        finally:
            if cursor:
                cursor.close()

    def save_resource(self, resource: CloudResource, run_id: str) -> None:
        """
        Save or update a resource.

        Args:
            resource: CloudResource to save
            run_id: Discovery run identifier

        Raises:
            RepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO resources (
                    id, name, type, provider, region, state, owner, cost_monthly,
                    created_at, updated_at, discovered_at, tags, metadata, discovered_run_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    state = EXCLUDED.state,
                    cost_monthly = EXCLUDED.cost_monthly,
                    updated_at = EXCLUDED.updated_at,
                    discovered_at = EXCLUDED.discovered_at,
                    tags = EXCLUDED.tags,
                    metadata = EXCLUDED.metadata,
                    discovered_run_id = EXCLUDED.discovered_run_id
            """, (
                resource.id,
                resource.name,
                resource.type.value,
                resource.provider,
                resource.region,
                resource.state.value,
                resource.owner,
                resource.cost_monthly,
                resource.created_at,
                resource.updated_at,
                resource.discovered_at,
                json.dumps(resource.tags),
                json.dumps(resource.metadata),
                run_id,
            ))

            self.connection.commit()
            logger.debug(f"Saved resource {resource.id}")
        except Exception as e:
            self.connection.rollback()
            raise RepositoryError(f"Failed to save resource {resource.id}: {e}") from e
        finally:
            cursor.close()

    def save_resources(self, resources: list[CloudResource], run_id: str) -> None:
        """
        Save multiple resources in batch.

        Args:
            resources: List of CloudResources
            run_id: Discovery run identifier

        Raises:
            RepositoryError: On database error
        """
        for resource in resources:
            self.save_resource(resource, run_id)
        logger.info(f"Saved {len(resources)} resources")

    def save_dependency(self, dependency: DependencyEdge) -> None:
        """
        Save resource dependency relationship.

        Args:
            dependency: DependencyEdge to save

        Raises:
            RepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO dependencies (
                    source_id, target_id, relationship_type, created_at, metadata
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_id, target_id, relationship_type) DO UPDATE SET
                    created_at = EXCLUDED.created_at,
                    metadata = EXCLUDED.metadata
            """, (
                dependency.source_id,
                dependency.target_id,
                dependency.relationship_type.value,
                dependency.created_at,
                json.dumps(dependency.metadata),
            ))

            self.connection.commit()
            logger.debug(f"Saved dependency {dependency.source_id} → {dependency.target_id}")
        except Exception as e:
            self.connection.rollback()
            raise RepositoryError(f"Failed to save dependency: {e}") from e
        finally:
            cursor.close()

    def save_dependencies(self, dependencies: list[DependencyEdge]) -> None:
        """
        Save multiple dependencies in batch.

        Args:
            dependencies: List of DependencyEdges
        """
        for dependency in dependencies:
            self.save_dependency(dependency)
        logger.info(f"Saved {len(dependencies)} dependencies")

    def get_resource(self, resource_id: str) -> Optional[CloudResource]:
        """
        Retrieve resource by ID.

        Args:
            resource_id: Resource identifier

        Returns:
            CloudResource or None if not found

        Raises:
            RepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute("SELECT * FROM resources WHERE id = %s", (resource_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_resource(row)
        except Exception as e:
            raise RepositoryError(f"Failed to get resource {resource_id}: {e}") from e
        finally:
            cursor.close()

    def get_resources_by_type(self, resource_type: ResourceType) -> list[CloudResource]:
        """
        Get all resources of a specific type.

        Args:
            resource_type: ResourceType enum value

        Returns:
            List of CloudResources

        Raises:
            RepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM resources WHERE type = %s ORDER BY created_at DESC",
                (resource_type.value,),
            )
            rows = cursor.fetchall()
            return [self._row_to_resource(row) for row in rows]
        except Exception as e:
            raise RepositoryError(f"Failed to get resources by type: {e}") from e
        finally:
            cursor.close()

    def get_resources_by_provider(self, provider: str) -> list[CloudResource]:
        """
        Get all resources from a specific cloud provider.

        Args:
            provider: Provider name (aws, azure, gcp, k8s)

        Returns:
            List of CloudResources

        Raises:
            RepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM resources WHERE provider = %s ORDER BY created_at DESC",
                (provider,),
            )
            rows = cursor.fetchall()
            return [self._row_to_resource(row) for row in rows]
        except Exception as e:
            raise RepositoryError(f"Failed to get resources by provider: {e}") from e
        finally:
            cursor.close()

    def get_resource_dependencies(self, resource_id: str) -> list[DependencyEdge]:
        """
        Get all outgoing dependencies for a resource.

        Args:
            resource_id: Resource identifier

        Returns:
            List of DependencyEdges where this resource is source

        Raises:
            RepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM dependencies WHERE source_id = %s",
                (resource_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_dependency(row) for row in rows]
        except Exception as e:
            raise RepositoryError(f"Failed to get dependencies for {resource_id}: {e}") from e
        finally:
            cursor.close()

    def get_resource_dependents(self, resource_id: str) -> list[DependencyEdge]:
        """
        Get all incoming dependencies for a resource (what depends on this).

        Args:
            resource_id: Resource identifier

        Returns:
            List of DependencyEdges where this resource is target

        Raises:
            RepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM dependencies WHERE target_id = %s",
                (resource_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_dependency(row) for row in rows]
        except Exception as e:
            raise RepositoryError(f"Failed to get dependents for {resource_id}: {e}") from e
        finally:
            cursor.close()

    def get_all_resources(self) -> list[CloudResource]:
        """
        Get all resources in repository.

        Returns:
            List of all CloudResources

        Raises:
            RepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute("SELECT * FROM resources ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [self._row_to_resource(row) for row in rows]
        except Exception as e:
            raise RepositoryError(f"Failed to get all resources: {e}") from e
        finally:
            cursor.close()

    def get_statistics(self) -> dict[str, int]:
        """
        Get repository statistics.

        Returns:
            Dict with resource counts by type and provider

        Raises:
            RepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)

            cursor.execute("SELECT COUNT(*) as total FROM resources")
            total = cursor.fetchone()["total"]

            cursor.execute(
                "SELECT type, COUNT(*) as count FROM resources GROUP BY type"
            )
            by_type = {row["type"]: row["count"] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT provider, COUNT(*) as count FROM resources GROUP BY provider"
            )
            by_provider = {row["provider"]: row["count"] for row in cursor.fetchall()}

            return {
                "total_resources": total,
                "by_type": by_type,
                "by_provider": by_provider,
            }
        except Exception as e:
            raise RepositoryError(f"Failed to get statistics: {e}") from e
        finally:
            cursor.close()

    def _row_to_resource(self, row: dict) -> CloudResource:
        """Convert database row to CloudResource."""
        return CloudResource(
            id=row["id"],
            name=row["name"],
            type=ResourceType(row["type"]),
            provider=row["provider"],
            region=row["region"],
            state=row["state"],
            owner=row["owner"],
            cost_monthly=float(row["cost_monthly"]) if row["cost_monthly"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            discovered_at=row["discovered_at"],
            tags=row["tags"] or {},
            metadata=row["metadata"] or {},
        )

    def _row_to_dependency(self, row: dict) -> DependencyEdge:
        """Convert database row to DependencyEdge."""
        from models_resource import DependencyType
        
        return DependencyEdge(
            source_id=row["source_id"],
            target_id=row["target_id"],
            relationship_type=DependencyType(row["relationship_type"]),
            created_at=row["created_at"],
            metadata=row["metadata"] or {},
        )

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

    def __enter__(self) -> "ResourceRepository":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()

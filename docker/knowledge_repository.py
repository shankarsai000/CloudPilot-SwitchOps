"""
Knowledge Repository — PostgreSQL persistence for knowledge graph entities.

Stores knowledge nodes and edges with support for adjacency queries.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from models_learning import KnowledgeNode, KnowledgeEdge

logger = logging.getLogger(__name__)


class KnowledgeRepositoryError(Exception):
    """Raised when knowledge repository operations fail."""

    pass


class KnowledgeRepository:
    """PostgreSQL repository for knowledge graph persistence."""

    def __init__(self, connection_string: str) -> None:
        """Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            KnowledgeRepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise KnowledgeRepositoryError(
                "psycopg2 required for PostgreSQL support"
            ) from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("KnowledgeRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_nodes (
                    node_id VARCHAR(255) PRIMARY KEY,
                    node_type VARCHAR(100) NOT NULL,
                    label VARCHAR(500) NOT NULL,
                    properties JSONB
                );

                CREATE TABLE IF NOT EXISTS knowledge_edges (
                    id SERIAL PRIMARY KEY,
                    source_id VARCHAR(255) NOT NULL,
                    target_id VARCHAR(255) NOT NULL,
                    edge_type VARCHAR(100) NOT NULL,
                    weight NUMERIC(8, 4) DEFAULT 1.0,
                    properties JSONB
                );

                CREATE INDEX IF NOT EXISTS idx_edge_source ON knowledge_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_edge_target ON knowledge_edges(target_id);
                CREATE INDEX IF NOT EXISTS idx_node_type ON knowledge_nodes(node_type);
            """)

            self.connection.commit()
            logger.info("Knowledge database schema initialized")
        except Exception as e:
            raise KnowledgeRepositoryError(
                f"Database initialization failed: {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def save_node(self, node: KnowledgeNode) -> None:
        """Save a knowledge node (upsert).

        Args:
            node: KnowledgeNode to save

        Raises:
            KnowledgeRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO knowledge_nodes (node_id, node_type, label, properties)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (node_id) DO UPDATE SET
                    node_type = EXCLUDED.node_type,
                    label = EXCLUDED.label,
                    properties = EXCLUDED.properties
            """, (
                node.node_id,
                node.node_type.value,
                node.label,
                json.dumps(node.properties),
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise KnowledgeRepositoryError(f"Failed to save node: {e}") from e
        finally:
            cursor.close()

    def save_edge(self, edge: KnowledgeEdge) -> None:
        """Save a knowledge edge.

        Args:
            edge: KnowledgeEdge to save

        Raises:
            KnowledgeRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO knowledge_edges (source_id, target_id, edge_type, weight, properties)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                edge.source_id,
                edge.target_id,
                edge.edge_type.value,
                edge.weight,
                json.dumps(edge.properties),
            ))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise KnowledgeRepositoryError(f"Failed to save edge: {e}") from e
        finally:
            cursor.close()

    def get_neighbors(self, node_id: str) -> list[dict[str, Any]]:
        """Get all nodes connected from a given node.

        Args:
            node_id: Source node ID

        Returns:
            List of neighbor node dicts
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute("""
                SELECT n.* FROM knowledge_nodes n
                JOIN knowledge_edges e ON e.target_id = n.node_id
                WHERE e.source_id = %s
            """, (node_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            raise KnowledgeRepositoryError(f"Failed to get neighbors: {e}") from e
        finally:
            cursor.close()

    def get_all_nodes(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Get all knowledge nodes.

        Args:
            limit: Maximum nodes to return

        Returns:
            List of node dicts
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM knowledge_nodes LIMIT %s", (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            raise KnowledgeRepositoryError(f"Failed to get nodes: {e}") from e
        finally:
            cursor.close()

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Knowledge database connection closed")

    def __enter__(self) -> "KnowledgeRepository":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type, exc_val: Exception, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

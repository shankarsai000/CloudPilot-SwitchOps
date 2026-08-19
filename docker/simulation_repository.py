"""
Simulation Repository — PostgreSQL persistence for M6 entities.

Stores digital twins, simulation reports, and comparative analysis results.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from models_simulation import SimulationReport, DigitalTwin

logger = logging.getLogger(__name__)


class SimulationRepositoryError(Exception):
    """Raised when simulation repository operations fail."""

    pass


class SimulationRepository:
    """PostgreSQL repository for Simulation & Predictive Intelligence data."""

    def __init__(self, connection_string: str) -> None:
        """Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            SimulationRepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise SimulationRepositoryError(
                "psycopg2 required for PostgreSQL support"
            ) from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("SimulationRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS digital_twins (
                    twin_id VARCHAR(255) PRIMARY KEY,
                    resources JSONB,
                    applications JSONB,
                    cost_model JSONB,
                    dependency_graph JSONB,
                    policies JSONB,
                    snapshot_time TIMESTAMP,
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS simulation_reports (
                    simulation_id VARCHAR(255) PRIMARY KEY,
                    target_id VARCHAR(255) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    safety_score NUMERIC(5, 2) NOT NULL,
                    safety_status VARCHAR(50) NOT NULL,
                    performance JSONB,
                    cost JSONB,
                    rollback JSONB,
                    cascading_failures JSONB,
                    execution_readiness_score NUMERIC(5, 2) NOT NULL,
                    simulated_at TIMESTAMP,
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sim_target ON simulation_reports(target_id);
                CREATE INDEX IF NOT EXISTS idx_sim_safety ON simulation_reports(safety_status);
            """)

            self.connection.commit()
            logger.info("Simulation database schema initialized")
        except Exception as e:
            raise SimulationRepositoryError(
                f"Database initialization failed: {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def save_twin(self, twin: DigitalTwin) -> None:
        """Save a digital twin representative state.

        Args:
            twin: DigitalTwin state context to save

        Raises:
            SimulationRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO digital_twins (
                    twin_id, resources, applications, cost_model,
                    dependency_graph, policies, snapshot_time
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (twin_id) DO NOTHING
            """, (
                twin.twin_id,
                json.dumps(twin.resources),
                json.dumps(twin.applications),
                json.dumps(twin.cost_model),
                json.dumps(twin.dependency_graph),
                json.dumps(twin.policies),
                twin.snapshot_time
            ))

            self.connection.commit()
            logger.debug("Saved digital twin %s", twin.twin_id)
        except Exception as e:
            self.connection.rollback()
            raise SimulationRepositoryError(
                f"Failed to save digital twin {twin.twin_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def save_simulation(self, report: SimulationReport) -> None:
        """Save a simulation report.

        Args:
            report: SimulationReport to save

        Raises:
            SimulationRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO simulation_reports (
                    simulation_id, target_id, action, safety_score,
                    safety_status, performance, cost, rollback,
                    cascading_failures, execution_readiness_score, simulated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (simulation_id) DO UPDATE SET
                    safety_score = EXCLUDED.safety_score,
                    safety_status = EXCLUDED.safety_status,
                    performance = EXCLUDED.performance,
                    cost = EXCLUDED.cost,
                    rollback = EXCLUDED.rollback,
                    cascading_failures = EXCLUDED.cascading_failures,
                    execution_readiness_score = EXCLUDED.execution_readiness_score
            """, (
                report.simulation_id,
                report.target_id,
                report.action,
                report.safety_score,
                report.safety_status,
                json.dumps(report.performance.dict()),
                json.dumps(report.cost.dict()),
                json.dumps(report.rollback.dict()),
                json.dumps(report.cascading_failures),
                report.execution_readiness_score,
                report.simulated_at
            ))

            self.connection.commit()
            logger.debug("Saved simulation report %s", report.simulation_id)
        except Exception as e:
            self.connection.rollback()
            raise SimulationRepositoryError(
                f"Failed to save simulation report {report.simulation_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def get_simulation(self, simulation_id: str) -> Optional[SimulationReport]:
        """Retrieve simulation report by ID.

        Args:
            simulation_id: Simulation identifier

        Returns:
            SimulationReport or None if not found
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM simulation_reports WHERE simulation_id = %s",
                (simulation_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_simulation(row)
        except Exception as e:
            raise SimulationRepositoryError(
                f"Failed to get simulation report {simulation_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def get_history(self, limit: int = 50) -> list[SimulationReport]:
        """Get history of simulations.

        Args:
            limit: Maximum records to return

        Returns:
            List of SimulationReport objects
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM simulation_reports ORDER BY simulated_at DESC LIMIT %s",
                (limit,)
            )
            rows = cursor.fetchall()
            return [self._row_to_simulation(row) for row in rows]
        except Exception as e:
            raise SimulationRepositoryError(f"Failed to fetch history: {e}") from e
        finally:
            cursor.close()

    def _row_to_simulation(self, row: dict[str, Any]) -> SimulationReport:
        """Convert database row to SimulationReport model."""
        from models_simulation import PerformanceForecast, CostForecast, RollbackReport

        perf_raw = row["performance"]
        perf = PerformanceForecast(
            cpu_utilization=float(perf_raw["cpu_utilization"]),
            memory_utilization=float(perf_raw["memory_utilization"]),
            latency_ms=float(perf_raw["latency_ms"]),
            throughput_rps=float(perf_raw["throughput_rps"]),
            error_rate=float(perf_raw["error_rate"]),
            availability_percentage=float(perf_raw["availability_percentage"])
        )

        cost_raw = row["cost"]
        cost = CostForecast(
            immediate_savings_usd=float(cost_raw["immediate_savings_usd"]),
            monthly_savings_usd=float(cost_raw["monthly_savings_usd"]),
            migration_cost_usd=float(cost_raw["migration_cost_usd"]),
            future_bill_monthly_usd=float(cost_raw["future_bill_monthly_usd"])
        )

        rollback_raw = row["rollback"]
        rollback = RollbackReport(
            rollback_duration_minutes=float(rollback_raw["rollback_duration_minutes"]),
            rollback_complexity=rollback_raw["rollback_complexity"],
            rollback_probability_percentage=float(rollback_raw["rollback_probability_percentage"]),
            recovery_confidence_percentage=float(rollback_raw["recovery_confidence_percentage"])
        )

        return SimulationReport(
            simulation_id=row["simulation_id"],
            target_id=row["target_id"],
            action=row["action"],
            safety_score=float(row["safety_score"]),
            safety_status=row["safety_status"],
            performance=perf,
            cost=cost,
            rollback=rollback,
            cascading_failures=row["cascading_failures"] or [],
            execution_readiness_score=float(row["execution_readiness_score"]),
            simulated_at=row["simulated_at"]
        )

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Simulation database connection closed")

    def __enter__(self) -> "SimulationRepository":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type, exc_val: Exception, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

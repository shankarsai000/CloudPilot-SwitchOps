"""
Strategy Repository — PostgreSQL persistence for M5 entities.

Stores optimization plans, recommendations, and roadmaps.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from models_strategy import OptimizationPlan

logger = logging.getLogger(__name__)


class StrategyRepositoryError(Exception):
    """Raised when strategy repository operations fail."""

    pass


class StrategyRepository:
    """PostgreSQL repository for Strategic Decision Intelligence data."""

    def __init__(self, connection_string: str) -> None:
        """Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string

        Raises:
            StrategyRepositoryError: If psycopg2 not installed
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError as e:
            raise StrategyRepositoryError(
                "psycopg2 required for PostgreSQL support"
            ) from e

        self.connection_string = connection_string
        self.psycopg2 = psycopg2
        self.RealDictCursor = RealDictCursor
        self.connection = None
        self._init_db()
        logger.info("StrategyRepository initialized")

    def _init_db(self) -> None:
        """Create necessary tables if they don't exist."""
        try:
            self.connection = self.psycopg2.connect(self.connection_string)
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS optimization_plans (
                    plan_id VARCHAR(255) PRIMARY KEY,
                    executive_summary TEXT NOT NULL,
                    current_state TEXT NOT NULL,
                    problem_statement TEXT NOT NULL,
                    candidate_strategies JSONB,
                    trade_off_analysis TEXT,
                    recommended_strategy JSONB,
                    expected_savings_monthly NUMERIC(12, 2) NOT NULL,
                    risk_assessment JSONB,
                    roi_analysis JSONB,
                    execution_blueprint JSONB,
                    success_metrics JSONB,
                    created_at TIMESTAMP,
                    created_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_plan_savings ON optimization_plans(expected_savings_monthly);
            """)

            self.connection.commit()
            logger.info("Strategy database schema initialized")
        except Exception as e:
            raise StrategyRepositoryError(
                f"Database initialization failed: {e}"
            ) from e
        finally:
            if cursor:
                cursor.close()

    def save_plan(self, plan: OptimizationPlan) -> None:
        """Save or update an optimization plan.

        Args:
            plan: OptimizationPlan to save

        Raises:
            StrategyRepositoryError: On database error
        """
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO optimization_plans (
                    plan_id, executive_summary, current_state, problem_statement,
                    candidate_strategies, trade_off_analysis, recommended_strategy,
                    expected_savings_monthly, risk_assessment, roi_analysis,
                    execution_blueprint, success_metrics, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (plan_id) DO UPDATE SET
                    executive_summary = EXCLUDED.executive_summary,
                    current_state = EXCLUDED.current_state,
                    problem_statement = EXCLUDED.problem_statement,
                    candidate_strategies = EXCLUDED.candidate_strategies,
                    trade_off_analysis = EXCLUDED.trade_off_analysis,
                    recommended_strategy = EXCLUDED.recommended_strategy,
                    expected_savings_monthly = EXCLUDED.expected_savings_monthly,
                    risk_assessment = EXCLUDED.risk_assessment,
                    roi_analysis = EXCLUDED.roi_analysis,
                    execution_blueprint = EXCLUDED.execution_blueprint,
                    success_metrics = EXCLUDED.success_metrics
            """, (
                plan.plan_id,
                plan.executive_summary,
                plan.current_state,
                plan.problem_statement,
                json.dumps([c.dict() for c in plan.candidate_strategies]),
                plan.trade_off_analysis,
                json.dumps(plan.recommended_strategy.dict()),
                plan.expected_savings_monthly,
                json.dumps(plan.risk_assessment),
                json.dumps(plan.roi_analysis.dict()),
                json.dumps(plan.execution_blueprint),
                json.dumps(plan.success_metrics),
                plan.created_at
            ))

            self.connection.commit()
            logger.debug("Saved optimization plan %s", plan.plan_id)
        except Exception as e:
            self.connection.rollback()
            raise StrategyRepositoryError(
                f"Failed to save optimization plan {plan.plan_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def get_plan(self, plan_id: str) -> Optional[OptimizationPlan]:
        """Retrieve optimization plan by ID.

        Args:
            plan_id: Plan identifier

        Returns:
            OptimizationPlan or None if not found
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM optimization_plans WHERE plan_id = %s",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_plan(row)
        except Exception as e:
            raise StrategyRepositoryError(
                f"Failed to get plan {plan_id}: {e}"
            ) from e
        finally:
            cursor.close()

    def get_all_plans(self) -> list[OptimizationPlan]:
        """Get all optimization plans.

        Returns:
            List of all OptimizationPlan objects
        """
        try:
            cursor = self.connection.cursor(cursor_factory=self.RealDictCursor)
            cursor.execute(
                "SELECT * FROM optimization_plans ORDER BY expected_savings_monthly DESC"
            )
            rows = cursor.fetchall()
            return [self._row_to_plan(row) for row in rows]
        except Exception as e:
            raise StrategyRepositoryError(
                f"Failed to get all plans: {e}"
            ) from e
        finally:
            cursor.close()

    def _row_to_plan(self, row: dict[str, Any]) -> OptimizationPlan:
        """Convert database row to OptimizationPlan model."""
        from models_strategy import CandidateStrategy, ROIMetrics

        candidates = [
            CandidateStrategy(
                strategy_id=c["strategy_id"],
                name=c["name"],
                expected_savings_monthly=float(c["expected_savings_monthly"]),
                risk_level=c["risk_level"],
                confidence_score=float(c["confidence_score"]),
                description=c["description"]
            )
            for c in (row["candidate_strategies"] or [])
        ]

        rec_raw = row["recommended_strategy"]
        recommended = CandidateStrategy(
            strategy_id=rec_raw["strategy_id"],
            name=rec_raw["name"],
            expected_savings_monthly=float(rec_raw["expected_savings_monthly"]),
            risk_level=rec_raw["risk_level"],
            confidence_score=float(rec_raw["confidence_score"]),
            description=rec_raw["description"]
        )

        roi_raw = row["roi_analysis"]
        roi = ROIMetrics(
            expected_savings_monthly=float(roi_raw["expected_savings_monthly"]),
            implementation_cost=float(roi_raw["implementation_cost"]),
            engineering_hours=float(roi_raw["engineering_hours"]),
            payback_period_days=float(roi_raw["payback_period_days"]),
            roi_score=float(roi_raw["roi_score"])
        )

        return OptimizationPlan(
            plan_id=row["plan_id"],
            executive_summary=row["executive_summary"],
            current_state=row["current_state"],
            problem_statement=row["problem_statement"],
            candidate_strategies=candidates,
            trade_off_analysis=row["trade_off_analysis"],
            recommended_strategy=recommended,
            expected_savings_monthly=float(row["expected_savings_monthly"]),
            risk_assessment=row["risk_assessment"] or {},
            roi_analysis=roi,
            execution_blueprint=row["execution_blueprint"] or [],
            success_metrics=row["success_metrics"] or [],
            created_at=row["created_at"]
        )

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Strategy database connection closed")

    def __enter__(self) -> "StrategyRepository":
        """Context manager entry."""
        return self

    def __exit__(
        self, exc_type: type, exc_val: Exception, exc_tb: object
    ) -> None:
        """Context manager exit."""
        self.close()

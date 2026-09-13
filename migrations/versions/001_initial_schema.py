"""Initial CloudPilot Platform Schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-13 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Platform Auth & Audit
    op.create_table(
        "platform_users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("teams", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_platform_users_username", "platform_users", ["username"])
    op.create_index("ix_platform_users_email", "platform_users", ["email"])

    op.create_table(
        "platform_api_keys",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("key_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="operator"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "platform_audit_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_platform_audit_actor", "platform_audit_logs", ["actor_id"])

    # 2. M1 Infrastructure Resources
    op.create_table(
        "resources",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("region", sa.String(100), nullable=False),
        sa.Column("state", sa.String(50), nullable=False, server_default="running"),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("cost_monthly", sa.Numeric(12, 2), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_resources_provider", "resources", ["provider"])
    op.create_index("ix_resources_type", "resources", ["type"])

    op.create_table(
        "dependencies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("relationship_type", sa.String(50), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dependencies_source", "dependencies", ["source_id"])

    # 3. M2 Cost Intelligence
    op.create_table(
        "cost_events",
        sa.Column("cost_event_id", sa.String(255), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("resource_name", sa.String(255), nullable=True),
        sa.Column("app_id", sa.String(255), nullable=True),
        sa.Column("team_id", sa.String(255), nullable=True),
        sa.Column("service", sa.String(255), nullable=False),
        sa.Column("cost_category", sa.String(50), nullable=False),
        sa.Column("daily_cost", sa.Numeric(15, 2), nullable=False),
        sa.Column("monthly_cost_estimate", sa.Numeric(15, 2), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_confidence", sa.Float(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cost_events_provider", "cost_events", ["provider"])
    op.create_index("ix_cost_events_team", "cost_events", ["team_id"])

    op.create_table(
        "cost_anomalies",
        sa.Column("anomaly_id", sa.String(255), primary_key=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("resource_name", sa.String(255), nullable=True),
        sa.Column("service", sa.String(255), nullable=False),
        sa.Column("cost_category", sa.String(50), nullable=False),
        sa.Column("anomaly_type", sa.String(50), nullable=False),
        sa.Column("baseline_daily_cost", sa.Numeric(15, 2), nullable=False),
        sa.Column("anomaly_daily_cost", sa.Numeric(15, 2), nullable=False),
        sa.Column("spike_percentage", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("root_cause_hypothesis", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 4. M3 Applications
    op.create_table(
        "applications",
        sa.Column("application_id", sa.String(255), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("app_type", sa.String(50), nullable=False, server_default="custom"),
        sa.Column("environment", sa.String(50), nullable=False, server_default="production"),
        sa.Column("criticality", sa.String(50), nullable=False, server_default="tier_2"),
        sa.Column("owner_team", sa.String(255), nullable=True),
        sa.Column("services", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 5. M4 Risk Assessments
    op.create_table(
        "risk_assessments",
        sa.Column("assessment_id", sa.String(255), primary_key=True),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(50), nullable=False),
        sa.Column("blast_radius_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mitigations", sa.JSON(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 6. M9 Decisions
    op.create_table(
        "decisions",
        sa.Column("decision_id", sa.String(255), primary_key=True),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("package_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 7. M10 Executions
    op.create_table(
        "executions",
        sa.Column("execution_id", sa.String(255), primary_key=True),
        sa.Column("decision_id", sa.String(255), nullable=False),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("logs", sa.JSON(), nullable=True),
        sa.Column("rollback_status", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("executions")
    op.drop_table("decisions")
    op.drop_table("risk_assessments")
    op.drop_table("applications")
    op.drop_table("cost_anomalies")
    op.drop_table("cost_events")
    op.drop_table("dependencies")
    op.drop_table("resources")
    op.drop_table("platform_audit_logs")
    op.drop_table("platform_api_keys")
    op.drop_table("platform_users")

"""
Declarative SQLAlchemy ORM models for CloudPilot AI Platform.
Covers core platform entities (auth, audit) and all modules (M1 to M10).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base, TimestampMixin


# ══════════════════════════════════════════════════════════════════
# Core Platform Auth & Audit Models
# ══════════════════════════════════════════════════════════════════

class UserRecord(Base, TimestampMixin):
    """User account model for authentication and RBAC."""
    __tablename__ = "platform_users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    teams: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=list)


class APIKeyRecord(Base, TimestampMixin):
    """API key for service-to-service and automated access."""
    __tablename__ = "platform_api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="operator", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLogRecord(Base, TimestampMixin):
    """Immutable audit trail for decisions, executions, and security events."""
    __tablename__ = "platform_audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)


# ══════════════════════════════════════════════════════════════════
# M1: Infrastructure Discovery Models
# ══════════════════════════════════════════════════════════════════

class ResourceRecord(Base, TimestampMixin):
    """Cloud infrastructure resource discovered by M1."""
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    region: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(50), default="running", nullable=False)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cost_monthly: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    resource_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DependencyRecord(Base, TimestampMixin):
    """Resource-to-resource dependency relationship edge."""
    __tablename__ = "dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    edge_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, default=dict)


# ══════════════════════════════════════════════════════════════════
# M2: Cost Intelligence Models
# ══════════════════════════════════════════════════════════════════

class CostEventRecord(Base, TimestampMixin):
    """Ingested and correlated cost event."""
    __tablename__ = "cost_events"

    cost_event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    resource_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    app_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    service: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    cost_category: Mapped[str] = mapped_column(String(50), nullable=False)
    daily_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    monthly_cost_estimate: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    correlation_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class CostAnomalyRecord(Base, TimestampMixin):
    """Detected cost anomaly / spike."""
    __tablename__ = "cost_anomalies"

    anomaly_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    resource_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False)
    cost_category: Mapped[str] = mapped_column(String(50), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(50), nullable=False)
    baseline_daily_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    anomaly_daily_cost: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    spike_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    root_cause_hypothesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ══════════════════════════════════════════════════════════════════
# M3: Application Intelligence Models
# ══════════════════════════════════════════════════════════════════

class ApplicationRecord(Base, TimestampMixin):
    """Discovered business application."""
    __tablename__ = "applications"

    application_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    app_type: Mapped[str] = mapped_column(String(50), default="custom", nullable=False)
    environment: Mapped[str] = mapped_column(String(50), default="production", nullable=False)
    criticality: Mapped[str] = mapped_column(String(50), default="tier_2", nullable=False)
    owner_team: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    services: Mapped[Optional[List[Any]]] = mapped_column(JSON, default=list)


# ══════════════════════════════════════════════════════════════════
# M4: Risk Intelligence Models
# ══════════════════════════════════════════════════════════════════

class RiskAssessmentRecord(Base, TimestampMixin):
    """Operational risk assessment for actions or topologies."""
    __tablename__ = "risk_assessments"

    assessment_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    target_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    blast_radius_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mitigations: Mapped[Optional[List[Any]]] = mapped_column(JSON, default=list)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


# ══════════════════════════════════════════════════════════════════
# M9 & M10: Decisions & Executions
# ══════════════════════════════════════════════════════════════════

class DecisionRecordTable(Base, TimestampMixin):
    """Decision record generated by Decision Engine (M9)."""
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    target_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    package_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class ExecutionRecordTable(Base, TimestampMixin):
    """Execution record tracked by Autonomous Execution Agent (M10)."""
    __tablename__ = "executions"

    execution_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    logs: Mapped[Optional[List[Any]]] = mapped_column(JSON, default=list)
    rollback_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

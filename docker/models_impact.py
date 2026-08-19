"""
Risk Intelligence Agent - Pydantic Models for Business Impact and Blast Radius

Defines impact assessment, blast radius reports, and impact graphs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class BlastRadiusReport(BaseModel):
    """Details of the blast radius when an infrastructure action occurs."""

    affected_resource_ids: list[str] = Field(default_factory=list, description="IDs of raw cloud resources directly/indirectly affected")
    affected_service_ids: list[str] = Field(default_factory=list, description="IDs of service nodes affected")
    affected_application_ids: list[str] = Field(default_factory=list, description="IDs of applications affected")
    affected_teams: list[str] = Field(default_factory=list, description="Names of engineering/ops teams affected")
    affected_users_count: int = Field(default=0, ge=0, description="Predicted number of affected end-users")
    revenue_exposure_usd: float = Field(default=0.0, ge=0.0, description="Estimated revenue at risk in USD")
    recovery_complexity: str = Field(default="LOW", description="Complexity of system recovery (LOW, MEDIUM, HIGH, COMPLEX)")
    has_spof: bool = Field(default=False, description="Whether the affected node constitutes a Single Point of Failure")


class BusinessImpactReport(BaseModel):
    """Details of the business-level damage from an action."""

    revenue_impact_score: float = Field(..., ge=0.0, le=10.0, description="Revenue damage scale (0-10)")
    customer_impact_score: float = Field(..., ge=0.0, le=10.0, description="Customer-facing disruption scale (0-10)")
    compliance_impact_score: float = Field(..., ge=0.0, le=10.0, description="Compliance breach or policy violation scale (0-10)")
    sla_impact_score: float = Field(..., ge=0.0, le=10.0, description="SLA violation probability scale (0-10)")
    engineering_impact_score: float = Field(..., ge=0.0, le=10.0, description="Complexity/effort to restore scale (0-10)")
    is_business_hours: bool = Field(default=False, description="Whether this change occurs during active business hours")


class ImpactGraphNode(BaseModel):
    """Single node in the impact propagation graph."""

    id: str = Field(..., description="Node identifier")
    name: str = Field(..., description="Human-readable node name")
    type: str = Field(..., description="Node type: resource, service, application, business_unit")
    risk_level: str = Field(..., description="Calculated node-specific risk level")


class ImpactGraphEdge(BaseModel):
    """Directed connection in the impact propagation graph."""

    source: str = Field(..., description="Upstream node ID")
    target: str = Field(..., description="Downstream node ID")
    relationship: str = Field(..., description="Relationship context")


class ImpactGraph(BaseModel):
    """Complete impact propagation graph showing cascading effects of simulated action."""

    nodes: list[ImpactGraphNode] = Field(default_factory=list)
    edges: list[ImpactGraphEdge] = Field(default_factory=list)

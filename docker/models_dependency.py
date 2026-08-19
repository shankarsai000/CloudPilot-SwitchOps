"""
Application Intelligence Agent - Dependency Graph Models

Defines dependency graph models for representing service-to-service
relationships with type classification and cycle detection results.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DependencyEdgeType(str, Enum):
    """Classification of dependency edge type."""

    RUNTIME = "runtime"
    BUILD = "build"
    DATA = "data"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    EVENT = "event"
    UNKNOWN = "unknown"


class DependencyStrength(str, Enum):
    """Strength of dependency relationship."""

    STRONG = "strong"       # Service fails without this dependency
    MODERATE = "moderate"   # Degraded performance without dependency
    WEAK = "weak"           # Optional, graceful degradation
    UNKNOWN = "unknown"


class DependencyGraphNode(BaseModel):
    """Node in the dependency graph with type classification."""

    node_id: str = Field(..., description="Unique node identifier")
    name: str = Field(..., description="Human-readable name")
    node_type: str = Field(default="service", description="Node type classification")
    application_id: Optional[str] = Field(
        None, description="Parent application ID"
    )
    resource_ids: list[str] = Field(
        default_factory=list, description="Bound M1 resource IDs"
    )
    in_degree: int = Field(default=0, ge=0, description="Number of incoming edges")
    out_degree: int = Field(default=0, ge=0, description="Number of outgoing edges")
    is_leaf: bool = Field(default=False, description="Node has no outgoing dependencies")
    is_root: bool = Field(default=False, description="Node has no incoming dependencies")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Node metadata")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "node_id": "svc-payment-api",
                "name": "Payment API",
                "node_type": "service",
                "application_id": "app-payment-service",
                "in_degree": 2,
                "out_degree": 3,
                "is_leaf": False,
                "is_root": False,
            }
        }


class DependencyGraphEdge(BaseModel):
    """Typed edge in the dependency graph."""

    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    edge_type: DependencyEdgeType = Field(
        default=DependencyEdgeType.RUNTIME, description="Dependency edge type"
    )
    strength: DependencyStrength = Field(
        default=DependencyStrength.UNKNOWN, description="Dependency strength"
    )
    protocol: str = Field(default="unknown", description="Communication protocol")
    port: Optional[int] = Field(None, description="Target port")
    latency_ms: Optional[float] = Field(None, description="Average latency")
    description: Optional[str] = Field(None, description="Human-readable description")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Edge metadata")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "source_id": "svc-api-gateway",
                "target_id": "svc-payment-api",
                "edge_type": "runtime",
                "strength": "strong",
                "protocol": "https",
                "port": 8443,
                "description": "API Gateway routes /payments/* to Payment API",
            }
        }


class CycleDependency(BaseModel):
    """Represents a detected circular dependency cycle."""

    cycle_id: str = Field(..., description="Unique cycle identifier")
    nodes: list[str] = Field(..., description="Node IDs forming the cycle")
    severity: str = Field(
        default="warning", description="Severity: critical, warning, info"
    )
    description: str = Field(
        default="", description="Human-readable cycle description"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "cycle_id": "cycle-001",
                "nodes": ["svc-order-api", "svc-inventory-api", "svc-order-api"],
                "severity": "warning",
                "description": "Circular dependency: Order API → Inventory API → Order API",
            }
        }


class DependencyGraph(BaseModel):
    """Complete dependency graph with cycle detection results."""

    application_id: Optional[str] = Field(
        None, description="Application ID (None for cross-application graph)"
    )
    nodes: list[DependencyGraphNode] = Field(
        default_factory=list, description="Graph nodes"
    )
    edges: list[DependencyGraphEdge] = Field(
        default_factory=list, description="Graph edges"
    )
    cycles: list[CycleDependency] = Field(
        default_factory=list, description="Detected circular dependencies"
    )
    has_cycles: bool = Field(default=False, description="Whether cycles were detected")
    total_nodes: int = Field(default=0, ge=0, description="Total node count")
    total_edges: int = Field(default=0, ge=0, description="Total edge count")
    max_depth: int = Field(default=0, ge=0, description="Maximum graph depth")
    critical_path: list[str] = Field(
        default_factory=list, description="Longest dependency chain (node IDs)"
    )
    built_at: datetime = Field(
        default_factory=datetime.utcnow, description="Build timestamp"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "application_id": "app-payment-service",
                "total_nodes": 8,
                "total_edges": 12,
                "has_cycles": False,
                "cycles": [],
                "max_depth": 4,
                "critical_path": [
                    "svc-frontend",
                    "svc-api-gateway",
                    "svc-payment-api",
                    "svc-postgres",
                ],
            }
        }

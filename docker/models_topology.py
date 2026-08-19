"""
Application Intelligence Agent - Topology Models

Defines topology-specific models for representing application deployment
topology with layered architecture (frontend, backend, data, cache, etc.).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TopologyLayer(str, Enum):
    """Logical layer classification in application topology."""

    INGRESS = "ingress"
    FRONTEND = "frontend"
    API_GATEWAY = "api_gateway"
    BACKEND = "backend"
    DATA = "data"
    CACHE = "cache"
    QUEUE = "queue"
    STORAGE = "storage"
    EXTERNAL = "external"
    MONITORING = "monitoring"
    UNKNOWN = "unknown"


class HealthStatus(str, Enum):
    """Health status for topology nodes."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class TopologyNode(BaseModel):
    """Node in the application topology with layer assignment."""

    node_id: str = Field(..., description="Unique node identifier")
    name: str = Field(..., description="Human-readable node name")
    layer: TopologyLayer = Field(
        default=TopologyLayer.UNKNOWN, description="Topology layer assignment"
    )
    service_type: str = Field(default="unknown", description="Service type classification")
    resource_ids: list[str] = Field(
        default_factory=list, description="Bound M1 resource IDs"
    )
    health: HealthStatus = Field(
        default=HealthStatus.UNKNOWN, description="Current health status"
    )
    replicas: int = Field(default=1, ge=0, description="Number of replicas/instances")
    port: Optional[int] = Field(None, description="Primary service port")
    protocol: str = Field(default="unknown", description="Primary communication protocol")
    cpu_utilization: Optional[float] = Field(None, description="CPU utilization %")
    memory_utilization: Optional[float] = Field(None, description="Memory utilization %")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Node metadata")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "node_id": "node-payment-api",
                "name": "Payment API",
                "layer": "backend",
                "service_type": "backend",
                "resource_ids": ["ec2-001", "ec2-002"],
                "health": "healthy",
                "replicas": 3,
                "port": 8443,
                "protocol": "https",
            }
        }


class TopologyEdge(BaseModel):
    """Edge in the application topology with traffic metadata."""

    source_node_id: str = Field(..., description="Source node ID")
    target_node_id: str = Field(..., description="Target node ID")
    protocol: str = Field(default="unknown", description="Communication protocol")
    port: Optional[int] = Field(None, description="Target port")
    requests_per_second: Optional[float] = Field(None, description="Average RPS")
    latency_ms: Optional[float] = Field(None, description="Average latency in ms")
    error_rate: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Error rate (0.0-1.0)"
    )
    is_encrypted: bool = Field(default=False, description="Whether traffic is encrypted")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Edge metadata")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "source_node_id": "node-api-gateway",
                "target_node_id": "node-payment-api",
                "protocol": "https",
                "port": 8443,
                "requests_per_second": 450.0,
                "latency_ms": 12.5,
                "is_encrypted": True,
            }
        }


class ApplicationTopology(BaseModel):
    """Complete topology for a single application.

    Organizes services into logical layers and tracks
    their interconnections with traffic metadata.
    """

    application_id: str = Field(..., description="Application identifier")
    nodes: list[TopologyNode] = Field(
        default_factory=list, description="Topology nodes"
    )
    edges: list[TopologyEdge] = Field(
        default_factory=list, description="Topology edges"
    )
    layers: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Layer → node IDs mapping"
    )
    entry_points: list[str] = Field(
        default_factory=list, description="Ingress node IDs"
    )
    data_stores: list[str] = Field(
        default_factory=list, description="Data layer node IDs"
    )
    external_dependencies: list[str] = Field(
        default_factory=list, description="External dependency node IDs"
    )
    depth: int = Field(default=0, ge=0, description="Maximum topology depth")
    built_at: datetime = Field(
        default_factory=datetime.utcnow, description="Topology build timestamp"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "application_id": "app-payment-service",
                "nodes": [],
                "edges": [],
                "layers": {
                    "ingress": ["node-alb"],
                    "backend": ["node-payment-api"],
                    "data": ["node-postgres", "node-redis"],
                },
                "entry_points": ["node-alb"],
                "data_stores": ["node-postgres", "node-redis"],
                "external_dependencies": [],
                "depth": 3,
            }
        }


class DeploymentTopology(BaseModel):
    """Deployment-aware topology with infrastructure bindings.

    Extends application topology with deployment-specific
    information such as availability zones and scaling configuration.
    """

    application_id: str = Field(..., description="Application identifier")
    topology: ApplicationTopology = Field(..., description="Base application topology")
    availability_zones: list[str] = Field(
        default_factory=list, description="AZs used by this deployment"
    )
    regions: list[str] = Field(
        default_factory=list, description="Regions used by this deployment"
    )
    providers: list[str] = Field(
        default_factory=list, description="Cloud providers used"
    )
    total_instances: int = Field(default=0, ge=0, description="Total instances/replicas")
    auto_scaling_enabled: bool = Field(
        default=False, description="Whether auto-scaling is enabled"
    )
    multi_az: bool = Field(default=False, description="Multi-AZ deployment")
    multi_region: bool = Field(default=False, description="Multi-region deployment")
    built_at: datetime = Field(
        default_factory=datetime.utcnow, description="Build timestamp"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "application_id": "app-payment-service",
                "availability_zones": ["us-east-1a", "us-east-1b"],
                "regions": ["us-east-1"],
                "providers": ["aws"],
                "total_instances": 6,
                "auto_scaling_enabled": True,
                "multi_az": True,
                "multi_region": False,
            }
        }

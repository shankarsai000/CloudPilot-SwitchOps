"""
Application Intelligence Agent - Core Application Models

Defines the canonical application representation for CloudPilot AI.
Transforms raw cloud resources into business-aware application entities
with ownership, dependencies, topology, and business criticality.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ApplicationType(str, Enum):
    """Classification of application architecture type."""

    MICROSERVICE = "microservice"
    MONOLITH = "monolith"
    SERVERLESS = "serverless"
    STATIC_SITE = "static_site"
    DATA_PIPELINE = "data_pipeline"
    BATCH_JOB = "batch_job"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


class EnvironmentType(str, Enum):
    """Deployment environment classification."""

    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TESTING = "testing"
    SANDBOX = "sandbox"
    UNKNOWN = "unknown"


class ServiceTier(str, Enum):
    """Service tier classification for SLA and priority."""

    TIER_1 = "tier_1"  # Mission-critical, customer-facing
    TIER_2 = "tier_2"  # Important, internal-facing
    TIER_3 = "tier_3"  # Supporting services
    TIER_4 = "tier_4"  # Development, experimental
    UNKNOWN = "unknown"


class ServiceType(str, Enum):
    """Classification of service role in application architecture."""

    FRONTEND = "frontend"
    BACKEND = "backend"
    API_GATEWAY = "api_gateway"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    STORAGE = "storage"
    LOAD_BALANCER = "load_balancer"
    CDN = "cdn"
    MONITORING = "monitoring"
    LOGGING = "logging"
    AUTH = "auth"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class DependencyDirection(str, Enum):
    """Direction of dependency relationship."""

    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    BIDIRECTIONAL = "bidirectional"


class DependencyProtocol(str, Enum):
    """Communication protocol between services."""

    HTTP = "http"
    HTTPS = "https"
    GRPC = "grpc"
    TCP = "tcp"
    UDP = "udp"
    WEBSOCKET = "websocket"
    AMQP = "amqp"
    KAFKA = "kafka"
    REDIS = "redis"
    SQL = "sql"
    UNKNOWN = "unknown"


class DependencyCoupling(str, Enum):
    """Type of coupling between services."""

    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"
    DATA = "data"
    EVENT = "event"
    CONFIGURATION = "configuration"


class DeploymentStrategy(str, Enum):
    """Deployment strategy type."""

    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    RECREATE = "recreate"
    A_B_TESTING = "a_b_testing"
    UNKNOWN = "unknown"


class DeploymentStatus(str, Enum):
    """Deployment execution status."""

    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    IN_PROGRESS = "in_progress"
    CANCELLED = "cancelled"


class CriticalityLevel(str, Enum):
    """Business criticality level classification."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class ServiceNode(BaseModel):
    """Node in the service dependency graph."""

    service_id: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Human-readable service name")
    service_type: ServiceType = Field(
        default=ServiceType.UNKNOWN, description="Role in application architecture"
    )
    protocol: DependencyProtocol = Field(
        default=DependencyProtocol.UNKNOWN, description="Primary communication protocol"
    )
    port: Optional[int] = Field(None, description="Primary service port")
    resource_ids: list[str] = Field(
        default_factory=list, description="Bound M1 resource IDs"
    )
    health_status: str = Field(default="unknown", description="Current health status")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Service-specific metadata"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "service_id": "svc-payment-api",
                "name": "Payment API",
                "service_type": "backend",
                "protocol": "https",
                "port": 8443,
                "resource_ids": ["ec2-001", "ec2-002"],
                "health_status": "healthy",
            }
        }


class ServiceDependency(BaseModel):
    """Edge in the service dependency graph."""

    source_service_id: str = Field(..., description="Source service ID")
    target_service_id: str = Field(..., description="Target service ID")
    dependency_type: DependencyCoupling = Field(
        default=DependencyCoupling.SYNCHRONOUS, description="Coupling type"
    )
    protocol: DependencyProtocol = Field(
        default=DependencyProtocol.UNKNOWN, description="Communication protocol"
    )
    port: Optional[int] = Field(None, description="Target port")
    latency_ms: Optional[float] = Field(None, description="Average latency in ms")
    requests_per_second: Optional[float] = Field(None, description="Average RPS")
    error_rate: Optional[float] = Field(None, description="Error rate (0.0-1.0)")
    is_critical: bool = Field(
        default=False, description="Whether this is a critical dependency"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Edge metadata")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "source_service_id": "svc-api-gateway",
                "target_service_id": "svc-payment-api",
                "dependency_type": "synchronous",
                "protocol": "https",
                "port": 8443,
                "latency_ms": 12.5,
                "requests_per_second": 450.0,
                "is_critical": True,
            }
        }


class OwnershipInfo(BaseModel):
    """Ownership and contact information for an application."""

    owner: Optional[str] = Field(None, description="Primary owner (individual)")
    team: Optional[str] = Field(None, description="Owning team name")
    team_id: Optional[str] = Field(None, description="Team identifier")
    slack_channel: Optional[str] = Field(None, description="Team Slack channel")
    email: Optional[str] = Field(None, description="Team email")
    repository: Optional[str] = Field(None, description="Source code repository URL")
    business_unit: Optional[str] = Field(None, description="Business unit")
    cost_center: Optional[str] = Field(None, description="Cost center code")
    environment: EnvironmentType = Field(
        default=EnvironmentType.UNKNOWN, description="Deployment environment"
    )
    pagerduty_service: Optional[str] = Field(None, description="PagerDuty service ID")
    documentation_url: Optional[str] = Field(None, description="Documentation URL")
    runbook_url: Optional[str] = Field(None, description="Runbook URL")
    on_call_schedule: Optional[str] = Field(None, description="On-call schedule ID")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Confidence score for ownership resolution"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "owner": "jane.doe",
                "team": "Payments",
                "team_id": "team-payments",
                "slack_channel": "#payments-eng",
                "repository": "https://github.com/org/payment-service",
                "business_unit": "Commerce",
                "pagerduty_service": "PD-PAY-001",
                "confidence": 0.95,
            }
        }


class DeploymentRecord(BaseModel):
    """Record of a deployment event."""

    deployment_id: str = Field(..., description="Unique deployment identifier")
    application_id: str = Field(..., description="Application this deployment belongs to")
    version: str = Field(..., description="Deployed version (semver or commit SHA)")
    previous_version: Optional[str] = Field(None, description="Previous version")
    strategy: DeploymentStrategy = Field(
        default=DeploymentStrategy.UNKNOWN, description="Deployment strategy"
    )
    status: DeploymentStatus = Field(
        default=DeploymentStatus.SUCCESS, description="Deployment status"
    )
    deployed_at: datetime = Field(
        default_factory=datetime.utcnow, description="Deployment timestamp"
    )
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    duration_seconds: Optional[int] = Field(None, description="Deployment duration")
    deployed_by: Optional[str] = Field(None, description="Deployer identity")
    commit_sha: Optional[str] = Field(None, description="Git commit SHA")
    is_rollback: bool = Field(default=False, description="Whether this was a rollback")
    change_summary: Optional[str] = Field(None, description="Summary of changes")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "deployment_id": "deploy-20240120-001",
                "application_id": "app-payment-service",
                "version": "2.3.1",
                "previous_version": "2.3.0",
                "strategy": "canary",
                "status": "success",
                "duration_seconds": 180,
                "deployed_by": "ci-pipeline",
                "is_rollback": False,
            }
        }


class TrafficFlow(BaseModel):
    """Traffic flow between services or external endpoints."""

    flow_id: str = Field(..., description="Unique flow identifier")
    source: str = Field(..., description="Source service or endpoint")
    destination: str = Field(..., description="Destination service or endpoint")
    protocol: DependencyProtocol = Field(
        default=DependencyProtocol.HTTPS, description="Traffic protocol"
    )
    port: Optional[int] = Field(None, description="Destination port")
    requests_per_second: float = Field(default=0.0, ge=0.0, description="Average RPS")
    latency_p50_ms: Optional[float] = Field(None, description="p50 latency in ms")
    latency_p99_ms: Optional[float] = Field(None, description="p99 latency in ms")
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Error rate")
    bandwidth_mbps: Optional[float] = Field(None, description="Bandwidth in Mbps")
    is_external: bool = Field(default=False, description="External traffic flow")
    direction: str = Field(default="internal", description="ingress, egress, or internal")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Flow metadata")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "flow_id": "flow-001",
                "source": "api-gateway",
                "destination": "payment-api",
                "protocol": "https",
                "port": 8443,
                "requests_per_second": 450.0,
                "latency_p50_ms": 12.5,
                "latency_p99_ms": 85.0,
                "error_rate": 0.002,
            }
        }


class BusinessCriticality(BaseModel):
    """Business criticality assessment for an application."""

    application_id: str = Field(..., description="Application identifier")
    revenue_impact: float = Field(
        default=0.0, ge=0.0, le=10.0,
        description="Revenue impact score (0-10)"
    )
    compliance_impact: float = Field(
        default=0.0, ge=0.0, le=10.0,
        description="Compliance impact score (0-10)"
    )
    availability_target: float = Field(
        default=99.0, ge=0.0, le=100.0,
        description="Availability SLA target (%)"
    )
    recovery_time_objective_minutes: int = Field(
        default=60, ge=0,
        description="RTO in minutes"
    )
    recovery_point_objective_minutes: int = Field(
        default=15, ge=0,
        description="RPO in minutes"
    )
    risk_level: CriticalityLevel = Field(
        default=CriticalityLevel.MEDIUM, description="Overall risk level"
    )
    criticality_score: float = Field(
        default=0.0, ge=0.0, le=100.0,
        description="Composite criticality score (0-100)"
    )
    compliance_frameworks: list[str] = Field(
        default_factory=list, description="Applicable compliance frameworks"
    )
    customer_facing: bool = Field(
        default=False, description="Whether application is customer-facing"
    )
    data_classification: str = Field(
        default="internal", description="Data classification level"
    )
    calculated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Calculation timestamp"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "application_id": "app-payment-service",
                "revenue_impact": 9.5,
                "compliance_impact": 8.0,
                "availability_target": 99.99,
                "recovery_time_objective_minutes": 5,
                "recovery_point_objective_minutes": 1,
                "risk_level": "critical",
                "criticality_score": 92.5,
                "compliance_frameworks": ["PCI-DSS", "SOC2"],
                "customer_facing": True,
                "data_classification": "confidential",
            }
        }


class Application(BaseModel):
    """Primary application entity — the core M3 model.

    Groups infrastructure resources into a business-aware application
    with ownership, dependencies, topology, and criticality metadata.
    """

    application_id: str = Field(..., description="Unique application identifier")
    name: str = Field(..., description="Human-readable application name")
    description: Optional[str] = Field(None, description="Application description")
    application_type: ApplicationType = Field(
        default=ApplicationType.UNKNOWN, description="Architecture type"
    )
    environment: EnvironmentType = Field(
        default=EnvironmentType.UNKNOWN, description="Deployment environment"
    )
    tier: ServiceTier = Field(
        default=ServiceTier.UNKNOWN, description="Service tier"
    )
    resource_ids: list[str] = Field(
        default_factory=list, description="Bound M1 resource IDs"
    )
    services: list[ServiceNode] = Field(
        default_factory=list, description="Services within this application"
    )
    dependencies: list[ServiceDependency] = Field(
        default_factory=list, description="Service dependency edges"
    )
    ownership: Optional[OwnershipInfo] = Field(
        None, description="Ownership and contact information"
    )
    criticality: Optional[BusinessCriticality] = Field(
        None, description="Business criticality assessment"
    )
    traffic_flows: list[TrafficFlow] = Field(
        default_factory=list, description="Traffic flow records"
    )
    deployments: list[DeploymentRecord] = Field(
        default_factory=list, description="Recent deployment records"
    )
    tags: dict[str, str] = Field(
        default_factory=dict, description="Application-level tags"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    total_monthly_cost: Optional[float] = Field(
        None, description="Total monthly cost from M2 enrichment"
    )
    discovered_at: datetime = Field(
        default_factory=datetime.utcnow, description="Discovery timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )
    discovery_source: str = Field(
        default="unknown", description="How this application was discovered"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "application_id": "app-payment-service",
                "name": "Payment Service",
                "description": "Handles payment processing and billing",
                "application_type": "microservice",
                "environment": "production",
                "tier": "tier_1",
                "resource_ids": ["ec2-001", "rds-023", "alb-12", "lambda-45"],
                "discovery_source": "tag_based",
                "total_monthly_cost": 1250.00,
            }
        }


class ApplicationGraph(BaseModel):
    """Complete application graph returned by the Application Intelligence Agent."""

    applications: list[Application] = Field(
        default_factory=list, description="Discovered applications"
    )
    total_applications: int = Field(
        default=0, description="Total applications discovered"
    )
    total_services: int = Field(
        default=0, description="Total services across all applications"
    )
    total_dependencies: int = Field(
        default=0, description="Total dependency edges"
    )
    applications_by_type: dict[str, int] = Field(
        default_factory=dict, description="Application count by type"
    )
    applications_by_environment: dict[str, int] = Field(
        default_factory=dict, description="Application count by environment"
    )
    applications_by_tier: dict[str, int] = Field(
        default_factory=dict, description="Application count by tier"
    )
    unassigned_resources: list[str] = Field(
        default_factory=list,
        description="M1 resource IDs not assigned to any application"
    )
    discovery_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When discovery ran"
    )
    failures: list[str] = Field(
        default_factory=list, description="Errors encountered during discovery"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "total_applications": 12,
                "total_services": 48,
                "total_dependencies": 85,
                "applications_by_type": {"microservice": 8, "monolith": 2, "serverless": 2},
                "applications_by_environment": {"production": 12},
                "applications_by_tier": {"tier_1": 3, "tier_2": 5, "tier_3": 4},
                "unassigned_resources": [],
                "failures": [],
            }
        }

"""
Domain models for CloudPilot Digital Enterprise Simulator.
Covers all infrastructure, relational topology, applications, telemetry, incidents, and actions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CloudProvider(str, Enum):
    """Supported cloud infrastructure providers."""
    AWS = "AWS"
    AZURE = "Azure"
    GCP = "GCP"


class ComputeState(str, Enum):
    """Runtime status of compute instances."""
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    DEGRADED = "degraded"


class DatabaseState(str, Enum):
    """Database instance states."""
    AVAILABLE = "available"
    MODIFYING = "modifying"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    TERMINATED = "terminated"


class CriticalityLevel(str, Enum):
    """Application and resource business criticality tiers."""
    TIER_1_MISSION_CRITICAL = "tier_1_mission_critical"
    TIER_2_BUSINESS_IMPORTANT = "tier_2_business_important"
    TIER_3_INTERNAL_NON_PROD = "tier_3_internal_non_prod"


class SimulationScale(str, Enum):
    """Scalable scenario generation presets."""
    SMALL = "small"          # ~100+ resources
    MEDIUM = "medium"        # ~500+ resources
    LARGE = "large"          # ~1000+ resources
    ENTERPRISE = "enterprise" # ~2500+ resources


class ActionType(str, Enum):
    """Simulation optimization and change actions."""
    RIGHTSIZE = "RIGHTSIZE"
    TERMINATE = "TERMINATE"
    STOP = "STOP"
    START = "START"
    PURGE_STORAGE = "PURGE_STORAGE"
    APPLY_RESERVATION = "APPLY_RESERVATION"
    FAILOVER = "FAILOVER"


class IncidentSeverity(str, Enum):
    """Simulated operational incident severity levels."""
    SEV1_CRITICAL = "sev1_critical"
    SEV2_HIGH = "sev2_high"
    SEV3_MEDIUM = "sev3_medium"
    SEV4_LOW = "sev4_low"


# ══════════════════════════════════════════════════════════════════
# Cloud Account & Network Topology Models
# ══════════════════════════════════════════════════════════════════

class CloudAccount(BaseModel):
    """Simulated enterprise cloud account / subscription."""
    account_id: str
    name: str
    provider: CloudProvider
    environment: str = "production"
    billing_account_id: str
    currency: str = "USD"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: Dict[str, str] = Field(default_factory=dict)


class SimulatedVPC(BaseModel):
    """Virtual Private Cloud network container."""
    vpc_id: str
    account_id: str
    region: str
    name: str
    cidr_block: str
    is_default: bool = False
    enable_dns_hostnames: bool = True
    tags: Dict[str, str] = Field(default_factory=dict)


class SimulatedSubnet(BaseModel):
    """Subnet segment within a VPC."""
    subnet_id: str
    vpc_id: str
    region: str
    availability_zone: str
    cidr_block: str
    tier: str = Field(description="'public', 'private', or 'database'")
    available_ips: int = 250
    tags: Dict[str, str] = Field(default_factory=dict)


class SimulatedSecurityGroup(BaseModel):
    """Virtual firewall rules container."""
    sg_id: str
    vpc_id: str
    name: str
    description: str
    ingress_rules: List[Dict[str, Any]] = Field(default_factory=list)
    egress_rules: List[Dict[str, Any]] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# Compute & Kubernetes Models
# ══════════════════════════════════════════════════════════════════

class SimulatedCompute(BaseModel):
    """Simulated virtual machine instance (e.g. EC2 instance)."""
    instance_id: str
    name: str
    account_id: str
    region: str
    vpc_id: str
    subnet_id: str
    security_group_ids: List[str] = Field(default_factory=list)
    instance_type: str
    vcpu: int
    memory_gib: float
    state: ComputeState = ComputeState.RUNNING
    lifecycle: str = "on-demand"  # 'on-demand' or 'spot'
    monthly_cost_usd: float
    hourly_rate_usd: float
    private_ip: str
    public_ip: Optional[str] = None
    role_id: Optional[str] = None
    app_id: Optional[str] = None
    service_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: Dict[str, str] = Field(default_factory=dict)


class SimulatedK8sPod(BaseModel):
    """Simulated Kubernetes Pod running a service container."""
    pod_id: str
    name: str
    namespace: str
    service_id: str
    node_id: str
    status: str = "Running"
    cpu_request_cores: float = 0.5
    memory_request_gib: float = 1.0


class SimulatedK8sCluster(BaseModel):
    """Simulated managed Kubernetes cluster (EKS / AKS / GKE)."""
    cluster_id: str
    name: str
    account_id: str
    region: str
    vpc_id: str
    subnet_ids: List[str] = Field(default_factory=list)
    version: str = "1.29"
    node_ids: List[str] = Field(default_factory=list)
    namespaces: List[str] = Field(default_factory=list)
    monthly_cost_usd: float = 73.0  # Base control plane cost
    tags: Dict[str, str] = Field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# Database, Storage & Networking Models
# ══════════════════════════════════════════════════════════════════

class SimulatedDatabase(BaseModel):
    """Simulated Managed Database (RDS, Aurora, DynamoDB, Redis Elasticache)."""
    database_id: str
    name: str
    account_id: str
    region: str
    vpc_id: str
    subnet_ids: List[str] = Field(default_factory=list)
    engine: str = Field(description="'postgres', 'aurora-postgresql', 'mysql', 'redis', 'dynamodb'")
    instance_class: str
    allocated_storage_gib: int
    state: DatabaseState = DatabaseState.AVAILABLE
    multi_az: bool = True
    is_clustered: bool = False
    replica_count: int = 0
    endpoint: str
    port: int = 5432
    monthly_cost_usd: float
    app_id: Optional[str] = None
    service_id: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)


class SimulatedStorage(BaseModel):
    """Simulated Object Storage bucket (S3 / GCS / Azure Blob)."""
    storage_id: str
    name: str
    account_id: str
    region: str
    size_gib: float
    object_count: int
    storage_class: str = "STANDARD"
    is_encrypted: bool = True
    versioning_enabled: bool = True
    monthly_cost_usd: float
    tags: Dict[str, str] = Field(default_factory=dict)


class SimulatedLoadBalancer(BaseModel):
    """Simulated Application Load Balancer / Ingress."""
    load_balancer_id: str
    name: str
    account_id: str
    region: str
    vpc_id: str
    subnet_ids: List[str] = Field(default_factory=list)
    dns_name: str
    scheme: str = "internet-facing"  # or 'internal'
    target_compute_ids: List[str] = Field(default_factory=list)
    monthly_cost_usd: float = 25.0
    tags: Dict[str, str] = Field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# Application & Dependency Models
# ══════════════════════════════════════════════════════════════════

class SimulatedService(BaseModel):
    """Specific microservice component within an application."""
    service_id: str
    app_id: str
    name: str
    tier: str = Field(description="'web', 'api', 'worker', 'caching', 'data'")
    compute_ids: List[str] = Field(default_factory=list)
    database_ids: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list, description="IDs of other services it calls")
    port: int = 8080
    health_endpoint: str = "/health"


class SimulatedApplication(BaseModel):
    """Logical business application tying together services and infrastructure."""
    app_id: str
    name: str
    description: str
    criticality: CriticalityLevel = CriticalityLevel.TIER_2_BUSINESS_IMPORTANT
    owner_team: str
    tech_lead: str
    on_call_schedule: str = "24x7-escalation"
    sla_target_percent: float = 99.95
    services: List[SimulatedService] = Field(default_factory=list)
    monthly_cost_usd: float = 0.0
    tags: Dict[str, str] = Field(default_factory=dict)


class SimulatedDependencyEdge(BaseModel):
    """Directed relationship between infrastructure or application components."""
    edge_id: str
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    relationship: str  # 'routes_to', 'reads_from', 'writes_to', 'hosted_on', 'part_of_vpc'
    criticality: str = "high"


# ══════════════════════════════════════════════════════════════════
# Telemetry, Events & State Actions
# ══════════════════════════════════════════════════════════════════

class SimulatedTelemetryPoint(BaseModel):
    """Snapshot of operational performance metrics for a resource."""
    target_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cpu_percent: float
    memory_percent: float
    network_in_mbps: float
    network_out_mbps: float
    disk_iops: float = 100.0
    latency_ms: float = 25.0
    error_rate: float = 0.0001
    availability: float = 1.0


class SimulatedIncident(BaseModel):
    """Simulated operational outage, performance degradation, or anomaly."""
    incident_id: str
    title: str
    severity: IncidentSeverity
    affected_resource_ids: List[str]
    root_cause: str
    symptoms: List[str]
    time_started: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_resolved: bool = False


class SimulatedHistoricalEvent(BaseModel):
    """Auditable historical event in the simulation timeline."""
    event_id: str
    timestamp: datetime
    event_type: str  # 'deployment', 'scale_up', 'outage', 'optimization', 'override'
    actor: str
    description: str
    target_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SimulationAction(BaseModel):
    """Action executed against the simulated cloud environment."""
    action_id: str
    action_type: ActionType
    target_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    executed_by: str = "CloudPilot-Autonomous-Agent"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SimulationActionResult(BaseModel):
    """Result of an executed simulation action."""
    action_id: str
    success: bool
    action_type: ActionType
    target_id: str
    pre_state: Dict[str, Any]
    post_state: Dict[str, Any]
    cost_delta_usd: float
    triggered_incident: Optional[SimulatedIncident] = None
    message: str

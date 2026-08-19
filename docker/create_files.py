#!/usr/bin/env python3
"""
Script to create all CloudPilot AI Infrastructure Discovery Agent files.
This circumvents symlink path resolution issues.
"""

import os
from pathlib import Path

# Define all files to create with their content
FILES = {}

# File 1: src/models/resource.py
FILES["src/models/resource.py"] = '''"""
Unified cloud resource schema for CloudPilot AI.

Defines the canonical resource representation across AWS, Azure, GCP, and Kubernetes.
All cloud-specific resources normalize to CloudResource for storage and querying.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    """Enumeration of all supported cloud resource types."""

    # AWS resources
    EC2_INSTANCE = "ec2_instance"
    RDS_DATABASE = "rds_database"
    RDS_CLUSTER = "rds_cluster"
    LAMBDA_FUNCTION = "lambda_function"
    S3_BUCKET = "s3_bucket"
    VPC = "vpc"
    SECURITY_GROUP = "security_group"
    SUBNET = "subnet"
    ROUTE_TABLE = "route_table"
    NETWORK_ACL = "network_acl"
    ELASTIC_IP = "elastic_ip"
    NAT_GATEWAY = "nat_gateway"
    ECS_CLUSTER = "ecs_cluster"
    ECS_SERVICE = "ecs_service"
    ECS_TASK_DEFINITION = "ecs_task_definition"
    ALB = "alb"
    NLB = "nlb"
    ELB = "elb"
    DYNAMODB_TABLE = "dynamodb_table"
    SNS_TOPIC = "sns_topic"
    SQS_QUEUE = "sqs_queue"
    KINESIS_STREAM = "kinesis_stream"
    CLOUDFRONT_DISTRIBUTION = "cloudfront_distribution"
    IAM_ROLE = "iam_role"
    IAM_POLICY = "iam_policy"
    KMS_KEY = "kms_key"

    # Azure resources
    AZURE_VM = "azure_vm"
    AZURE_SQL_DATABASE = "azure_sql_database"
    AZURE_SQL_SERVER = "azure_sql_server"
    AZURE_COSMOS_DB = "azure_cosmos_db"
    AZURE_APP_SERVICE = "azure_app_service"
    AZURE_FUNCTION_APP = "azure_function_app"
    AZURE_VNET = "azure_vnet"
    AZURE_SUBNET = "azure_subnet"
    AZURE_NSG = "azure_nsg"
    AZURE_STORAGE_ACCOUNT = "azure_storage_account"
    AZURE_LOAD_BALANCER = "azure_load_balancer"
    AZURE_APPLICATION_GATEWAY = "azure_application_gateway"
    AZURE_MANAGED_IDENTITY = "azure_managed_identity"

    # GCP resources
    GCP_COMPUTE_INSTANCE = "gcp_compute_instance"
    GCP_COMPUTE_DISK = "gcp_compute_disk"
    GCP_COMPUTE_IMAGE = "gcp_compute_image"
    GCP_SQL_INSTANCE = "gcp_sql_instance"
    GCP_SQL_DATABASE = "gcp_sql_database"
    GCP_CLOUD_FUNCTION = "gcp_cloud_function"
    GCP_CLOUD_RUN_SERVICE = "gcp_cloud_run_service"
    GCP_STORAGE_BUCKET = "gcp_storage_bucket"
    GCP_VPC = "gcp_vpc"
    GCP_SUBNET = "gcp_subnet"
    GCP_FIREWALL_RULE = "gcp_firewall_rule"
    GCP_LOAD_BALANCER = "gcp_load_balancer"
    GCP_CLOUD_KMS_KEY = "gcp_cloud_kms_key"
    GCP_BIGQUERY_DATASET = "gcp_bigquery_dataset"
    GCP_PUBSUB_TOPIC = "gcp_pubsub_topic"

    # Kubernetes resources
    K8S_POD = "k8s_pod"
    K8S_DEPLOYMENT = "k8s_deployment"
    K8S_STATEFULSET = "k8s_statefulset"
    K8S_DAEMONSET = "k8s_daemonset"
    K8S_JOB = "k8s_job"
    K8S_CRONJOB = "k8s_cronjob"
    K8S_SERVICE = "k8s_service"
    K8S_INGRESS = "k8s_ingress"
    K8S_CONFIGMAP = "k8s_configmap"
    K8S_SECRET = "k8s_secret"
    K8S_PERSISTENTVOLUME = "k8s_persistentvolume"
    K8S_PERSISTENTVOLUMECLAIM = "k8s_persistentvolumeclaim"
    K8S_NAMESPACE = "k8s_namespace"
    K8S_STORAGECLASS = "k8s_storageclass"


class ResourceState(str, Enum):
    """State/status of a resource."""

    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    PENDING = "pending"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DELETING = "deleting"
    DELETED = "deleted"
    UNKNOWN = "unknown"


class DependencyType(str, Enum):
    """Type of relationship between resources."""

    ATTACHED = "attached"
    REFERENCES = "references"
    MANAGES = "manages"
    ROUTES_TO = "routes_to"
    CONTAINS = "contains"
    ASSOCIATED_WITH = "associated_with"
    DEPENDS_ON = "depends_on"


class CloudResource(BaseModel):
    """Canonical representation of a cloud resource."""

    id: str = Field(..., description="Unique resource identifier (UUID)")
    name: str = Field(..., description="Human-readable resource name")
    type: ResourceType = Field(..., description="Type of resource")
    provider: str = Field(..., description="Cloud provider: aws, azure, gcp, k8s")
    region: str | None = Field(
        None, description="Geographic region (empty for non-regional resources)"
    )
    state: ResourceState = Field(
        default=ResourceState.UNKNOWN, description="Current resource state"
    )
    owner: str | None = Field(None, description="Owner/team responsible for resource")
    cost_monthly: float | None = Field(
        None, description="Estimated monthly cost in USD"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Resource creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )
    discovered_at: datetime = Field(
        default_factory=datetime.utcnow, description="When discovery agent found it"
    )
    tags: dict[str, str] = Field(
        default_factory=dict, description="Provider-native tags"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata (arn, instance_type, etc.)",
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "prod-web-server",
                "type": "ec2_instance",
                "provider": "aws",
                "region": "us-east-1",
                "state": "running",
                "owner": "platform-team",
                "cost_monthly": 45.50,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-20T14:22:00Z",
                "discovered_at": "2024-01-20T15:00:00Z",
                "tags": {"env": "production", "team": "platform"},
                "metadata": {
                    "instance_id": "i-0123456789abcdef0",
                    "instance_type": "t3.large",
                    "ami_id": "ami-0123456789abcdef0",
                },
            }
        }


class DependencyEdge(BaseModel):
    """Edge in the resource dependency graph."""

    source_id: str = Field(..., description="Source resource UUID")
    target_id: str = Field(..., description="Target resource UUID")
    relationship_type: DependencyType = Field(
        default=DependencyType.DEPENDS_ON, description="Type of dependency"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Edge creation timestamp"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Relationship-specific metadata"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "source_id": "550e8400-e29b-41d4-a716-446655440000",
                "target_id": "6f47ac10-b91f-11ea-857f-068e0d1f1234",
                "relationship_type": "attached",
                "created_at": "2024-01-20T15:00:00Z",
                "metadata": {"attachment_type": "security_group", "port": 443},
            }
        }


class ResourceGraph(BaseModel):
    """Complete resource graph returned by discovery agent."""

    resources: list[CloudResource] = Field(
        default_factory=list, description="Discovered resources"
    )
    dependencies: list[DependencyEdge] = Field(
        default_factory=list, description="Resource dependency edges"
    )
    discovery_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When discovery ran"
    )
    total_resources: int = Field(
        default=0, description="Total resources discovered"
    )
    resources_by_type: dict[str, int] = Field(
        default_factory=dict, description="Resource count by type"
    )
    resources_by_provider: dict[str, int] = Field(
        default_factory=dict, description="Resource count by provider"
    )
    failures: list[str] = Field(
        default_factory=list, description="Errors encountered during discovery"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "resources": [],
                "dependencies": [],
                "discovery_timestamp": "2024-01-20T15:00:00Z",
                "total_resources": 0,
                "resources_by_type": {},
                "resources_by_provider": {},
                "failures": [],
            }
        }
'''

def main() -> None:
    """Create all project files."""
    for file_path, content in FILES.items():
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Created: {file_path}")

if __name__ == "__main__":
    main()

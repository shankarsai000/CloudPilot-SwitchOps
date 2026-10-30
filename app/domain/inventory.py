"""
CloudPilot SwitchOps — Normalized Infrastructure Inventory Domain Models

Defines typed, vendor-neutral contracts for discovered infrastructure resources
from Terraform HCL and Docker Compose configurations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator


class ResourceCategory(str, Enum):
    """Broad category for infrastructure resources."""
    COMPUTE = "COMPUTE"
    STORAGE = "STORAGE"
    DATABASE = "DATABASE"
    NETWORK = "NETWORK"
    SECURITY = "SECURITY"
    CONTAINER = "CONTAINER"
    OTHER = "OTHER"


class DiscoveredResource(BaseModel):
    """
    Normalized representation of a single discovered cloud or container resource.
    Distinguishes known explicit values from unknown/dynamic expressions.
    """
    resource_id: str = Field(default_factory=lambda: f"res-{uuid.uuid4().hex[:10]}")
    resource_type: str = Field(..., description="Canonical resource type e.g. aws_instance, compose_service")
    provider: str = Field(..., description="Infrastructure provider e.g. aws, docker, azure")
    name: str = Field(..., description="Resource declaration name e.g. web_server, redis_cache")
    category: ResourceCategory = Field(default=ResourceCategory.OTHER)
    source_file: str = Field(..., description="Path to declaring file relative to workspace root")
    source_location: Optional[str] = Field(None, description="Line number or block identifier")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="Full parsed configuration attributes")
    attributes_known: Dict[str, Any] = Field(default_factory=dict, description="Explicitly verified static values")
    attributes_unknown: List[str] = Field(default_factory=list, description="Attributes referencing dynamic expressions or vars")
    discovery_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0")

    @field_validator("discovery_timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


class InfrastructureInventory(BaseModel):
    """
    Consolidated collection of resources discovered across an infrastructure workspace.
    """
    inventory_id: str = Field(default_factory=lambda: f"inv-{uuid.uuid4().hex[:10]}")
    task_id: Optional[str] = None
    workspace_root: str
    resources: List[DiscoveredResource] = Field(default_factory=list)
    discovered_files: List[str] = Field(default_factory=list)
    discovery_duration_ms: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0")

    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    @property
    def total_resources(self) -> int:
        return len(self.resources)

    def get_resources_by_category(self, category: ResourceCategory) -> List[DiscoveredResource]:
        return [r for r in self.resources if r.category == category]

    def get_resources_by_provider(self, provider: str) -> List[DiscoveredResource]:
        return [r for r in self.resources if r.provider.lower() == provider.lower()]

"""
CloudPilot SwitchOps — Policy Configuration Models

Represents user-defined and organizational operational policies,
including budget ceilings and mandatory security/reliability bars.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


class PolicyConfiguration(BaseModel):
    """
    Operational boundaries and constraints applied during candidate evaluation.
    """
    monthly_budget_ceiling: Optional[str] = Field(
        default=None,
        description="Optional maximum monthly infrastructure spend in USD (Decimal string)",
    )
    disallow_public_database: bool = Field(
        default=True,
        description="Hard constraint: candidates must not expose database listeners to public internet",
    )
    disallow_privileged_containers: bool = Field(
        default=True,
        description="Hard constraint: candidates must not introduce or retain privileged container flags",
    )
    disallow_docker_socket: bool = Field(
        default=True,
        description="Hard constraint: candidates must not mount /var/run/docker.sock into application containers",
    )
    disallow_wildcard_ingress: bool = Field(
        default=True,
        description="Hard constraint: candidates must not retain 0.0.0.0/0 ingress to sensitive management ports",
    )
    mandatory_persistence_for_stateful: bool = Field(
        default=True,
        description="Hard constraint: stateful database workloads must not have persistent storage removed",
    )
    mandatory_encryption: bool = Field(
        default=True,
        description="Hard constraint: candidates must not disable storage encryption at rest",
    )
    require_healthchecks: bool = Field(
        default=False,
        description="Advisory policy: flag containers lacking healthcheck probes",
    )
    policy_version: str = Field(default="1.0")

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "disallow_public_databases" in data:
                data["disallow_public_database"] = data["disallow_public_databases"]
            if "require_storage_encryption" in data:
                data["mandatory_encryption"] = data["require_storage_encryption"]
            if "prevent_data_volume_deletion" in data:
                data["mandatory_persistence_for_stateful"] = data["prevent_data_volume_deletion"]
            if "max_monthly_budget" in data:
                data["monthly_budget_ceiling"] = str(data["max_monthly_budget"])
        return data

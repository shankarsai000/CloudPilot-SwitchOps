"""
Opportunity Detector Component

Rule Engine to analyze resources, costs, and applications to detect optimization opportunities:
- Idle compute, underutilized databases, oversized Kubernetes nodes, unused storage, duplicates.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from models_resource import CloudResource, ResourceType
from models_application import Application

logger = logging.getLogger(__name__)


from pydantic import BaseModel, Field


class OptimizationOpportunity(BaseModel):
    """Details of a detected optimization opportunity."""

    target_id: str
    name: str
    type: str
    description: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class OpportunityDetector:
    """Detects optimization opportunities using static and heuristic rule engines."""

    def __init__(self) -> None:
        """Initialize Opportunity Detector."""
        pass

    def detect_opportunities(
        self,
        resources: list[CloudResource],
        applications: list[Application],
        cost_anomalies: list[Any] = None
    ) -> list[OptimizationOpportunity]:
        """Scan resource graphs, application layers, and costs to detect opportunities.

        Args:
            resources: Discovered resources
            applications: Discovered applications
            cost_anomalies: M2 anomaly list

        Returns:
            List of detected OptimizationOpportunity structures
        """
        opportunities = []
        assigned_resource_ids = {rid for app in applications for rid in app.resource_ids}

        for res in resources:
            # 1. Idle compute check
            is_compute = res.type.value in ("ec2_instance", "azure_vm", "gcp_compute_instance", "k8s_pod")
            cpu = res.metadata.get("cpu_utilization", 100.0)
            if is_compute and (cpu < 5.0 or "idle" in res.tags.get("status", "").lower()):
                opportunities.append(
                    OptimizationOpportunity(
                        target_id=res.id,
                        name=res.name,
                        type="COMPUTE",
                        description=f"Compute instance '{res.name}' is idle (CPU utilization is {cpu}%).",
                        metrics={"cpu_utilization": cpu, "monthly_cost": res.cost_monthly or 0.0}
                    )
                )

            # 2. Underutilized databases
            is_db = res.type.value in ("rds_database", "rds_cluster", "azure_sql_database", "gcp_sql_instance")
            db_cpu = res.metadata.get("cpu_utilization", 100.0)
            connections = res.metadata.get("database_connections", 1)
            if is_db and (db_cpu < 10.0 or connections == 0):
                opportunities.append(
                    OptimizationOpportunity(
                        target_id=res.id,
                        name=res.name,
                        type="DATABASES",
                        description=f"Database '{res.name}' is underutilized (CPU: {db_cpu}%, Connections: {connections}).",
                        metrics={"cpu_utilization": db_cpu, "connections": connections, "monthly_cost": res.cost_monthly or 0.0}
                    )
                )

            # 3. Unused Storage
            is_storage = res.type.value in ("s3_bucket", "azure_storage_account", "gcp_storage_bucket")
            operations = res.metadata.get("storage_operations_count", 100)
            if is_storage and operations < 5:
                opportunities.append(
                    OptimizationOpportunity(
                        target_id=res.id,
                        name=res.name,
                        type="STORAGE",
                        description=f"Storage bucket/account '{res.name}' has low operations activity ({operations} actions).",
                        metrics={"operations_count": operations, "monthly_cost": res.cost_monthly or 0.0}
                    )
                )

            # 4. Duplicate / Zombie resources
            # Running cloud resource not mapped to any application boundary
            if res.id not in assigned_resource_ids and res.type.value in ("ec2_instance", "rds_database", "alb"):
                opportunities.append(
                    OptimizationOpportunity(
                        target_id=res.id,
                        name=res.name,
                        type="ARCHITECTURE",
                        description=f"Zombie/Orphan resource '{res.name}' exists outside of mapped application boundaries.",
                        metrics={"monthly_cost": res.cost_monthly or 0.0}
                    )
                )

            # 5. Inefficient Autoscaling
            is_k8s_or_asg = res.type.value in ("k8s_deployment", "k8s_statefulset")
            replicas = res.metadata.get("replicas", 1)
            if is_k8s_or_asg and replicas > 5 and res.metadata.get("autoscaling_enabled") is False:
                opportunities.append(
                    OptimizationOpportunity(
                        target_id=res.id,
                        name=res.name,
                        type="AUTOSCALING",
                        description=f"Kubernetes cluster deployment '{res.name}' has high static replicas ({replicas}) with autoscaling disabled.",
                        metrics={"replicas": replicas, "autoscaling_enabled": False}
                    )
                )

        logger.info("Opportunity detector found %d candidates", len(opportunities))
        return opportunities

"""
Base Scenario Builder and Relational Integrity Framework.
Guarantees determinism, strict referential integrity, and scalable generation.
"""

import random
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from simulator.ground_truth import GroundTruthEngine
from simulator.models import (
    CloudAccount,
    SimulatedApplication,
    SimulatedCompute,
    SimulatedDatabase,
    SimulatedDependencyEdge,
    SimulatedHistoricalEvent,
    SimulatedIncident,
    SimulatedK8sCluster,
    SimulatedLoadBalancer,
    SimulatedSecurityGroup,
    SimulatedService,
    SimulatedStorage,
    SimulatedSubnet,
    SimulatedTelemetryPoint,
    SimulatedVPC,
    SimulationScale,
)


class ScenarioContext(BaseModel):
    """Encapsulates the complete generated enterprise cloud topology and state."""
    profile_name: str
    scale: SimulationScale
    seed: int
    account: CloudAccount
    vpcs: List[SimulatedVPC] = Field(default_factory=list)
    subnets: List[SimulatedSubnet] = Field(default_factory=list)
    security_groups: List[SimulatedSecurityGroup] = Field(default_factory=list)
    compute: List[SimulatedCompute] = Field(default_factory=list)
    k8s_clusters: List[SimulatedK8sCluster] = Field(default_factory=list)
    databases: List[SimulatedDatabase] = Field(default_factory=list)
    storage: List[SimulatedStorage] = Field(default_factory=list)
    load_balancers: List[SimulatedLoadBalancer] = Field(default_factory=list)
    applications: List[SimulatedApplication] = Field(default_factory=list)
    dependencies: List[SimulatedDependencyEdge] = Field(default_factory=list)
    telemetry: Dict[str, List[SimulatedTelemetryPoint]] = Field(default_factory=dict)
    incidents: List[SimulatedIncident] = Field(default_factory=list)
    events: List[SimulatedHistoricalEvent] = Field(default_factory=list)
    ground_truth: GroundTruthEngine = Field(default_factory=GroundTruthEngine)

    class Config:
        arbitrary_types_allowed = True

    @property
    def total_resource_count(self) -> int:
        """Total count of cloud infrastructure assets."""
        return (
            len(self.vpcs)
            + len(self.subnets)
            + len(self.security_groups)
            + len(self.compute)
            + len(self.k8s_clusters)
            + len(self.databases)
            + len(self.storage)
            + len(self.load_balancers)
        )

    @property
    def total_monthly_cost_usd(self) -> float:
        """Total monthly cloud spend across all infrastructure."""
        compute_cost = sum(c.monthly_cost_usd for c in self.compute if c.state.value == "running")
        db_cost = sum(d.monthly_cost_usd for d in self.databases if d.state.value == "available")
        storage_cost = sum(s.monthly_cost_usd for s in self.storage)
        lb_cost = sum(lb.monthly_cost_usd for lb in self.load_balancers)
        k8s_cost = sum(k.monthly_cost_usd for k in self.k8s_clusters)
        return round(compute_cost + db_cost + storage_cost + lb_cost + k8s_cost, 2)


class BaseScenarioBuilder(ABC):
    """
    Abstract base builder for enterprise scenario generation.
    Enforces deterministic seeding and relational consistency checks.
    """

    def __init__(self, seed: int = 42, scale: SimulationScale = SimulationScale.SMALL) -> None:
        self.seed = seed
        self.scale = scale
        self.rng = random.Random(seed)

    def get_scale_multiplier(self) -> int:
        """Return numerical scaling factor based on simulation preset."""
        if self.scale == SimulationScale.ENTERPRISE:
            return 25
        if self.scale == SimulationScale.LARGE:
            return 10
        if self.scale == SimulationScale.MEDIUM:
            return 5
        return 1  # SMALL baseline ~100+ resources

    @abstractmethod
    def build(self) -> ScenarioContext:
        """Generate and assemble the complete enterprise scenario."""
        pass

    def validate_consistency(self, ctx: ScenarioContext) -> None:
        """
        Verify referential integrity across the entire generated environment.
        Ensures no orphaned references, missing subnets, or phantom dependencies.
        """
        vpc_ids = {v.vpc_id for v in ctx.vpcs}
        subnet_ids = {s.subnet_id for s in ctx.subnets}
        compute_ids = {c.instance_id for c in ctx.compute}
        db_ids = {d.database_id for d in ctx.databases}
        all_resource_ids = (
            vpc_ids
            | subnet_ids
            | compute_ids
            | db_ids
            | {sg.sg_id for sg in ctx.security_groups}
            | {s.storage_id for s in ctx.storage}
            | {lb.load_balancer_id for lb in ctx.load_balancers}
            | {k.cluster_id for k in ctx.k8s_clusters}
        )

        # 1. Verify Subnets belong to existing VPCs
        for subnet in ctx.subnets:
            assert subnet.vpc_id in vpc_ids, f"Subnet {subnet.subnet_id} references missing VPC {subnet.vpc_id}"

        # 2. Verify Compute instances belong to existing VPCs and Subnets
        for inst in ctx.compute:
            assert inst.vpc_id in vpc_ids, f"Instance {inst.instance_id} references missing VPC {inst.vpc_id}"
            assert inst.subnet_id in subnet_ids, f"Instance {inst.instance_id} references missing Subnet {inst.subnet_id}"

        # 3. Verify Databases belong to existing VPCs
        for db in ctx.databases:
            assert db.vpc_id in vpc_ids, f"Database {db.database_id} references missing VPC {db.vpc_id}"

        # 4. Verify Applications reference existing infrastructure
        for app in ctx.applications:
            for svc in app.services:
                for comp_id in svc.compute_ids:
                    assert comp_id in compute_ids, f"Service {svc.service_id} references missing Compute {comp_id}"
                for db_id in svc.database_ids:
                    assert db_id in db_ids, f"Service {svc.service_id} references missing Database {db_id}"

        # 5. Verify Dependency Edges connect existing entities
        for edge in ctx.dependencies:
            assert edge.source_id in all_resource_ids or any(edge.source_id == a.app_id for a in ctx.applications), (
                f"Dependency source {edge.source_id} does not exist"
            )
            assert edge.target_id in all_resource_ids or any(edge.target_id == a.app_id for a in ctx.applications), (
                f"Dependency target {edge.target_id} does not exist"
            )

"""
CloudPilot Provider Adapters for the Digital Enterprise Simulator.
Allows M1 (Discovery), M2 (Cost Intelligence), and M10 (Execution) to seamlessly
interface with simulated environments without requiring real cloud accounts.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces.adapters import (
    BaseBillingAdapter,
    BaseCloudAdapter,
    BaseExecutorAdapter,
    get_adapter_registry,
)
from models_cost import BillingLineItem, CostCategory, CostProvider
from models_resource import CloudResource, DependencyEdge, DependencyType, ResourceState, ResourceType
from simulator.engine import get_simulator
from simulator.models import ActionType, SimulationAction


class SimulatedCloudAdapter(BaseCloudAdapter):
    """
    Discovery Adapter that inspects the active simulated enterprise cloud.
    Emits CloudResource and DependencyEdge entities for M1 Infrastructure Discovery.
    """

    def __init__(self) -> None:
        self.simulator = get_simulator()

    def discover(self) -> Tuple[List[CloudResource], List[DependencyEdge]]:
        ctx = self.simulator.get_context()
        resources: List[CloudResource] = []
        edges: List[DependencyEdge] = []

        now = datetime.now(timezone.utc)

        # 1. Map Compute
        for c in ctx.compute:
            st = ResourceState.RUNNING if c.state.value == "running" else ResourceState.STOPPED
            r = CloudResource(
                id=c.instance_id,
                name=c.name,
                type=ResourceType.EC2_INSTANCE,
                provider=c.account_id.split("-")[1].lower() if "-" in c.account_id else "aws",
                region=c.region,
                state=st,
                owner=c.app_id or "Platform",
                cost_monthly=c.monthly_cost_usd,
                created_at=c.created_at,
                updated_at=now,
                discovered_at=now,
                tags=c.tags,
                metadata={
                    "instance_type": c.instance_type,
                    "vcpu": c.vcpu,
                    "memory_gib": c.memory_gib,
                    "private_ip": c.private_ip,
                    "vpc_id": c.vpc_id,
                    "subnet_id": c.subnet_id,
                },
            )
            resources.append(r)

        # 2. Map Databases
        for d in ctx.databases:
            st = ResourceState.RUNNING if d.state.value == "available" else ResourceState.STOPPED
            res_type = ResourceType.RDS_CLUSTER if ("cluster" in d.engine.lower() or "aurora" in d.engine.lower()) else ResourceType.RDS_DATABASE
            r = CloudResource(
                id=d.database_id,
                name=d.name,
                type=res_type,
                provider="aws",
                region=d.region,
                state=st,
                owner=d.app_id or "Database Team",
                cost_monthly=d.monthly_cost_usd,
                created_at=now,
                updated_at=now,
                discovered_at=now,
                tags=d.tags,
                metadata={
                    "engine": d.engine,
                    "instance_class": d.instance_class,
                    "allocated_storage_gib": d.allocated_storage_gib,
                    "endpoint": d.endpoint,
                    "vpc_id": d.vpc_id,
                },
            )
            resources.append(r)

        # 3. Map Storage
        for s in ctx.storage:
            r = CloudResource(
                id=s.storage_id,
                name=s.name,
                type=ResourceType.S3_BUCKET,
                provider="aws",
                region=s.region,
                state=ResourceState.RUNNING,
                owner="Platform Storage",
                cost_monthly=s.monthly_cost_usd,
                created_at=now,
                updated_at=now,
                discovered_at=now,
                tags=s.tags,
                metadata={
                    "size_gib": s.size_gib,
                    "object_count": s.object_count,
                },
            )
            resources.append(r)

        # 4. Map Load Balancers
        for lb in ctx.load_balancers:
            r = CloudResource(
                id=lb.load_balancer_id,
                name=lb.name,
                type=ResourceType.ALB,
                provider="aws",
                region=lb.region,
                state=ResourceState.RUNNING,
                owner="Network Team",
                cost_monthly=lb.monthly_cost_usd,
                created_at=now,
                updated_at=now,
                discovered_at=now,
                tags=lb.tags,
                metadata={
                    "dns_name": lb.dns_name,
                    "vpc_id": lb.vpc_id,
                    "target_compute_ids": lb.target_compute_ids,
                },
            )
            resources.append(r)

        # 5. Map Dependencies
        for dep in ctx.dependencies:
            edges.append(
                DependencyEdge(
                    source_id=dep.source_id,
                    target_id=dep.target_id,
                    relationship_type=DependencyType.DEPENDS_ON,
                    metadata={"relationship": dep.relationship, "criticality": dep.criticality},
                )
            )

        return resources, edges

    def health_check(self) -> bool:
        return self.simulator.active_context is not None


class SimulatedBillingAdapter(BaseBillingAdapter):
    """
    Billing Ingestion Adapter producing billing line items matching the simulation.
    Feeds M2 Cost Intelligence.
    """

    def __init__(self) -> None:
        self.simulator = get_simulator()

    def fetch_billing_data(self, start_date: datetime, end_date: datetime) -> List[BillingLineItem]:
        ctx = self.simulator.get_context()
        items: List[BillingLineItem] = []

        now = datetime.now(timezone.utc)
        for i, c in enumerate(ctx.compute):
            items.append(
                BillingLineItem(
                    line_item_id=f"bill-item-comp-{i:04d}",
                    provider=CostProvider.AWS,
                    account_id=ctx.account.account_id,
                    service="Amazon Elastic Compute Cloud",
                    resource_id=c.instance_id,
                    cost_category=CostCategory.COMPUTE,
                    usage_type=f"BoxUsage:{c.instance_type}",
                    usage_quantity=720.0,
                    usage_unit="Hrs",
                    cost_amount=round(c.monthly_cost_usd, 2),
                    billing_period_start=start_date,
                    billing_period_end=end_date,
                )
            )

        for j, d in enumerate(ctx.databases):
            items.append(
                BillingLineItem(
                    line_item_id=f"bill-item-db-{j:04d}",
                    provider=CostProvider.AWS,
                    account_id=ctx.account.account_id,
                    service="Amazon Relational Database Service" if d.engine != "redis" else "Amazon ElastiCache",
                    resource_id=d.database_id,
                    cost_category=CostCategory.DATABASE,
                    usage_type=f"InstanceUsage:{d.instance_class}",
                    usage_quantity=720.0,
                    usage_unit="Hrs",
                    cost_amount=round(d.monthly_cost_usd, 2),
                    billing_period_start=start_date,
                    billing_period_end=end_date,
                )
            )

        return items

    def health_check(self) -> bool:
        return self.simulator.active_context is not None


class SimulatedExecutorAdapter(BaseExecutorAdapter):
    """
    Autonomous Execution Adapter executing actions against the simulator.
    Feeds M10 Autonomous Execution Engine.
    """

    def __init__(self) -> None:
        self.simulator = get_simulator()

    def execute_action(self, target_id: str, action: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import uuid
        action_type = ActionType(action.upper()) if action.upper() in ActionType._value2member_map_ else ActionType.RIGHTSIZE
        sim_action = SimulationAction(
            action_id=f"act-{uuid.uuid4().hex[:8]}",
            action_type=action_type,
            target_id=target_id,
            parameters=parameters or {},
        )
        res = self.simulator.execute_action(sim_action)
        return res.model_dump()

    def rollback_action(self, execution_id: str) -> bool:
        return self.simulator.rollback_action(execution_id)

    def health_check(self) -> bool:
        return self.simulator.active_context is not None


# Register with platform ProviderAdapterRegistry
registry = get_adapter_registry()
registry.register_cloud_adapter("simulated", SimulatedCloudAdapter)
registry.register_billing_adapter("simulated", SimulatedBillingAdapter)
registry.register_executor_adapter("simulated", SimulatedExecutorAdapter)

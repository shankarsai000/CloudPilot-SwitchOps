"""
REST API endpoints for the Digital Enterprise Simulator.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from simulator.engine import get_simulator
from simulator.ground_truth import AccuracyMetrics, EvaluationScore
from simulator.models import ActionType, SimulationAction, SimulationScale

simulator_router = APIRouter(prefix="/simulator", tags=["Digital Enterprise Simulator"])


class GenerateScenarioRequest(BaseModel):
    """Payload to trigger deterministic scenario generation."""
    profile: str = Field(default="SaaS", description="Scenario profile (SaaS, Banking, E-commerce, AI Research, Startup, Healthcare, Gaming)")
    scale: SimulationScale = Field(default=SimulationScale.SMALL, description="Scale preset: small (~100), medium (~500), large (~1000), enterprise (~2500)")
    seed: int = Field(default=42, description="Deterministic seed")


class ExecuteActionRequest(BaseModel):
    """Payload to execute an action in the simulated environment."""
    action_type: ActionType
    target_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class RollbackActionRequest(BaseModel):
    """Payload to rollback an action."""
    action_id: str


class ScoreDecisionsRequest(BaseModel):
    """Payload containing CloudPilot decisions to evaluate against ground truth."""
    decisions: List[Dict[str, Any]]


# ══════════════════════════════════════════════════════════════════
# Scenario & Topology Endpoints
# ══════════════════════════════════════════════════════════════════

@simulator_router.get("/scenarios")
async def list_available_scenarios() -> List[Dict[str, Any]]:
    """List all supported enterprise scenario profiles and scale presets."""
    return [
        {
            "id": "SaaS",
            "name": "B2B SaaS Multi-Tenant Platform",
            "description": "Multi-tier microservices, Aurora primary & replicas, Redis caching cluster, auto-scaling worker nodes, S3 customer assets.",
            "available_scales": ["small (~100)", "medium (~500)", "large (~1000)", "enterprise (~2500)"],
        },
        {
            "id": "Banking",
            "name": "Tier-1 Core Banking Ledger",
            "description": "Strict PCI-DSS compliance, encrypted multi-AZ primary ledger, zero-downtime requirements, strict change freezes.",
            "available_scales": ["small (~100)", "medium (~500)", "large (~1000)", "enterprise (~2500)"],
        },
        {
            "id": "E-commerce",
            "name": "Global Retail Storefront",
            "description": "Storefront CDN, checkout cart microservices, Redis session caching, product catalog Aurora clusters.",
            "available_scales": ["small (~100)", "medium (~500)", "large (~1000)", "enterprise (~2500)"],
        },
        {
            "id": "AI Research",
            "name": "Foundation Model AI Lab",
            "description": "High-throughput GPU training clusters (p4d.24xlarge), distributed model checkpointing, massive training datasets.",
            "available_scales": ["small (~100)", "medium (~500)", "large (~1000)", "enterprise (~2500)"],
        },
        {
            "id": "Startup",
            "name": "High-Growth Lean Startup",
            "description": "Single-region fast deployment, PostgreSQL backend, lightweight Redis, high right-sizing opportunities.",
            "available_scales": ["small (~100)", "medium (~500)", "large (~1000)", "enterprise (~2500)"],
        },
        {
            "id": "Healthcare",
            "name": "Clinical Healthcare & EHR",
            "description": "HIPAA audit pipeline, mission-critical Electronic Health Records database, telehealth WebRTC gateways.",
            "available_scales": ["small (~100)", "medium (~500)", "large (~1000)", "enterprise (~2500)"],
        },
        {
            "id": "Gaming",
            "name": "Multiplayer Game Studio Fleet",
            "description": "Low-latency UDP game server fleets, Redis leaderboards, matchmaking clusters, global player traffic.",
            "available_scales": ["small (~100)", "medium (~500)", "large (~1000)", "enterprise (~2500)"],
        },
    ]


@simulator_router.post("/scenarios/generate")
async def generate_scenario(req: GenerateScenarioRequest) -> Dict[str, Any]:
    """Deterministically generate and activate an enterprise scenario."""
    sim = get_simulator()
    ctx = sim.generate(profile=req.profile, scale=req.scale, seed=req.seed)
    return {
        "status": "generated",
        "profile": ctx.profile_name,
        "scale": ctx.scale.value,
        "seed": ctx.seed,
        "resource_count": ctx.total_resource_count,
        "monthly_spend_usd": ctx.total_monthly_cost_usd,
        "applications_count": len(ctx.applications),
        "incidents_count": len(ctx.incidents),
    }


@simulator_router.get("/state")
async def get_simulation_state() -> Dict[str, Any]:
    """Retrieve current simulation state and overall topology counters."""
    sim = get_simulator()
    ctx = sim.get_context()
    return {
        "profile": ctx.profile_name,
        "scale": ctx.scale.value,
        "seed": ctx.seed,
        "account_id": ctx.account.account_id,
        "provider": ctx.account.provider.value,
        "total_resources": ctx.total_resource_count,
        "monthly_spend_usd": ctx.total_monthly_cost_usd,
        "compute_count": len(ctx.compute),
        "database_count": len(ctx.databases),
        "storage_count": len(ctx.storage),
        "applications_count": len(ctx.applications),
        "active_incidents_count": len([i for i in ctx.incidents if not i.is_resolved]),
    }


@simulator_router.get("/resources")
async def list_simulated_resources(resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query simulated resources with optional type filter."""
    sim = get_simulator()
    ctx = sim.get_context()
    results = []

    if not resource_type or resource_type.lower() == "compute":
        for c in ctx.compute:
            results.append({"id": c.instance_id, "type": "compute", "name": c.name, "state": c.state.value, "cost": c.monthly_cost_usd, "details": c.model_dump()})

    if not resource_type or resource_type.lower() == "database":
        for d in ctx.databases:
            results.append({"id": d.database_id, "type": "database", "name": d.name, "state": d.state.value, "cost": d.monthly_cost_usd, "details": d.model_dump()})

    if not resource_type or resource_type.lower() == "storage":
        for s in ctx.storage:
            results.append({"id": s.storage_id, "type": "storage", "name": s.name, "cost": s.monthly_cost_usd, "details": s.model_dump()})

    return results


@simulator_router.get("/resources/{resource_id}")
async def get_resource_details(resource_id: str) -> Dict[str, Any]:
    """Retrieve specific resource details and direct dependency relationships."""
    sim = get_simulator()
    ctx = sim.get_context()

    compute = next((c for c in ctx.compute if c.instance_id == resource_id), None)
    db = next((d for d in ctx.databases if d.database_id == resource_id), None)
    storage = next((s for s in ctx.storage if s.storage_id == resource_id), None)

    if not compute and not db and not storage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Resource '{resource_id}' not found")

    item = compute or db or storage
    dependencies = [e.model_dump() for e in ctx.dependencies if e.source_id == resource_id or e.target_id == resource_id]

    return {
        "resource_id": resource_id,
        "details": item.model_dump(),
        "direct_dependencies": dependencies,
    }


@simulator_router.get("/topology")
async def get_simulation_topology() -> Dict[str, Any]:
    """Retrieve the full dependency graph and relational topology."""
    sim = get_simulator()
    ctx = sim.get_context()

    nodes = []
    for c in ctx.compute:
        nodes.append({"id": c.instance_id, "label": c.name, "type": "compute", "tier": "compute", "status": c.state.value})
    for d in ctx.databases:
        nodes.append({"id": d.database_id, "label": d.name, "type": "database", "tier": "data", "status": d.state.value})
    for s in ctx.storage:
        nodes.append({"id": s.storage_id, "label": s.name, "type": "storage", "tier": "storage"})
    for lb in ctx.load_balancers:
        nodes.append({"id": lb.load_balancer_id, "label": lb.name, "type": "load_balancer", "tier": "network"})

    edges = [e.model_dump() for e in ctx.dependencies]

    return {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }


# ══════════════════════════════════════════════════════════════════
# Telemetry, Events & Actions
# ══════════════════════════════════════════════════════════════════

@simulator_router.get("/telemetry/{target_id}")
async def get_resource_telemetry(target_id: str) -> Dict[str, Any]:
    """Fetch live operational telemetry metrics respecting resource state."""
    sim = get_simulator()
    return sim.get_live_telemetry(target_id)


@simulator_router.get("/events")
async def get_simulation_events() -> Dict[str, Any]:
    """Retrieve simulated incidents and historical deployments."""
    sim = get_simulator()
    ctx = sim.get_context()
    return {
        "incidents": [i.model_dump() for i in ctx.incidents],
        "events": [e.model_dump() for e in ctx.events],
    }


@simulator_router.post("/actions/execute")
async def execute_action_endpoint(req: ExecuteActionRequest) -> Dict[str, Any]:
    """Execute change or optimization action in the simulated environment."""
    import uuid
    sim = get_simulator()
    action = SimulationAction(
        action_id=f"act-{uuid.uuid4().hex[:8]}",
        action_type=req.action_type,
        target_id=req.target_id,
        parameters=req.parameters,
    )
    res = sim.execute_action(action)
    return res.model_dump()


@simulator_router.post("/actions/rollback")
async def rollback_action_endpoint(req: RollbackActionRequest) -> Dict[str, Any]:
    """Rollback an executed simulation action."""
    sim = get_simulator()
    success = sim.rollback_action(req.action_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No rollback snapshot found for action '{req.action_id}'")
    return {"status": "rolled_back", "action_id": req.action_id}


@simulator_router.post("/reset")
async def reset_simulation_endpoint() -> Dict[str, Any]:
    """Reset the simulated cloud to the initial generated state."""
    sim = get_simulator()
    ctx = sim.reset()
    return {
        "status": "reset_complete",
        "profile": ctx.profile_name,
        "resource_count": ctx.total_resource_count,
        "monthly_spend_usd": ctx.total_monthly_cost_usd,
    }


# ══════════════════════════════════════════════════════════════════
# Ground Truth & Evaluation (Strictly isolated for evaluation)
# ══════════════════════════════════════════════════════════════════

@simulator_router.get("/evaluation/ground-truth")
async def get_ground_truth_oracle() -> Dict[str, Any]:
    """
    Retrieve ground truth safe/unsafe action matrix.
    EVALUATION ONLY: Decision agents must not call this endpoint during reasoning.
    """
    sim = get_simulator()
    ctx = sim.get_context()
    gt = ctx.ground_truth
    actions = [a.model_dump() for a in gt.get_all_ground_truth_actions()]
    strategy = gt.get_optimal_strategy()
    return {
        "scenario": ctx.profile_name,
        "total_rules": len(actions),
        "ground_truth_actions": actions,
        "optimal_strategy": strategy.model_dump() if strategy else None,
    }


@simulator_router.post("/evaluation/score-decisions")
async def score_decisions_endpoint(req: ScoreDecisionsRequest) -> AccuracyMetrics:
    """Benchmark CloudPilot decisions against Ground Truth and compute accuracy scores."""
    sim = get_simulator()
    ctx = sim.get_context()
    metrics = ctx.ground_truth.calculate_benchmark_metrics(req.decisions)
    return metrics

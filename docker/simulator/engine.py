"""
Stateful Digital Enterprise Simulation Engine.
Manages active simulated cloud environments, state transitions, snapshots,
incident injection, rollbacks, and telemetry generation.
"""

import copy
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from simulator.ground_truth import GroundTruthEngine
from simulator.models import (
    ActionType,
    ComputeState,
    DatabaseState,
    IncidentSeverity,
    SimulatedCompute,
    SimulatedDatabase,
    SimulatedIncident,
    SimulatedTelemetryPoint,
    SimulationAction,
    SimulationActionResult,
    SimulationScale,
)
from simulator.scenarios.base import ScenarioContext
from simulator.scenarios.profiles import get_scenario_builder

logger = logging.getLogger("cloudpilot.simulator")


class EnterpriseSimulator:
    """
    Stateful digital enterprise cloud simulator.
    Executes actions, maintains snapshots, triggers incidents upon unsafe operations,
    and exposes realistic telemetry streams.
    """

    def __init__(self) -> None:
        self.active_context: Optional[ScenarioContext] = None
        self._initial_context: Optional[ScenarioContext] = None
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._action_history: List[SimulationActionResult] = []

    def generate(
        self,
        profile: str = "SaaS",
        scale: SimulationScale | str = SimulationScale.SMALL,
        seed: int = 42,
    ) -> ScenarioContext:
        """
        Deterministically generate and activate an enterprise scenario profile.
        """
        if isinstance(scale, str):
            try:
                scale = SimulationScale(scale.lower())
            except ValueError:
                scale = SimulationScale.SMALL
        logger.info("Generating enterprise scenario: profile=%s, scale=%s, seed=%d", profile, scale.value, seed)
        builder = get_scenario_builder(profile_name=profile, seed=seed, scale=scale)
        ctx = builder.build()

        self.active_context = ctx
        # Store a deep copy as baseline for resets
        self._initial_context = copy.deepcopy(ctx)
        self._snapshots.clear()
        self._action_history.clear()

        logger.info(
            "Scenario generated successfully: %d resources, $%.2f/mo spend",
            ctx.total_resource_count,
            ctx.total_monthly_cost_usd,
        )
        return ctx

    def get_context(self) -> ScenarioContext:
        """Return the active simulation context or generate default SaaS scenario."""
        if self.active_context is None:
            return self.generate(profile="SaaS", scale=SimulationScale.SMALL, seed=42)
        return self.active_context

    def execute_action(self, action: SimulationAction) -> SimulationActionResult:
        """
        Execute an optimization or change action against the simulated cloud.
        Applies state transitions, checks ground truth safety, and triggers incidents if unsafe.
        """
        ctx = self.get_context()
        target_id = action.target_id
        action_type = action.action_type

        # 1. Find target resource
        compute_target = next((c for c in ctx.compute if c.instance_id == target_id), None)
        db_target = next((d for d in ctx.databases if d.database_id == target_id), None)

        if not compute_target and not db_target:
            return SimulationActionResult(
                action_id=action.action_id,
                success=False,
                action_type=action_type,
                target_id=target_id,
                pre_state={},
                post_state={},
                cost_delta_usd=0.0,
                message=f"Target resource '{target_id}' not found in simulation environment",
            )

        # 2. Capture pre-action state snapshot
        pre_state = (
            compute_target.model_dump() if compute_target else db_target.model_dump()
        )
        self._snapshots[action.action_id] = {
            "resource_type": "compute" if compute_target else "database",
            "state": copy.deepcopy(pre_state),
        }

        # 3. Check Ground Truth Safety Oracle
        gt = ctx.ground_truth.get_ground_truth(target_id, action_type)
        is_safe = gt.is_safe if gt else True
        triggered_incident: Optional[SimulatedIncident] = None

        # 4. Apply State Transitions
        cost_delta = 0.0
        post_state = {}

        if compute_target:
            old_cost = compute_target.monthly_cost_usd
            if action_type == ActionType.TERMINATE:
                compute_target.state = ComputeState.TERMINATED
                compute_target.monthly_cost_usd = 0.0
                cost_delta = old_cost
            elif action_type == ActionType.STOP:
                compute_target.state = ComputeState.STOPPED
                # EBS storage still incurs ~10% cost
                compute_target.monthly_cost_usd = round(old_cost * 0.1, 2)
                cost_delta = old_cost - compute_target.monthly_cost_usd
            elif action_type == ActionType.START:
                compute_target.state = ComputeState.RUNNING
                compute_target.monthly_cost_usd = action.parameters.get("monthly_cost_usd", old_cost)
                cost_delta = -(compute_target.monthly_cost_usd - old_cost)
            elif action_type == ActionType.RIGHTSIZE:
                new_type = action.parameters.get("new_instance_type", "m5.large")
                compute_target.instance_type = new_type
                compute_target.vcpu = action.parameters.get("vcpu", 2)
                compute_target.memory_gib = action.parameters.get("memory_gib", 8.0)
                savings = gt.expected_savings_monthly_usd if gt else (old_cost * 0.4)
                compute_target.monthly_cost_usd = max(20.0, round(old_cost - savings, 2))
                cost_delta = old_cost - compute_target.monthly_cost_usd
            elif action_type == ActionType.APPLY_RESERVATION:
                compute_target.lifecycle = "reserved_1yr"
                compute_target.monthly_cost_usd = round(old_cost * 0.65, 2)
                cost_delta = old_cost - compute_target.monthly_cost_usd

            post_state = compute_target.model_dump()

        elif db_target:
            old_cost = db_target.monthly_cost_usd
            if action_type == ActionType.TERMINATE:
                db_target.state = DatabaseState.TERMINATED
                db_target.monthly_cost_usd = 0.0
                cost_delta = old_cost
            elif action_type == ActionType.STOP:
                db_target.state = DatabaseState.STOPPED
                db_target.monthly_cost_usd = round(old_cost * 0.15, 2)
                cost_delta = old_cost - db_target.monthly_cost_usd
            elif action_type == ActionType.RIGHTSIZE:
                new_class = action.parameters.get("new_instance_class", "db.m5.large")
                db_target.instance_class = new_class
                savings = gt.expected_savings_monthly_usd if gt else (old_cost * 0.35)
                db_target.monthly_cost_usd = max(50.0, round(old_cost - savings, 2))
                cost_delta = old_cost - db_target.monthly_cost_usd

            post_state = db_target.model_dump()

        # 5. If action is UNSAFE according to ground truth, trigger an active incident!
        if not is_safe:
            incident_id = f"inc-{int(time.time())}"
            reason_text = gt.reason if gt else "Critical dependency impacted by optimization"
            triggered_incident = SimulatedIncident(
                incident_id=incident_id,
                title=f"CRITICAL OUTAGE: Unsafe {action_type.value} on {target_id}",
                severity=IncidentSeverity.SEV1_CRITICAL,
                affected_resource_ids=[target_id] + (gt.blast_radius_resource_ids if gt else []),
                root_cause=reason_text,
                symptoms=["Connection Refused", "Service Unavailable 503", "Elevated Latency"],
                is_resolved=False,
            )
            ctx.incidents.append(triggered_incident)
            logger.error("UNSAFE ACTION TRIGGERED SIMULATION INCIDENT [%s]: %s", incident_id, reason_text)

        msg = (
            f"Action {action_type.value} executed successfully on {target_id}. Monthly savings: ${cost_delta:.2f}."
            if is_safe
            else f"CRITICAL WARNING: Unsafe action {action_type.value} executed on {target_id}! Outage incident triggered."
        )

        result = SimulationActionResult(
            action_id=action.action_id,
            success=True,
            action_type=action_type,
            target_id=target_id,
            pre_state=pre_state,
            post_state=post_state,
            cost_delta_usd=round(cost_delta, 2),
            triggered_incident=triggered_incident,
            message=msg,
        )
        self._action_history.append(result)
        return result

    def rollback_action(self, action_id: str) -> bool:
        """
        Restore pre-action state snapshot and resolve associated incidents.
        """
        snapshot_data = self._snapshots.get(action_id)
        if not snapshot_data:
            logger.warning("No rollback snapshot found for action: %s", action_id)
            return False

        ctx = self.get_context()
        res_type = snapshot_data["resource_type"]
        state = snapshot_data["state"]
        target_id = state.get("instance_id") or state.get("database_id")

        if res_type == "compute":
            inst = next((c for c in ctx.compute if c.instance_id == target_id), None)
            if inst:
                inst.state = ComputeState(state["state"])
                inst.instance_type = state["instance_type"]
                inst.vcpu = state["vcpu"]
                inst.memory_gib = state["memory_gib"]
                inst.monthly_cost_usd = state["monthly_cost_usd"]
                inst.lifecycle = state["lifecycle"]
        elif res_type == "database":
            db = next((d for d in ctx.databases if d.database_id == target_id), None)
            if db:
                db.state = DatabaseState(state["state"])
                db.instance_class = state["instance_class"]
                db.monthly_cost_usd = state["monthly_cost_usd"]

        # Resolve any incidents associated with this target
        for inc in ctx.incidents:
            if target_id in inc.affected_resource_ids and not inc.is_resolved:
                inc.is_resolved = True
                logger.info("Rollback resolved incident [%s]", inc.incident_id)

        del self._snapshots[action_id]
        logger.info("Successfully rolled back action %s on %s", action_id, target_id)
        return True

    def reset(self) -> ScenarioContext:
        """Reset the simulated cloud to the initial generated baseline."""
        if self._initial_context:
            self.active_context = copy.deepcopy(self._initial_context)
            self._snapshots.clear()
            self._action_history.clear()
            logger.info("Reset simulator to initial baseline: %s", self.active_context.profile_name)
            return self.active_context
        return self.generate(profile="SaaS", scale=SimulationScale.SMALL, seed=42)

    def get_live_telemetry(self, target_id: str) -> Dict[str, Any]:
        """
        Generate dynamic live metrics for target respecting its current state.
        """
        ctx = self.get_context()
        compute = next((c for c in ctx.compute if c.instance_id == target_id), None)
        db = next((d for d in ctx.databases if d.database_id == target_id), None)

        state_str = compute.state.value if compute else (db.state.value if db else "unknown")

        # Check if target is in an active incident (outages take priority in telemetry)
        has_incident = any(
            target_id in inc.affected_resource_ids and not inc.is_resolved for inc in ctx.incidents
        )

        now = datetime.now(timezone.utc)
        sec = now.second
        if has_incident:
            return {
                "target_id": target_id,
                "timestamp": now.isoformat(),
                "cpu_percent": 98.5,
                "memory_percent": 96.0,
                "network_in_mbps": 5.0,
                "network_out_mbps": 1.0,
                "error_rate": 0.85,
                "latency_ms": 850.0,
                "availability": 0.1,
                "status": "degraded_incident",
            }

        if state_str in ("stopped", "terminated"):
            return {
                "target_id": target_id,
                "timestamp": now.isoformat(),
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "network_in_mbps": 0.0,
                "network_out_mbps": 0.0,
                "error_rate": 0.0,
                "latency_ms": 0.0,
                "availability": 0.0,
                "status": state_str,
            }

        # Normal operational variation
        base_cpu = 25.0 + (hash(target_id) % 35)
        sin_factor = (sec % 10) * 1.5
        cpu = min(95.0, max(5.0, base_cpu + sin_factor))
        mem = min(90.0, max(20.0, base_cpu * 1.2))

        return {
            "target_id": target_id,
            "timestamp": now.isoformat(),
            "cpu_percent": round(cpu, 1),
            "memory_percent": round(mem, 1),
            "network_in_mbps": round(30.0 + (sec * 2.0), 1),
            "network_out_mbps": round(50.0 + (sec * 4.0), 1),
            "error_rate": 0.0001,
            "latency_ms": round(25.0 + (sec * 0.5), 1),
            "availability": 1.0,
            "status": "healthy",
        }


_simulator = EnterpriseSimulator()


def get_simulator() -> EnterpriseSimulator:
    """Return the singleton instance of EnterpriseSimulator."""
    return _simulator

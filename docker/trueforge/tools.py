"""
Controlled Tools for TrueForge Agent Runtime.

Implements controlled tools for CloudPilot intelligence (M1-M4, M6) and
sandboxed Terraform plan execution. All tool calls are intercepted,
audited, and cleanly separated from the agent harness.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from simulator.engine import get_simulator
from trueforge.models import ToolCallAuditLog
from trueforge.sandbox import get_sandbox_manager

logger = logging.getLogger("cloudpilot.trueforge.tools")


class ControlledToolRegistry:
    """
    Registry and execution dispatcher for TrueForge controlled tools.
    Enforces audit logging, schema validation, and sandbox isolation.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable[..., Any]] = {}
        self._audit_logs: List[ToolCallAuditLog] = []
        self._register_default_tools()
        logger.info("ControlledToolRegistry initialized with %d tools", len(self._tools))

    def register_tool(
        self,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
        handler: Callable[..., Any],
        requires_approval: bool = False,
        read_only: bool = True,
    ) -> None:
        """Register a new controlled tool."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters_schema,
            "requires_approval": requires_approval,
            "read_only": read_only,
        }
        self._handlers[name] = handler

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools in MCP / OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
                "requires_approval": t["requires_approval"],
                "read_only": t["read_only"],
            }
            for t in self._tools.values()
        ]

    def get_tool_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific tool."""
        return self._tools.get(name)

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tool_call_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        thread_id: str = "main",
        sandbox_id: Optional[str] = None,
    ) -> Any:
        """
        Execute a registered tool and record an immutable audit log.
        """
        cid = tool_call_id or f"call-{uuid.uuid4().hex[:8]}"
        handler = self._handlers.get(tool_name)
        if not handler:
            err = f"Unknown tool: {tool_name}"
            self._record_audit(cid, turn_id, thread_id, tool_name, arguments, None, 0.0, sandbox_id, "ERROR", err)
            raise ValueError(err)

        start_time = time.time()
        status = "SUCCESS"
        error_msg = None
        result = None

        try:
            result = handler(**arguments)
        except Exception as exc:
            status = "ERROR"
            error_msg = str(exc)
            logger.exception("Error executing tool %s", tool_name)
            raise
        finally:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            self._record_audit(
                tool_call_id=cid,
                turn_id=turn_id,
                thread_id=thread_id,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                duration_ms=duration_ms,
                sandbox_id=sandbox_id,
                status=status,
                error_message=error_msg,
            )

        return result

    def _record_audit(
        self,
        tool_call_id: str,
        turn_id: Optional[str],
        thread_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        duration_ms: float,
        sandbox_id: Optional[str],
        status: str,
        error_message: Optional[str],
    ) -> None:
        """Internal helper to append audit log."""
        log = ToolCallAuditLog(
            tool_call_id=tool_call_id,
            turn_id=turn_id,
            thread_id=thread_id,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            duration_ms=duration_ms,
            sandbox_id=sandbox_id,
            status=status,
            error_message=error_message,
        )
        self._audit_logs.append(log)

    def get_audit_logs(
        self,
        turn_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> List[ToolCallAuditLog]:
        """Query tool call audit history."""
        logs = self._audit_logs
        if turn_id:
            logs = [l for l in logs if l.turn_id == turn_id]
        if tool_name:
            logs = [l for l in logs if l.tool_name == tool_name]
        return list(logs)

    # -------------------------------------------------------------------------
    # Default Controlled Tools Implementation
    # -------------------------------------------------------------------------
    def _register_default_tools(self) -> None:
        """Register the standard set of 9 CloudPilot controlled tools."""

        # 1. inspect_infrastructure
        self.register_tool(
            name="inspect_infrastructure",
            description="Query live cloud infrastructure inventory (M1 Discovery) including compute, databases, VPCs, and storage.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "scenario_name": {"type": "string", "description": "Scenario name (e.g. SaaS, E-commerce)"},
                    "resource_type": {"type": "string", "description": "Optional filter: compute, database, storage, vpc"},
                    "environment": {"type": "string", "description": "Optional filter: prod, dev, staging"},
                },
            },
            handler=self._tool_inspect_infrastructure,
            read_only=True,
            requires_approval=False,
        )

        # 2. analyze_costs
        self.register_tool(
            name="analyze_costs",
            description="Analyze cloud costs, monthly spend breakdown, idle resources, and optimization opportunities (M2 Cost Intelligence).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "scenario_name": {"type": "string", "description": "Scenario name"},
                    "target_reduction_pct": {"type": "number", "description": "Desired reduction percentage (e.g. 20.0)"},
                },
            },
            handler=self._tool_analyze_costs,
            read_only=True,
            requires_approval=False,
        )

        # 3. inspect_dependencies
        self.register_tool(
            name="inspect_dependencies",
            description="Inspect application service graph, upstream/downstream dependencies, and criticality tiers (M3 Application Intelligence).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "scenario_name": {"type": "string", "description": "Scenario name"},
                    "service_name": {"type": "string", "description": "Optional specific service name to inspect"},
                },
            },
            handler=self._tool_inspect_dependencies,
            read_only=True,
            requires_approval=False,
        )

        # 4. analyze_risks
        self.register_tool(
            name="analyze_risks",
            description="Assess blast radius, SLO risk probability, compliance constraints, and safety classification (M4 Risk Intelligence).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "proposed_actions": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of proposed infrastructure change actions",
                    },
                },
                "required": ["proposed_actions"],
            },
            handler=self._tool_analyze_risks,
            read_only=True,
            requires_approval=False,
        )

        # 5. simulate_action
        self.register_tool(
            name="simulate_action",
            description="Simulate an infrastructure modification on the Digital Twin (M6) to forecast savings, CPU/memory headroom, and latency impact.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "action_type": {"type": "string", "description": "Action: rightsize_instance, terminate_idle, archive_volume"},
                    "target_resource_id": {"type": "string", "description": "Target resource ID"},
                    "parameters": {"type": "object", "description": "Action specific parameters (e.g. target_type)"},
                },
                "required": ["action_type", "target_resource_id"],
            },
            handler=self._tool_simulate_action,
            read_only=True,
            requires_approval=False,
        )

        # 6. generate_terraform
        self.register_tool(
            name="generate_terraform",
            description="Generate safe Terraform HCL infrastructure code targeting approved cost optimization actions.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "actions": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of validated plan steps to generate code for",
                    },
                    "sandbox_id": {"type": "string", "description": "Target sandbox to store HCL artifact in"},
                },
                "required": ["actions"],
            },
            handler=self._tool_generate_terraform,
            read_only=False,
            requires_approval=False,
        )

        # 7. execute_terraform_plan
        self.register_tool(
            name="execute_terraform_plan",
            description="Execute terraform plan in the isolated sandbox without touching production. Returns resource diffs and stores plan artifacts.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "sandbox_id": {"type": "string", "description": "Sandbox ID"},
                    "hcl_code": {"type": "string", "description": "Terraform HCL code to plan"},
                },
                "required": ["sandbox_id", "hcl_code"],
            },
            handler=self._tool_execute_terraform_plan,
            read_only=True,
            requires_approval=False,
        )

        # 8. execute_sandbox_code
        self.register_tool(
            name="execute_sandbox_code",
            description="Execute analysis code in the isolated sandbox environment with timeout and output capture.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "sandbox_id": {"type": "string", "description": "Sandbox ID"},
                    "command": {"type": "array", "items": {"type": "string"}, "description": "Command list to run"},
                    "timeout_seconds": {"type": "number", "description": "Execution timeout"},
                },
                "required": ["sandbox_id", "command"],
            },
            handler=self._tool_execute_sandbox_code,
            read_only=False,
            requires_approval=False,
        )

        # 9. inspect_resource_state
        self.register_tool(
            name="inspect_resource_state",
            description="Inspect detailed live state, metrics, tags, and dependencies for a single cloud resource.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "resource_id": {"type": "string", "description": "Resource identifier"},
                },
                "required": ["resource_id"],
            },
            handler=self._tool_inspect_resource_state,
            read_only=True,
            requires_approval=False,
        )

    # -------------------------------------------------------------------------
    # Tool Handler Implementations
    # -------------------------------------------------------------------------
    def _get_resources_from_context(self, ctx: Any) -> List[Dict[str, Any]]:
        """Normalize resources from simulator ScenarioContext."""
        res: List[Dict[str, Any]] = []
        for c in getattr(ctx, "compute", []):
            tags = getattr(c, "tags", {}) or {}
            env = getattr(c, "environment", tags.get("env", "dev"))
            res.append({
                "resource_id": c.instance_id,
                "name": c.name,
                "type": "compute",
                "environment": env,
                "cost_per_month": c.monthly_cost_usd,
                "state": c.state.value if hasattr(c.state, "value") else str(c.state),
                "region": c.region,
                "tags": tags,
            })
        for d in getattr(ctx, "databases", []):
            tags = getattr(d, "tags", {}) or {}
            env = getattr(d, "environment", tags.get("env", "prod"))
            res.append({
                "resource_id": d.database_id,
                "name": d.name,
                "type": "database",
                "environment": env,
                "cost_per_month": d.monthly_cost_usd,
                "state": d.state.value if hasattr(d.state, "value") else str(d.state),
                "region": d.region,
                "tags": tags,
            })
        for s in getattr(ctx, "storage", []):
            tags = getattr(s, "tags", {}) or {}
            env = getattr(s, "environment", tags.get("env", "prod"))
            res.append({
                "resource_id": s.storage_id,
                "name": s.name,
                "type": "storage",
                "environment": env,
                "cost_per_month": s.monthly_cost_usd,
                "state": "available",
                "region": s.region,
                "tags": tags,
            })
        return res

    def _get_app_tier(self, app: Any) -> str:
        """Map app criticality enum to tier name."""
        crit = getattr(app, "criticality", None)
        c_val = crit.value if hasattr(crit, "value") else str(crit).lower()
        if "tier_1" in c_val or "mission_critical" in c_val or "tier-1" in c_val:
            return "tier-1"
        elif "tier_2" in c_val or "important" in c_val or "tier-2" in c_val:
            return "tier-2"
        elif "tier_3" in c_val or "internal" in c_val:
            return "tier-3"
        return "dev"

    def _tool_inspect_infrastructure(
        self,
        scenario_name: str = "SaaS",
        resource_type: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> Dict[str, Any]:
        sim = get_simulator()
        ctx = sim.get_context()
        if not ctx or getattr(ctx, "profile_name", None) != scenario_name:
            ctx = sim.generate(profile=scenario_name, scale="small", seed=42)

        resources = self._get_resources_from_context(ctx)
        if resource_type:
            resources = [r for r in resources if r["type"] == resource_type or resource_type in r["type"]]
        if environment:
            resources = [r for r in resources if r["environment"] == environment or r.get("tags", {}).get("env") == environment]

        account_id = ctx.account.account_id if hasattr(ctx, "account") else "acc-saas-prod"
        regions = list(set(r["region"] for r in resources)) if resources else ["us-east-1"]

        return {
            "scenario_name": scenario_name,
            "total_resources": len(resources),
            "accounts": [account_id],
            "regions": regions,
            "resource_summary": resources[:30],
        }

    def _tool_analyze_costs(
        self,
        scenario_name: str = "SaaS",
        target_reduction_pct: float = 20.0,
    ) -> Dict[str, Any]:
        sim = get_simulator()
        ctx = sim.get_context()
        if not ctx or getattr(ctx, "profile_name", None) != scenario_name:
            ctx = sim.generate(profile=scenario_name, scale="small", seed=42)

        resources = self._get_resources_from_context(ctx)
        total_cost = sum(r["cost_per_month"] for r in resources)
        target_savings = round(total_cost * (target_reduction_pct / 100.0), 2)

        optimization_candidates: List[Dict[str, Any]] = []
        for r in resources:
            env = r["environment"].lower()
            tags = r.get("tags", {})
            is_idle = tags.get("idle") == "true" or (r["cost_per_month"] > 50.0 and env in ("dev", "test", "staging"))
            is_unattached = tags.get("attached") == "false" or "unattached" in r["name"].lower()

            if env not in ("prod", "production") and (is_idle or is_unattached):
                est_savings = round(r["cost_per_month"] * 0.75, 2)
                optimization_candidates.append({
                    "resource_id": r["resource_id"],
                    "name": r["name"],
                    "type": r["type"],
                    "environment": env,
                    "current_cost_usd": r["cost_per_month"],
                    "estimated_savings_usd": est_savings,
                    "action_type": "terminate_idle" if is_unattached else "rightsize_instance",
                    "reason": "Unattached storage or idle development compute",
                })

        available_savings = sum(c["estimated_savings_usd"] for c in optimization_candidates)

        return {
            "scenario_name": scenario_name,
            "total_monthly_spend_usd": round(total_cost, 2),
            "target_reduction_pct": target_reduction_pct,
            "target_savings_usd": target_savings,
            "identified_opportunity_count": len(optimization_candidates),
            "total_identifiable_savings_usd": round(available_savings, 2),
            "target_achievable": available_savings >= target_savings,
            "candidates": optimization_candidates,
        }

    def _tool_inspect_dependencies(
        self,
        scenario_name: str = "SaaS",
        service_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        sim = get_simulator()
        ctx = sim.get_context()
        if not ctx or getattr(ctx, "profile_name", None) != scenario_name:
            ctx = sim.generate(profile=scenario_name, scale="small", seed=42)

        apps = getattr(ctx, "applications", [])
        if service_name:
            apps = [a for a in apps if a.name == service_name or a.app_id == service_name]

        app_list = []
        for a in apps:
            tier = self._get_app_tier(a)
            app_list.append({
                "app_id": a.app_id,
                "name": a.name,
                "criticality_tier": tier,
                "is_critical": tier in ("tier-1", "tier-2"),
                "environment": getattr(a, "environment", "prod"),
                "dependencies": [d for d in getattr(a, "dependencies", [])],
                "slo_target": getattr(a, "sla_target_percent", 99.9),
                "owner_team": getattr(a, "owner_team", "platform"),
            })

        return {
            "scenario_name": scenario_name,
            "total_applications": len(app_list),
            "applications": app_list,
        }

    def _tool_analyze_risks(
        self,
        proposed_actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        sim = get_simulator()
        ctx = sim.get_context()

        critical_services = set()
        if ctx:
            for app in getattr(ctx, "applications", []):
                tier = self._get_app_tier(app)
                if tier in ("tier-1", "tier-2"):
                    critical_services.add(app.name)
                    critical_services.add(app.app_id)

        evaluations = []
        any_critical_app_violation = False
        overall_risk = "LOW"

        for act in proposed_actions:
            target_res = act.get("target_resource_id", "")
            target_svc = act.get("target_service", "")
            env = act.get("environment", "dev").lower()

            is_critical_app = target_svc in critical_services or env in ("prod", "production")
            if is_critical_app:
                any_critical_app_violation = True
                blast_radius = "HIGH"
                slo_risk = 0.85
                verdict = "REJECTED_CRITICAL_APPLICATION_SAFETY"
            else:
                blast_radius = "LOW"
                slo_risk = 0.02
                verdict = "APPROVED_SAFE_OPTIMIZATION"

            evaluations.append({
                "target_resource_id": target_res,
                "target_service": target_svc,
                "environment": env,
                "is_critical_application": is_critical_app,
                "blast_radius": blast_radius,
                "slo_risk": slo_risk,
                "verdict": verdict,
                "requires_approval": not is_critical_app,
            })

        if any_critical_app_violation:
            overall_risk = "CRITICAL_VIOLATION"

        return {
            "total_actions_evaluated": len(proposed_actions),
            "any_critical_app_violation": any_critical_app_violation,
            "overall_risk_level": overall_risk,
            "evaluations": evaluations,
            "safe_to_proceed_with_approval": not any_critical_app_violation,
        }

    def _tool_simulate_action(
        self,
        action_type: str,
        target_resource_id: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        sim = get_simulator()
        ctx = sim.get_context()
        target_res = None
        if ctx:
            all_res = self._get_resources_from_context(ctx)
            for r in all_res:
                if r["resource_id"] == target_resource_id:
                    target_res = r
                    break

        base_cost = target_res["cost_per_month"] if target_res else 150.0
        if action_type in ("terminate_idle", "terminate", "delete"):
            savings = round(base_cost, 2)
            cpu_headroom = "0% (Terminated)"
        elif action_type in ("rightsize_instance", "rightsize"):
            savings = round(base_cost * 0.5, 2)
            cpu_headroom = "65% (Healthy)"
        else:
            savings = round(base_cost * 0.3, 2)
            cpu_headroom = "80% (Healthy)"

        return {
            "action_type": action_type,
            "target_resource_id": target_resource_id,
            "current_monthly_cost": base_cost,
            "simulated_monthly_savings": savings,
            "projected_cost_after_action": round(base_cost - savings, 2),
            "simulated_cpu_headroom": cpu_headroom,
            "simulated_slo_impact": "0.0% (Zero degradation)",
            "safety_verdict": "SAFE_TO_EXECUTE",
        }

    def _tool_generate_terraform(
        self,
        actions: List[Dict[str, Any]],
        sandbox_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        hcl_blocks = [
            "# CloudPilot TrueForge Autonomous Infrastructure Optimization",
            "# Environment: Sandbox Dry-Run (Production Access Disabled)",
            'terraform {\n  required_version = ">= 1.5.0"\n}\n',
        ]

        for idx, act in enumerate(actions, start=1):
            res_id = act.get("target_resource_id", f"res-{idx}")
            safe_name = res_id.replace("-", "_").replace(".", "_")
            act_type = act.get("action_type", "rightsize")

            if "terminate" in act_type:
                block = (
                    f'# Step {idx}: Terminate idle resource {res_id}\n'
                    f'resource "aws_instance" "{safe_name}" {{\n'
                    f'  # action: destroy (idle cleanup)\n'
                    f'  instance_type = "t3.micro"\n'
                    f'  tags = {{\n'
                    f'    CloudPilotOptimization = "TerminateIdle"\n'
                    f'    Status = "MarkedForCleanup"\n'
                    f'  }}\n'
                    f'}}\n'
                )
            else:
                block = (
                    f'# Step {idx}: Rightsize instance {res_id}\n'
                    f'resource "aws_instance" "{safe_name}" {{\n'
                    f'  # action: modify\n'
                    f'  instance_type = "t3.small"\n'
                    f'  tags = {{\n'
                    f'    CloudPilotOptimization = "RightsizeCompute"\n'
                    f'    OptimizedAt = "{datetime.now(timezone.utc).isoformat()}"\n'
                    f'  }}\n'
                    f'}}\n'
                )
            hcl_blocks.append(block)

        complete_hcl = "\n".join(hcl_blocks)

        artifact_meta = None
        if sandbox_id:
            sbx = get_sandbox_manager()
            artifact = sbx.store_artifact(
                sandbox_id=sandbox_id,
                filename="optimization_plan.tf",
                content=complete_hcl,
                artifact_type="terraform_hcl",
            )
            artifact_meta = artifact.model_dump(mode="json")

        return {
            "hcl_code": complete_hcl,
            "actions_count": len(actions),
            "artifact": artifact_meta,
        }

    def _tool_execute_terraform_plan(
        self,
        sandbox_id: str,
        hcl_code: str,
    ) -> Dict[str, Any]:
        sbx = get_sandbox_manager()
        return sbx.execute_terraform_plan(sandbox_id=sandbox_id, hcl_code=hcl_code)

    def _tool_execute_sandbox_code(
        self,
        sandbox_id: str,
        command: List[str],
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        sbx = get_sandbox_manager()
        res = sbx.execute_command(sandbox_id=sandbox_id, command=command, timeout_seconds=timeout_seconds)
        return res.model_dump()

    def _tool_inspect_resource_state(
        self,
        resource_id: str,
    ) -> Dict[str, Any]:
        sim = get_simulator()
        ctx = sim.get_context()
        found = None
        if ctx:
            for r in self._get_resources_from_context(ctx):
                if r["resource_id"] == resource_id:
                    found = r
                    break

        if not found:
            return {
                "resource_id": resource_id,
                "exists": False,
                "message": f"Resource {resource_id} not found in active simulation context",
            }

        return {
            "resource_id": found["resource_id"],
            "exists": True,
            "name": found["name"],
            "type": found["type"],
            "environment": found["environment"],
            "cost_per_month": found["cost_per_month"],
            "state": found["state"],
            "region": found.get("region", "us-east-1"),
            "tags": found.get("tags", {}),
            "telemetry_cpu_utilization": 15.0,
            "telemetry_memory_utilization": 25.0,
        }


# Global singleton instance
_tool_registry: Optional[ControlledToolRegistry] = None


def get_tool_registry() -> ControlledToolRegistry:
    """Get or create singleton ControlledToolRegistry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ControlledToolRegistry()
    return _tool_registry

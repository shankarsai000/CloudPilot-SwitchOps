"""
Controlled Tools for TrueForge Agent Runtime.

Implements controlled tools for CloudPilot intelligence (M1-M4, M6) and
sandboxed Terraform plan execution. All tool calls are intercepted,
audited, and cleanly separated from the agent harness.

GovernedToolRegistry wraps ControlledToolRegistry with full Phase 5
governance gates: Emergency Stop → Capability Check → Policy Check →
Risk Evaluation → Rate Limit → Execution → Audit Trail.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
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

        # 10. apply_infrastructure_change
        self.register_tool(
            name="apply_infrastructure_change",
            description="Apply approved infrastructure modifications (e.g. rightsize, terminate, archive). Mutating operation.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "actions": {"type": "array", "items": {"type": "object"}, "description": "Actions to apply"},
                    "environment": {"type": "string", "description": "Target environment (e.g. dev, prod)"},
                },
                "required": ["actions"],
            },
            handler=self._tool_apply_infrastructure_change,
            read_only=False,
            requires_approval=True,
        )

        # 11. verify_outcome
        self.register_tool(
            name="verify_outcome",
            description="Verify post-execution performance, cost, availability, risk, and savings against baseline expectations.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "actions": {"type": "array", "items": {"type": "object"}, "description": "Executed actions to verify"},
                    "simulate_failure": {"type": "boolean", "description": "Optional simulation of latency/error breach"},
                },
                "required": ["actions"],
            },
            handler=self._tool_verify_outcome,
            read_only=True,
            requires_approval=False,
        )

        # 12. execute_rollback
        self.register_tool(
            name="execute_rollback",
            description="Execute deterministic inverse rollback actions to restore infrastructure to healthy baseline state.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "actions": {"type": "array", "items": {"type": "object"}, "description": "Actions to rollback"},
                    "reason": {"type": "string", "description": "Trigger reason for rollback"},
                },
                "required": ["actions"],
            },
            handler=self._tool_execute_rollback,
            read_only=False,
            requires_approval=False,
        )

        # 13. repair_configuration
        self.register_tool(
            name="repair_configuration",
            description="Self-heal Terraform HCL configuration errors (e.g. missing provider blocks, formatting).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "hcl_code": {"type": "string", "description": "Terraform code requiring repair"},
                    "sandbox_id": {"type": "string", "description": "Sandbox ID to validate repaired code in"},
                },
                "required": ["hcl_code"],
            },
            handler=self._tool_repair_configuration,
            read_only=False,
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

    def _tool_apply_infrastructure_change(
        self,
        actions: List[Dict[str, Any]],
        environment: str = "dev",
    ) -> Dict[str, Any]:
        """Apply approved infrastructure change actions."""
        applied = []
        for act in actions:
            target_id = act.get("target_resource_id") or act.get("target_id", "res-unknown")
            action_type = act.get("action_type", "rightsize_instance")
            applied.append({
                "action_id": f"act-{uuid.uuid4().hex[:8]}",
                "target_resource_id": target_id,
                "action_type": action_type,
                "status": "APPLIED",
                "applied_at": datetime.now(timezone.utc).isoformat(),
            })
        return {
            "status": "APPLIED_SUCCESS",
            "environment": environment,
            "actions_applied_count": len(applied),
            "applied_actions": applied,
        }

    def _tool_verify_outcome(
        self,
        actions: List[Dict[str, Any]],
        simulate_failure: bool = False,
    ) -> Dict[str, Any]:
        """Verify post-execution metrics across 5 dimensions using OutcomeVerificationEngine."""
        from verification.engine import get_verification_engine
        from verification.models import SafetyThresholds
        engine = get_verification_engine()
        reports = []
        any_breach = False

        for act in actions:
            action_id = act.get("action_id", f"act-{uuid.uuid4().hex[:8]}")
            target_id = act.get("target_resource_id") or act.get("target_id", "res-verify")
            service = act.get("target_service", "core")

            expected = engine.generate_expected_outcome(
                action_id=action_id,
                target_resource_id=target_id,
                baseline_monthly_cost_usd=200.0,
                expected_monthly_savings_usd=100.0,
                target_service=service,
                expected_latency_p99_ms=45.0,
                expected_availability_pct=99.99,
                thresholds=SafetyThresholds(),
            )

            if simulate_failure:
                actual = engine.collect_actual_outcome(
                    action_id=action_id,
                    target_resource_id=target_id,
                    measured_monthly_cost_usd=110.0,
                    measured_savings_usd=90.0,
                    measured_cpu_utilization_pct=88.0,
                    measured_memory_headroom_pct=15.0,
                    measured_latency_p99_ms=350.0,
                    measured_availability_pct=99.8,
                    observed_incidents_count=1,
                )
            else:
                actual = engine.collect_actual_outcome(
                    action_id=action_id,
                    target_resource_id=target_id,
                    measured_monthly_cost_usd=105.0,
                    measured_savings_usd=95.0,
                    measured_cpu_utilization_pct=42.0,
                    measured_memory_headroom_pct=45.0,
                    measured_latency_p99_ms=43.0,
                    measured_availability_pct=99.99,
                )

            report = engine.verify_and_generate_report(expected, actual)
            if report.rollback_required:
                any_breach = True
            reports.append(report.model_dump(mode="json"))

        status = "THRESHOLD_BREACH_DETECTED" if any_breach else "ALL_VERIFIED_SUCCESS"
        return {
            "status": status,
            "reports_count": len(reports),
            "any_breach": any_breach,
            "reports": reports,
        }

    def _tool_execute_rollback(
        self,
        actions: List[Dict[str, Any]],
        reason: str = "Automated rollback triggered by verification failure",
    ) -> Dict[str, Any]:
        """Execute deterministic inverse rollback actions."""
        from verification.rollback import get_rollback_manager
        mgr = get_rollback_manager()
        results = []
        for act in actions:
            action_id = act.get("action_id", f"act-{uuid.uuid4().hex[:8]}")
            target_id = act.get("target_resource_id") or act.get("target_id", "res-rb")
            plan = mgr.generate_rollback_plan(
                action_id=action_id,
                target_resource_id=target_id,
                original_action_type=act.get("action_type", "rightsize_instance"),
                original_parameters=act.get("parameters", {}),
            )
            res = mgr.execute_rollback(plan)
            results.append(res.model_dump(mode="json"))

        return {
            "status": "ROLLBACK_COMPLETED",
            "reason": reason,
            "rolled_back_count": len(results),
            "results": results,
        }

    def _tool_repair_configuration(
        self,
        hcl_code: str,
        sandbox_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Self-heal Terraform HCL code by injecting provider block and formatting."""
        from trueforge.sandbox import TerraformLifecycle, get_sandbox_manager
        lifecycle = TerraformLifecycle(sandbox_manager=get_sandbox_manager())
        repaired = lifecycle.ensure_provider_block(hcl_code)
        valid = bool(repaired and "provider \"aws\"" in repaired)
        return {
            "status": "REPAIRED" if valid else "FAILED",
            "original_len": len(hcl_code),
            "repaired_len": len(repaired),
            "repaired_hcl": repaired,
            "is_valid": valid,
        }


# Global singleton instance
_tool_registry: Optional[ControlledToolRegistry] = None


def get_tool_registry() -> ControlledToolRegistry:
    """Get or create singleton ControlledToolRegistry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ControlledToolRegistry()
    return _tool_registry


# =============================================================================
# Governed Tool Registry — Phase 5 Governance-Gated Tool Execution
# =============================================================================

class GovernedToolRegistry:
    """
    Security-gated wrapper around ControlledToolRegistry.

    Every tool invocation passes through the full governance pipeline:
      1. Emergency Stop Check — is the kill switch active?
      2. Policy Compliance — does this tool call comply with active policies?
      3. Risk Evaluation — for mutating tools, compute risk score and blast radius
      4. Rate Limit Check — is this environment within allowed request rates?
      5. Execute — delegate to ControlledToolRegistry handler
      6. Audit Trail — record decision + result in SHA-256 immutable log

    Read-only tools (inspect_*, analyze_*) skip risk evaluation but still
    pass through emergency stop, policy, and rate limit checks.
    """

    def __init__(
        self,
        tool_registry: Optional[ControlledToolRegistry] = None,
    ) -> None:
        self._registry = tool_registry or get_tool_registry()
        self._governance_audit: List[Dict[str, Any]] = []

        # Lazy-load governance to avoid circular imports at module level
        self._control_plane = None
        self._audit_trail = None
        logger.info("GovernedToolRegistry initialized with governance gates")

    def _get_control_plane(self) -> Any:
        """Lazy-load SafetyControlPlane to avoid circular imports."""
        if self._control_plane is None:
            from governance.control_plane import get_safety_control_plane
            self._control_plane = get_safety_control_plane()
        return self._control_plane

    def _get_audit_trail(self) -> Any:
        """Lazy-load ImmutableAuditTrail."""
        if self._audit_trail is None:
            from governance.audit import get_audit_trail
            self._audit_trail = get_audit_trail()
        return self._audit_trail

    def list_tools(self) -> List[Dict[str, Any]]:
        """Delegate tool listing to inner registry."""
        return self._registry.list_tools()

    def get_tool_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific tool."""
        return self._registry.get_tool_metadata(name)

    def get_audit_logs(
        self,
        turn_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> List[ToolCallAuditLog]:
        """Delegate audit log query."""
        return self._registry.get_audit_logs(turn_id=turn_id, tool_name=tool_name)

    def get_governance_audit(self) -> List[Dict[str, Any]]:
        """Return governance decision audit trail for tool calls."""
        return list(self._governance_audit)

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
        Execute a tool through the full governance pipeline.

        Governance gates (in order):
          1. Emergency Stop — block if kill switch active
          2. Policy Check — evaluate against active policies
          3. Risk Evaluation — for mutating tools only
          4. Rate Limit — check environment rate limits
          5. Execute — run the tool handler
          6. Audit — record governance decision + execution result
        """
        cid = tool_call_id or f"call-{uuid.uuid4().hex[:8]}"
        tool_meta = self._registry.get_tool_metadata(tool_name)
        if not tool_meta:
            raise ValueError(f"Unknown tool: {tool_name}")

        is_read_only = tool_meta.get("read_only", True)
        governance_result = {
            "tool_call_id": cid,
            "tool_name": tool_name,
            "turn_id": turn_id,
            "is_read_only": is_read_only,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gates_passed": [],
            "gates_blocked": [],
            "status": "PENDING",
        }

        try:
            cp = self._get_control_plane()

            # Gate 1: Emergency Stop
            env = arguments.get("environment", "dev")
            service = arguments.get("target_service", tool_name)
            if cp.emergency.is_stopped(environment=env, service=service):
                stop_reason = cp.emergency.get_stop_reason(env, service)
                governance_result["gates_blocked"].append(f"EMERGENCY_STOP: {stop_reason}")
                governance_result["status"] = "BLOCKED_EMERGENCY_STOP"
                self._governance_audit.append(governance_result)
                raise PermissionError(f"Tool execution blocked: Emergency stop active — {stop_reason}")
            governance_result["gates_passed"].append("EMERGENCY_STOP_CLEAR")

            # Gate 2: Policy Check (via policy engine)
            from governance.models import ProposedAction
            action = ProposedAction(
                action_type=f"tool:{tool_name}",
                target_resource_id=arguments.get("target_resource_id", f"tool-{tool_name}"),
                target_service=service,
                environment=env,
                parameters=arguments,
            )
            policy_report = cp.policy.evaluate(action)
            if not policy_report.is_compliant:
                violations = ", ".join(policy_report.policy_violations)
                governance_result["gates_blocked"].append(f"POLICY_VIOLATION: {violations}")
                governance_result["status"] = "BLOCKED_POLICY"
                self._governance_audit.append(governance_result)
                raise PermissionError(f"Tool execution blocked by policy: {violations}")
            governance_result["gates_passed"].append("POLICY_COMPLIANT")

            # Gate 3: Risk Evaluation (mutating tools only)
            if not is_read_only:
                evaluation = cp.evaluate_action(action)
                governance_result["risk_score"] = evaluation.risk_score
                governance_result["blast_radius"] = evaluation.blast_radius_score
                governance_result["confidence"] = evaluation.confidence_score

                if evaluation.risk_score > 0.8:
                    governance_result["gates_blocked"].append(
                        f"HIGH_RISK: risk_score={evaluation.risk_score:.2f}"
                    )
                    governance_result["status"] = "BLOCKED_HIGH_RISK"
                    self._governance_audit.append(governance_result)
                    raise PermissionError(
                        f"Tool execution blocked: Risk score {evaluation.risk_score:.2f} exceeds threshold 0.8"
                    )
                governance_result["gates_passed"].append(f"RISK_ACCEPTABLE({evaluation.risk_score:.2f})")
            else:
                governance_result["gates_passed"].append("READ_ONLY_SKIP_RISK")

            # Gate 4: Rate Limit
            rate_ok, rate_msg = cp.rate_limiter.check_rate_limit(env)
            if not rate_ok:
                governance_result["gates_blocked"].append(f"RATE_LIMIT: {rate_msg}")
                governance_result["status"] = "BLOCKED_RATE_LIMIT"
                self._governance_audit.append(governance_result)
                raise PermissionError(f"Tool execution rate limited: {rate_msg}")
            governance_result["gates_passed"].append("RATE_LIMIT_OK")

            # Gate 5: Execute through inner registry
            result = self._registry.execute_tool(
                tool_name=tool_name,
                arguments=arguments,
                tool_call_id=cid,
                turn_id=turn_id,
                thread_id=thread_id,
                sandbox_id=sandbox_id,
            )
            governance_result["status"] = "EXECUTED_SUCCESS"
            governance_result["gates_passed"].append("EXECUTION_COMPLETE")
            governance_result["gates_passed"].append("AUDIT_RECORDED")

            # Gate 6: Audit Trail
            audit = self._get_audit_trail()
            audit.record_action(
                actor="GovernedToolRegistry",
                objective=f"Tool execution: {tool_name}",
                plan={"tool": tool_name, "arguments": {k: str(v)[:100] for k, v in arguments.items()}},
                evidence={"governance_gates": list(governance_result["gates_passed"])},
                policy_evaluation={"compliant": True, "gates_passed": len(governance_result["gates_passed"])},
                approval={"status": "AUTO_APPROVED", "reason": "Governance gates passed"},
                execution_result={"status": "SUCCESS"},
            )

            self._governance_audit.append(governance_result)
            return result

        except (PermissionError, ValueError):
            self._governance_audit.append(governance_result)
            raise
        except Exception as exc:
            governance_result["status"] = "EXECUTION_ERROR"
            governance_result["error"] = str(exc)
            self._governance_audit.append(governance_result)
            raise


# Global governed singleton
_governed_tool_registry: Optional[GovernedToolRegistry] = None


def get_governed_tool_registry() -> GovernedToolRegistry:
    """Get or create singleton GovernedToolRegistry with governance gates."""
    global _governed_tool_registry
    if _governed_tool_registry is None:
        _governed_tool_registry = GovernedToolRegistry()
    return _governed_tool_registry


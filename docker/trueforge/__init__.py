"""
CloudPilot TrueForge Autonomous Agent Runtime Package.

Integrates CloudPilot intelligence with TrueForge agent harness & TrueFoundry AI Gateway.
"""

from trueforge.gateway import TrueForgeGatewayAdapter, build_cloudpilot_agent_manifest
from trueforge.models import (
    CodeArtifact,
    ExecutionPlan,
    ExecutionPlanStep,
    OperationalObjective,
    SandboxExecutionResult,
    ToolCallAuditLog,
)
from trueforge.routes import router as trueforge_router
from trueforge.runtime import TrueForgeAgentRuntime, get_agent_runtime
from trueforge.sandbox import SandboxManager, get_sandbox_manager
from trueforge.state import AgentStateManager, get_agent_state_manager
from trueforge.tools import ControlledToolRegistry, get_tool_registry

__all__ = [
    "TrueForgeAgentRuntime",
    "get_agent_runtime",
    "TrueForgeGatewayAdapter",
    "build_cloudpilot_agent_manifest",
    "SandboxManager",
    "get_sandbox_manager",
    "AgentStateManager",
    "get_agent_state_manager",
    "ControlledToolRegistry",
    "get_tool_registry",
    "trueforge_router",
    "OperationalObjective",
    "ExecutionPlan",
    "ExecutionPlanStep",
    "ToolCallAuditLog",
    "CodeArtifact",
    "SandboxExecutionResult",
]

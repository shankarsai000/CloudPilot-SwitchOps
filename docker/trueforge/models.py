"""
TrueForge Models & Official Schema Integration.

Re-exports official TrueFoundry AI Gateway & TrueForge Agent Harness models
and defines CloudPilot operational objective, execution plan, and audit models.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field

# Re-export official TrueFoundry Gateway SDK types
from truefoundry_gateway_sdk import (
    ActionRequiredEvent,
    AgentInfo,
    AgentParent,
    AgentSpec,
    AgentSpecUserMessage,
    ApprovalAllow,
    ApprovalDecision,
    ApprovalDeny,
    ChatCompletionMessageToolCall,
    FileContent,
    McpAuthRequiredEvent,
    McpInitializeEvent,
    McpServer,
    McpServerAuthInfo,
    McpServerInitInfo,
    Model,
    ModelMessageDeltaEvent,
    ModelMessageEvent,
    ModelParams,
    RegisteredMcpServer,
    ResponseFormat,
    ResponseFormatZero,
    RuntimeConfig,
    SandboxConfig,
    SandboxCreatedEvent,
    Session,
    Subject,
    TextContent,
    ThreadCreatedEvent,
    ThreadDoneEvent,
    ThreadState,
    ThreadStateDone,
    ThreadStateError,
    ToolApprovalRequiredEvent,
    ToolCall,
    ToolCallRef,
    ToolInfo,
    ToolResponseEvent,
    ToolResponseRequiredEvent,
    ToolsSelectorTag,
    TrueFoundryGateway,
    Turn,
    TurnCreatedEvent,
    TurnDoneEvent,
    TurnEvent,
    TurnInputItem,
    TurnMetrics,
    TurnState,
    TurnStateCancelled,
    TurnStateDone,
    TurnStateError,
    TurnStateRunning,
    TurnStreamingEvent,
    UserMessage,
    UserMessageContentItem,
    UserToolApprovalEvent,
    UserToolResponseEvent,
)
from truefoundry_gateway_sdk.agents import (
    is_event_delta,
    merge_event_delta,
)


class OperationalObjective(BaseModel):
    """Structured representation of a natural-language operational objective."""

    objective_text: str = Field(..., description="Original user prompt/objective")
    target_cost_reduction_pct: float = Field(20.0, description="Target reduction percentage")
    preserve_critical_applications: bool = Field(True, description="Strict rule: never degrade critical apps")
    allowed_environments: List[str] = Field(
        default_factory=lambda: ["dev", "staging", "test", "sandbox"],
        description="Environments eligible for automated modifications",
    )
    require_approval: bool = Field(True, description="Enforce human approval checkpoint before state modification")
    scenario_name: str = Field("SaaS", description="Cloud environment / simulator scenario to operate on")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionPlanStep(BaseModel):
    """Discrete atomic change step within an agent execution plan."""

    step_id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:8]}")
    action_type: str = Field(..., description="E.g. rightsize_instance, terminate_idle_instance, cleanup_unattached_volume")
    target_resource_id: str = Field(..., description="Target cloud resource ID")
    target_service: str = Field(..., description="Application or service name")
    environment: str = Field("dev", description="Resource environment")
    criticality_tier: str = Field("dev", description="Criticality tier: tier-1, tier-2, dev")
    projected_monthly_savings_usd: float = Field(0.0, description="Expected monthly savings in USD")
    blast_radius: str = Field("LOW", description="Blast radius classification: LOW, MEDIUM, HIGH")
    slo_risk: float = Field(0.0, description="Estimated probability of SLO degradation (0.0 - 1.0)")
    requires_approval: bool = Field(True, description="Whether this step triggers an approval interrupt")
    terraform_hcl: Optional[str] = Field(None, description="Generated Terraform HCL code snippet")
    status: str = Field("PENDING", description="Status: PENDING, APPROVED, EXECUTED, DENIED, FAILED")


class ExecutionPlan(BaseModel):
    """End-to-end execution plan synthesized by CloudPilot intelligence."""

    plan_id: str = Field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    objective: str = Field(..., description="Operational objective")
    scenario_name: str = Field("SaaS", description="Target scenario")
    total_baseline_cost_usd: float = Field(0.0, description="Current monthly cloud spend")
    projected_monthly_savings_usd: float = Field(0.0, description="Total projected monthly savings")
    projected_cost_reduction_pct: float = Field(0.0, description="Total projected percentage savings")
    steps: List[ExecutionPlanStep] = Field(default_factory=list, description="Ordered execution steps")
    critical_applications_protected: List[str] = Field(default_factory=list, description="Critical apps verified untouched")
    requires_human_approval: bool = Field(True, description="Whether plan contains gated actions")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = Field("GENERATED", description="Status: GENERATED, AWAITING_APPROVAL, APPROVED, EXECUTED, REJECTED")


class ToolCallAuditLog(BaseModel):
    """Audit record capturing every tool call for compliance and observability."""

    audit_id: str = Field(default_factory=lambda: f"audit-{uuid.uuid4().hex[:10]}")
    turn_id: Optional[str] = None
    thread_id: str = "main"
    tool_call_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    duration_ms: float = 0.0
    sandbox_id: Optional[str] = None
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "SUCCESS"
    error_message: Optional[str] = None


class CodeArtifact(BaseModel):
    """Metadata for code generated and stored by the agent runtime."""

    artifact_id: str = Field(default_factory=lambda: f"art-{uuid.uuid4().hex[:8]}")
    sandbox_id: str
    filename: str
    relative_path: str
    absolute_path: str
    sha256_hash: str
    size_bytes: int
    artifact_type: str = "terraform_hcl"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_content(
        cls,
        sandbox_id: str,
        filename: str,
        relative_path: str,
        absolute_path: str,
        content: str,
        artifact_type: str = "terraform_hcl",
    ) -> "CodeArtifact":
        content_bytes = content.encode("utf-8")
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        return cls(
            sandbox_id=sandbox_id,
            filename=filename,
            relative_path=relative_path,
            absolute_path=absolute_path,
            sha256_hash=sha256,
            size_bytes=len(content_bytes),
            artifact_type=artifact_type,
        )


class SandboxExecutionResult(BaseModel):
    """Result of running code or commands in an isolated sandbox."""

    sandbox_id: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    resource_limit_exceeded: bool = False
    artifacts_generated: List[str] = Field(default_factory=list)
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

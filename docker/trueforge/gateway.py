"""
TrueFoundry AI Gateway Client Adapter & Event Streaming Engine.

Provides clean integration with the official TrueFoundry AI Gateway SDK,
supporting live gateway connections or high-fidelity deterministic execution
for offline and test environments.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional
import uuid

from trueforge.models import (
    AgentSpec,
    ApprovalAllow,
    ApprovalDeny,
    ChatCompletionMessageToolCall,
    McpInitializeEvent,
    McpServerInitInfo,
    Model,
    ModelMessageDeltaEvent,
    ModelMessageEvent,
    ModelParams,
    RegisteredMcpServer,
    ResponseFormatZero,
    RuntimeConfig,
    SandboxConfig,
    SandboxCreatedEvent,
    Subject,
    ToolApprovalRequiredEvent,
    ToolCall,
    ToolCallRef,
    ToolInfo,
    ToolResponseEvent,
    TrueFoundryGateway,
    TurnCreatedEvent,
    TurnDoneEvent,
    TurnMetrics,
    TurnStateDone,
    TurnStateRunning,
    TurnStreamingEvent,
    UserMessage,
    UserToolApprovalEvent,
)

logger = logging.getLogger("cloudpilot.trueforge.gateway")


def build_cloudpilot_agent_manifest() -> AgentSpec:
    """
    Construct the official AgentSpec manifest for the CloudPilot Autonomous Agent.
    """
    return AgentSpec(
        name="cloudpilot-cost-optimizer",
        description=(
            "Autonomous CloudPilot optimization agent that analyzes cloud infrastructure, "
            "evaluates cost and application dependencies, generates safe Terraform code in a sandbox, "
            "and requests human approval before applying changes."
        ),
        model=Model(
            name=os.getenv("TFY_MODEL_NAME", "anthropic/claude-sonnet-4-6"),
            params=ModelParams(
                max_tokens=4096,
                temperature=0.2,
            ),
        ),
        instructions=(
            "You are CloudPilot AI, an autonomous Principal Cloud Platform & FinOps Engineer.\n"
            "Your objective is to optimize cloud costs without impacting critical Tier-1 applications.\n"
            "Workflow Rules:\n"
            "1. Inspect infrastructure inventory and dependencies.\n"
            "2. Identify idle and unattached waste in non-critical environments (dev, test, staging).\n"
            "3. Strictly protect critical Tier-1 and production applications; never degrade their SLOs.\n"
            "4. Generate clean Terraform HCL for optimizations and plan in the isolated sandbox.\n"
            "5. Pause for human approval if modifications require changes to existing resources.\n"
            "6. After approval, finalize the operational report."
        ),
        mcp_servers=[
            RegisteredMcpServer(
                name="cloudpilot-controlled-tools",
                enable_tools=["@all"],
                require_approval_for_tools=["@write", "@destructive", "rightsize_instance", "terminate_idle"],
            )
        ],
        config=RuntimeConfig(
            iteration_limit=25,
            timeout_seconds=900,
            sandbox=SandboxConfig(enabled=True, file_downloads=True),
        ),
        response_format=ResponseFormatZero(type="text"),
    )


class TrueForgeGatewayAdapter:
    """
    Adapter bridging CloudPilot with TrueFoundry AI Gateway & Agent Harness.
    Supports official live gateway SDK or local deterministic execution engine.
    """

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.gateway_url = gateway_url or os.getenv("TFY_GATEWAY_URL")
        self.api_key = api_key or os.getenv("TFY_API_KEY")
        self._live_client: Optional[TrueFoundryGateway] = None

        if self.gateway_url and self.api_key:
            try:
                self._live_client = TrueFoundryGateway(
                    base_url=self.gateway_url,
                    api_key=self.api_key,
                )
                logger.info("Connected to live TrueFoundry AI Gateway at %s", self.gateway_url)
            except Exception as e:
                logger.warning("Could not initialize live TrueFoundry gateway client: %s", e)
        else:
            logger.info("Running TrueForgeGatewayAdapter in local deterministic engine mode")

    @property
    def is_live(self) -> bool:
        return self._live_client is not None

    def get_live_client(self) -> Optional[TrueFoundryGateway]:
        return self._live_client

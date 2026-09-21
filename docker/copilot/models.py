"""
CloudPilot Copilot Models.

Data structures for conversational AI interaction, intent classification,
evidence presentation, and autonomous mission linkage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field


class CopilotRole(str, Enum):
    """Message sender role."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class CopilotIntent(str, Enum):
    """Classified conversational intent."""
    DIAGNOSE_BILLING = "DIAGNOSE_BILLING"
    INVENTORY_QUERY = "INVENTORY_QUERY"
    DEPENDENCY_QUERY = "DEPENDENCY_QUERY"
    DISPATCH_MISSION = "DISPATCH_MISSION"  # "Fix it", "Reduce cost by 20%"
    APPROVE_EXECUTION = "APPROVE_EXECUTION"  # "Approve", "Yes, apply it"
    DENY_EXECUTION = "DENY_EXECUTION"  # "Deny", "Cancel"
    QUERY_APPROVALS = "QUERY_APPROVALS"  # "Show pending approvals"
    GENERAL_QUERY = "GENERAL_QUERY"


class CopilotMessage(BaseModel):
    """Discrete message in a Copilot conversation."""
    message_id: str = Field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    role: CopilotRole
    content: str
    intent: Optional[CopilotIntent] = None
    evidence: Optional[Dict[str, Any]] = None
    structured_data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CopilotConversation(BaseModel):
    """Multi-turn conversation session tracking context and active agent missions."""
    conversation_id: str = Field(default_factory=lambda: f"conv-{uuid.uuid4().hex[:8]}")
    messages: List[CopilotMessage] = Field(default_factory=list)
    active_session_id: Optional[str] = None
    pending_approval_checkpoint_id: Optional[str] = None
    scenario_name: str = "SaaS"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def add_message(
        self,
        role: CopilotRole,
        content: str,
        intent: Optional[CopilotIntent] = None,
        evidence: Optional[Dict[str, Any]] = None,
        structured_data: Optional[Dict[str, Any]] = None,
    ) -> CopilotMessage:
        msg = CopilotMessage(
            role=role,
            content=content,
            intent=intent,
            evidence=evidence,
            structured_data=structured_data,
        )
        self.messages.append(msg)
        self.updated_at = datetime.now(timezone.utc)
        return msg


class CopilotResponse(BaseModel):
    """Response returned to user with conversational text and actionable UI payloads."""
    conversation_id: str
    reply_text: str
    intent: CopilotIntent
    evidence: Optional[Dict[str, Any]] = None
    pending_approval: Optional[Dict[str, Any]] = None
    agent_state: Optional[str] = None
    quick_actions: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

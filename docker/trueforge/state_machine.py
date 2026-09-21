"""
CloudPilot Durable Agent State Machine.

Provides a persistent, thread-safe, crash-resilient state machine for
the TrueForge Autonomous Agent Control Loop. Every state transition is
validated against legal transitions and atomically serialized to disk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
import logging
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Set
import uuid

from pydantic import BaseModel, Field

logger = logging.getLogger("cloudpilot.trueforge.state_machine")

DEFAULT_STATE_MACHINE_FILE = Path("docker/scratch/state/agent_state_machine.json").resolve()


class AgentState(str, Enum):
    """Lifecycle states of the autonomous agent control loop."""
    # Active operational states
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    OBSERVING = "OBSERVING"
    DECIDING = "DECIDING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"

    # Terminal / Failure / Recovery states
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"


# Strict state transition matrix
ALLOWED_TRANSITIONS: Dict[AgentState, Set[AgentState]] = {
    AgentState.CREATED: {
        AgentState.PLANNING,
        AgentState.FAILED,
        AgentState.CANCELLED,
    },
    AgentState.PLANNING: {
        AgentState.EXECUTING_TOOL,
        AgentState.DECIDING,
        AgentState.BLOCKED,
        AgentState.FAILED,
        AgentState.CANCELLED,
    },
    AgentState.EXECUTING_TOOL: {
        AgentState.OBSERVING,
        AgentState.FAILED,
        AgentState.BLOCKED,
    },
    AgentState.OBSERVING: {
        AgentState.DECIDING,
        AgentState.PLANNING,
        AgentState.EXECUTING_TOOL,
        AgentState.FAILED,
        AgentState.BLOCKED,
    },
    AgentState.DECIDING: {
        AgentState.PLANNING,
        AgentState.EXECUTING_TOOL,
        AgentState.WAITING_FOR_APPROVAL,
        AgentState.EXECUTING,
        AgentState.BLOCKED,
        AgentState.COMPLETED,
        AgentState.FAILED,
    },
    AgentState.WAITING_FOR_APPROVAL: {
        AgentState.EXECUTING,
        AgentState.CANCELLED,
        AgentState.BLOCKED,
        AgentState.FAILED,
    },
    AgentState.EXECUTING: {
        AgentState.VERIFYING,
        AgentState.ROLLING_BACK,
        AgentState.FAILED,
    },
    AgentState.VERIFYING: {
        AgentState.COMPLETED,
        AgentState.ROLLING_BACK,
        AgentState.FAILED,
    },
    AgentState.ROLLING_BACK: {
        AgentState.ROLLED_BACK,
        AgentState.FAILED,
    },
    AgentState.COMPLETED: set(),
    AgentState.FAILED: set(),
    AgentState.BLOCKED: {
        AgentState.PLANNING,
        AgentState.CANCELLED,
    },
    AgentState.CANCELLED: set(),
    AgentState.ROLLED_BACK: set(),
}


class AgentStepRecord(BaseModel):
    """Chronological trace record of an individual agent step."""
    step_number: int
    thought: str
    action_tool: Optional[str] = None
    action_args: Dict[str, Any] = Field(default_factory=dict)
    observation: Optional[Dict[str, Any]] = None
    decision: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DurableAgentContext(BaseModel):
    """
    Complete, serializable execution context of the autonomous agent.
    Can be restored from disk at any state (especially WAITING_FOR_APPROVAL)
    after a cold process restart.
    """
    session_id: str = Field(default_factory=lambda: f"sess-{uuid.uuid4().hex[:8]}")
    run_id: str = Field(default_factory=lambda: f"run-{uuid.uuid4().hex[:8]}")
    goal: str
    scenario_name: str = "SaaS"
    current_state: AgentState = AgentState.CREATED
    step_history: List[AgentStepRecord] = Field(default_factory=list)

    # Discovered & inferred knowledge
    discovered_inventory: Dict[str, Any] = Field(default_factory=dict)
    cost_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    dependencies: Dict[str, Any] = Field(default_factory=dict)
    selected_actions: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_actions: List[Dict[str, Any]] = Field(default_factory=list)

    # Infrastructure as code & sandbox
    hcl_code: Optional[str] = None
    plan_output: Optional[Dict[str, Any]] = None
    sandbox_id: Optional[str] = None

    # Safety & Approval
    risk_evaluation: Optional[Dict[str, Any]] = None
    checkpoint_id: Optional[str] = None
    approval_required: bool = False
    approved_by: Optional[str] = None

    # Execution & Verification
    execution_result: Optional[Dict[str, Any]] = None
    verification_report: Optional[Dict[str, Any]] = None
    rollback_report: Optional[Dict[str, Any]] = None
    learning_record: Optional[Dict[str, Any]] = None

    # Stop conditions & metadata
    stop_reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_terminal(self) -> bool:
        """Return True if agent has reached an un-resumable terminal state."""
        return self.current_state in {
            AgentState.COMPLETED,
            AgentState.FAILED,
            AgentState.CANCELLED,
            AgentState.ROLLED_BACK,
        }

    def record_step(
        self,
        thought: str,
        action_tool: Optional[str] = None,
        action_args: Optional[Dict[str, Any]] = None,
        observation: Optional[Dict[str, Any]] = None,
        decision: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> AgentStepRecord:
        """Append an audited step to execution history."""
        step = AgentStepRecord(
            step_number=len(self.step_history) + 1,
            thought=thought,
            action_tool=action_tool,
            action_args=action_args or {},
            observation=observation,
            decision=decision,
            duration_ms=duration_ms,
        )
        self.step_history.append(step)
        self.updated_at = datetime.now(timezone.utc)
        return step


class DurableStateMachine:
    """
    Thread-safe, disk-backed state machine for managing agent context transitions.
    Enforces valid state graph transitions and atomic disk writes.
    """

    def __init__(self, persistence_file: Optional[Path] = None) -> None:
        self.persistence_file = Path(persistence_file or DEFAULT_STATE_MACHINE_FILE)
        self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
        self._contexts: Dict[str, DurableAgentContext] = {}  # session_id -> context
        self._lock = threading.Lock()
        self._load_from_disk()

    def transition(
        self,
        context: DurableAgentContext,
        new_state: AgentState,
        reason: Optional[str] = None,
    ) -> None:
        """
        Validate and perform a state transition, updating timestamps and persisting.
        Raises ValueError on invalid transitions.
        """
        with self._lock:
            current = context.current_state
            allowed = ALLOWED_TRANSITIONS.get(current, set())
            if new_state not in allowed:
                raise ValueError(
                    f"Illegal state transition from {current.value} to {new_state.value}. "
                    f"Allowed target states: {[s.value for s in allowed]}"
                )

            context.current_state = new_state
            context.updated_at = datetime.now(timezone.utc)
            if reason:
                context.stop_reason = reason

            self._contexts[context.session_id] = context
            self._save_to_disk_locked()

        logger.info(
            "Agent [%s] transitioned from %s -> %s (reason: %s)",
            context.session_id, current.value, new_state.value, reason or "normal",
        )

    def save(self, context: DurableAgentContext) -> None:
        """Persist or update context in storage."""
        with self._lock:
            context.updated_at = datetime.now(timezone.utc)
            self._contexts[context.session_id] = context
            self._save_to_disk_locked()

    def get_context(self, session_id: str) -> Optional[DurableAgentContext]:
        """Retrieve context by session_id from memory or disk."""
        with self._lock:
            return self._contexts.get(session_id)

    def list_contexts(self) -> List[DurableAgentContext]:
        """List all managed agent contexts."""
        with self._lock:
            return list(self._contexts.values())

    def clear(self) -> None:
        """Clear all in-memory and on-disk contexts (useful for tests)."""
        with self._lock:
            self._contexts.clear()
            if self.persistence_file.exists():
                try:
                    self.persistence_file.unlink()
                except OSError:
                    pass

    # -------------------------------------------------------------------------
    # Disk Persistence
    # -------------------------------------------------------------------------
    def _save_to_disk_locked(self) -> None:
        try:
            payload = {
                "contexts": [ctx.model_dump(mode="json") for ctx in self._contexts.values()],
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp_file = self.persistence_file.with_suffix(".tmp")
            tmp_file.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            tmp_file.replace(self.persistence_file)
        except Exception as e:
            logger.warning("Failed to serialize state machine to disk: %s", e)

    def _load_from_disk(self) -> None:
        if not self.persistence_file.exists():
            return
        try:
            raw = json.loads(self.persistence_file.read_text(encoding="utf-8"))
            for item in raw.get("contexts", []):
                ctx = DurableAgentContext(**item)
                self._contexts[ctx.session_id] = ctx
            logger.info("Loaded %d agent contexts from %s", len(self._contexts), self.persistence_file)
        except Exception as e:
            logger.warning("Could not load state machine from %s: %s", self.persistence_file, e)


# Global singleton
_state_machine_instance: Optional[DurableStateMachine] = None


def get_durable_state_machine() -> DurableStateMachine:
    """Get or create singleton DurableStateMachine."""
    global _state_machine_instance
    if _state_machine_instance is None:
        _state_machine_instance = DurableStateMachine()
    return _state_machine_instance

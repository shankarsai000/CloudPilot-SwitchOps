"""
Agent State Persistence & Resumable Execution Engine.

Manages sessions, turns, event streams, approval checkpoints, and artifact
references with thread-safety and disk-backed persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

from trueforge.models import (
    ApprovalAllow,
    ApprovalDeny,
    ExecutionPlan,
    Session,
    Subject,
    Turn,
    TurnEvent,
    TurnInputItem,
    TurnState,
    TurnStateCancelled,
    TurnStateDone,
    TurnStateError,
    TurnStateRunning,
)

logger = logging.getLogger("cloudpilot.trueforge.state")

DEFAULT_STATE_FILE = Path("docker/scratch/state/agent_state.json").resolve()


class AgentStateManager:
    """
    Persistent state engine managing Agent Sessions, Turns, Event logs,
    and Human-in-the-loop Approval Checkpoints.
    """

    def __init__(self, state_file: Optional[Path] = None) -> None:
        self.state_file = Path(state_file or DEFAULT_STATE_FILE)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, Session] = {}
        self._turns: Dict[str, Dict[str, Turn]] = {}  # session_id -> {turn_id: Turn}
        self._events: Dict[str, List[Dict[str, Any]]] = {}  # turn_id -> list of serialized events
        self._checkpoints: Dict[str, Dict[str, Any]] = {}  # turn_id -> checkpoint data
        self._lock = threading.Lock()
        self._load_from_disk()
        logger.info("AgentStateManager initialized (persisting to %s)", self.state_file)

    def _load_from_disk(self) -> None:
        """Load state from persistent JSON storage if present."""
        if not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            for s_dict in raw.get("sessions", []):
                sess = Session(**s_dict)
                self._sessions[sess.id] = sess
                self._turns[sess.id] = {}

            for t_dict in raw.get("turns", []):
                turn = Turn(**t_dict)
                if turn.session_id not in self._turns:
                    self._turns[turn.session_id] = {}
                self._turns[turn.session_id][turn.id] = turn

            self._events = raw.get("events", {})
            self._checkpoints = raw.get("checkpoints", {})
            logger.info("Loaded %d sessions, %d turns from disk", len(self._sessions), len(raw.get("turns", [])))
        except Exception as e:
            logger.warning("Could not read state file: %s (initializing fresh)", e)

    def _save_to_disk(self) -> None:
        """Atomically persist current state snapshot to disk."""
        try:
            sessions_data = [s.model_dump(mode="json") for s in self._sessions.values()]
            turns_data = []
            for t_map in self._turns.values():
                for t in t_map.values():
                    turns_data.append(t.model_dump(mode="json"))

            payload = {
                "sessions": sessions_data,
                "turns": turns_data,
                "events": self._events,
                "checkpoints": self._checkpoints,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp_file = self.state_file.with_suffix(".tmp")
            tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp_file.replace(self.state_file)
        except Exception as e:
            logger.warning("Failed to persist state snapshot: %s", e)

    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------
    def create_session(
        self,
        agent_name: str = "cloudpilot-cost-optimizer",
        title: Optional[str] = None,
        subject: Optional[Subject] = None,
    ) -> Session:
        """Create a new conversation session."""
        now = datetime.now(timezone.utc).isoformat()
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        subj = subject or Subject(subject_id="cloudpilot-admin", subject_type="user", subject_slug="cloudpilot-admin")

        session = Session(
            id=session_id,
            agent_name=agent_name,
            title=title or f"Optimization Session {session_id[-6:]}",
            created_by_subject=subj,
            created_at=now,
            updated_at=now,
        )

        with self._lock:
            self._sessions[session_id] = session
            self._turns[session_id] = {}
            self._save_to_disk()

        logger.info("Created session %s for agent %s", session_id, agent_name)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Fetch session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self, agent_name: Optional[str] = None) -> List[Session]:
        """List sessions sorted newest first."""
        with self._lock:
            sessions = list(self._sessions.values())
            if agent_name:
                sessions = [s for s in sessions if s.agent_name == agent_name]
            sessions.sort(key=lambda s: s.created_at, reverse=True)
            return sessions

    def cancel_session(self, session_id: str) -> bool:
        """Cancel the active/running turn for a session."""
        with self._lock:
            turns = self._turns.get(session_id, {})
            cancelled_any = False
            for turn in turns.values():
                if isinstance(turn.state, TurnStateRunning) or (hasattr(turn.state, "status") and turn.state.status == "running"):
                    turn.state = TurnStateCancelled(
                        status="cancelled",
                        reason="client-cancelled",
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                    cancelled_any = True
            if cancelled_any:
                self._save_to_disk()
            return cancelled_any

    # -------------------------------------------------------------------------
    # Turn Management
    # -------------------------------------------------------------------------
    def create_turn(
        self,
        session_id: str,
        input_items: Optional[List[TurnInputItem]] = None,
        previous_turn_id: Optional[str] = "auto",
        subject: Optional[Subject] = None,
    ) -> Turn:
        """Start or chain a new turn within a session."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} does not exist")

        with self._lock:
            existing_turns = self._turns.get(session_id, {})

            # Auto resolve previous_turn_id to the most recent turn in the session
            prev_id: Optional[str] = None
            if previous_turn_id == "auto":
                if existing_turns:
                    sorted_existing = sorted(existing_turns.values(), key=lambda t: t.created_at, reverse=True)
                    prev_id = sorted_existing[0].id
            elif previous_turn_id and previous_turn_id != "none":
                prev_id = previous_turn_id

            turn_id = f"turn-{uuid.uuid4().hex[:12]}"
            turn = Turn(
                id=turn_id,
                session_id=session_id,
                previous_turn_id=prev_id,
                created_by_subject=subject or session.created_by_subject,
                created_at=datetime.now(timezone.utc).isoformat(),
                input=input_items or [],
                state=TurnStateRunning(status="running"),
            )

            existing_turns[turn_id] = turn
            self._turns[session_id] = existing_turns
            self._events[turn_id] = []
            self._save_to_disk()

        logger.info("Created turn %s (chained from %s) in session %s", turn_id, prev_id, session_id)
        return turn

    def get_turn(self, session_id: str, turn_id: str) -> Optional[Turn]:
        """Fetch turn by ID within a session."""
        with self._lock:
            return self._turns.get(session_id, {}).get(turn_id)

    def list_turns(self, session_id: str) -> List[Turn]:
        """List turns for a session (newest-first)."""
        with self._lock:
            turns = list(self._turns.get(session_id, {}).values())
            turns.sort(key=lambda t: t.created_at, reverse=True)
            return turns

    def update_turn_state(self, session_id: str, turn_id: str, new_state: TurnState) -> None:
        """Update turn state to terminal state (done, cancelled, error)."""
        with self._lock:
            turn = self._turns.get(session_id, {}).get(turn_id)
            if turn:
                turn.state = new_state
                self._save_to_disk()
                logger.info("Updated turn %s state to %s", turn_id, getattr(new_state, "status", "unknown"))

    # -------------------------------------------------------------------------
    # Event Stream Logging
    # -------------------------------------------------------------------------
    def record_turn_event(self, turn_id: str, event: Any) -> None:
        """Record an SSE event in the persistent turn event log."""
        with self._lock:
            if turn_id not in self._events:
                self._events[turn_id] = []

            event_dict = event.model_dump(mode="json") if hasattr(event, "model_dump") else event
            self._events[turn_id].append(event_dict)
            self._save_to_disk()

    def list_turn_events(self, turn_id: str) -> List[Dict[str, Any]]:
        """Retrieve full sequence of events emitted during a turn."""
        with self._lock:
            return list(self._events.get(turn_id, []))

    # -------------------------------------------------------------------------
    # Checkpoints & Resumable Interrupts
    # -------------------------------------------------------------------------
    def save_checkpoint(
        self,
        session_id: str,
        turn_id: str,
        execution_plan: ExecutionPlan,
        sandbox_id: str,
        pending_tool_call_ids: List[str],
        context_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Persist execution state when the agent encounters an approval gate.
        Enables resuming the exact plan when a subsequent turn supplies user approval.
        """
        with self._lock:
            self._checkpoints[turn_id] = {
                "session_id": session_id,
                "turn_id": turn_id,
                "execution_plan": execution_plan.model_dump(mode="json"),
                "sandbox_id": sandbox_id,
                "pending_tool_call_ids": pending_tool_call_ids,
                "context_data": context_data or {},
                "paused_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save_to_disk()
        logger.info("Saved approval checkpoint for turn %s (pending tools: %s)", turn_id, pending_tool_call_ids)

    def get_checkpoint(self, turn_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve approval checkpoint for an interrupted turn."""
        with self._lock:
            return self._checkpoints.get(turn_id)

    def find_latest_checkpoint_for_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Find the most recent approval checkpoint across turns in a session."""
        with self._lock:
            matching = [cp for cp in self._checkpoints.values() if cp.get("session_id") == session_id]
            if not matching:
                return None
            matching.sort(key=lambda cp: cp.get("paused_at", ""), reverse=True)
            return matching[0]


# Global singleton instance
_agent_state_manager: Optional[AgentStateManager] = None


def get_agent_state_manager() -> AgentStateManager:
    """Get or create singleton AgentStateManager."""
    global _agent_state_manager
    if _agent_state_manager is None:
        _agent_state_manager = AgentStateManager()
    return _agent_state_manager

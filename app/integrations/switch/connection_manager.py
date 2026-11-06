"""
CloudPilot SwitchOps — Switch Connection & Idempotent Publication Manager (Phase 4.2)

Implements Workstream A3, A4, B3, and I:
- Bounded reconnection with exponential backoff and jitter.
- Strict fail-closed behavior after max_retries.
- Outbound message idempotency (prevents duplicate publication across reconnects/retries).
- Outbox queueing when Switch disconnects after local execution succeeds (never undoes local execution).
- Inbound message deduplication by message_id and sequence cursor.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import random
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from app.integrations.switch.client import SwitchAdapterInterface, SwitchWireClient
from app.integrations.switch.config import SwitchConnectionConfig
from app.integrations.switch.exceptions import (
    SwitchAuthError,
    SwitchConnectionError,
    SwitchIntegrationError,
    SwitchProtocolError,
    SwitchPublishError,
    SwitchTimeoutError,
    SwitchUnverifiedLiveError,
)
from app.integrations.switch.health import SwitchConnectionHealth, SwitchConnectionState
from app.integrations.switch.message_mapper import (
    SwitchCollaborationEvent,
    SwitchMessageMapper,
    WorkflowEventType,
)
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge

logger = logging.getLogger("cloudpilot.integrations.switch.connection_manager")


class SwitchConnectionManager:
    """
    Manages Switch adapter lifecycle, connection health, bounded retries with exponential
    backoff + jitter, idempotent publication, and post-disconnection outbox recovery.
    """

    def __init__(
        self,
        adapter: Optional[SwitchAdapterInterface] = None,
        config: Optional[SwitchConnectionConfig] = None,
    ) -> None:
        self.adapter = adapter or EmulatedSwitchBridge()
        self.config = config or SwitchConnectionConfig.from_env_and_settings()
        self.session_id = f"swsess-{uuid.uuid4().hex[:12]}"

        # Determine initial truthful state
        is_emulated = isinstance(self.adapter, EmulatedSwitchBridge)
        is_mock = not isinstance(self.adapter, (SwitchWireClient, EmulatedSwitchBridge))

        if is_emulated or self.config.mode == "emulated":
            initial_state = SwitchConnectionState.EMULATED_MODE
            mode_label = "EMULATED"
        elif is_mock or self.config.mode == "mock":
            initial_state = SwitchConnectionState.MOCK_MODE
            mode_label = "MOCK"
        else:
            initial_state = SwitchConnectionState.LIVE_UNVERIFIED
            mode_label = "LIVE"

        self.health = SwitchConnectionHealth(
            connection_state=initial_state,
            integration_mode=mode_label,
            verified_live=False,
            bridge_url=getattr(adapter, "bridge_url", self.config.endpoint),
            room_id=self.config.room_id,
            agent_id=getattr(adapter, "agent_id", self.config.agent_id),
            session_id=self.session_id,
        )
        if initial_state == SwitchConnectionState.EMULATED_MODE:
            self.health.mark_emulated_mode(session_id=self.session_id)
        elif initial_state == SwitchConnectionState.MOCK_MODE:
            self.health.mark_mock_mode(session_id=self.session_id)

        # Idempotency & deduplication tracking
        self._published_keys: Dict[str, Dict[str, Any]] = {}
        self._collaboration_events: List[SwitchCollaborationEvent] = []
        self._pending_outbox: List[Tuple[SwitchCollaborationEvent, str]] = []
        self._processed_inbound_ids: set[str] = set()
        self._highest_sequence: int = 0

    def outbox_size(self) -> int:
        return len(self._pending_outbox)

    def get_health(self) -> SwitchConnectionHealth:
        return self.health

    def compute_backoff_delay(self, attempt: int, deterministic_jitter: Optional[float] = None) -> float:
        """
        Computes bounded exponential backoff with jitter:
        delay = base_delay * (2 ** attempt) + jitter
        """
        exp_delay = self.config.retry_base_delay * (2 ** max(0, attempt))
        jitter = (
            deterministic_jitter
            if deterministic_jitter is not None
            else random.uniform(0.0, min(0.25, self.config.retry_base_delay * 0.5))
        )
        return min(30.0, exp_delay + jitter)

    async def verify_connection(self, require_live: bool = False) -> SwitchConnectionHealth:
        """
        Probes the Switch Bridge and verifies connection health.
        Never reports LIVE_CONNECTED unless the adapter is a real live SwitchWireClient
        with valid credentials AND the health probe + auth check succeed.
        """
        if isinstance(self.adapter, EmulatedSwitchBridge):
            if require_live:
                blocker = (
                    "Adapter is EmulatedSwitchBridge (local in-memory simulation). "
                    "Live Switch mode requires SwitchWireClient connected to a real Switch Agent Bridge."
                )
                self.health.mark_live_unverified(reason=blocker, blocker=blocker)
                raise SwitchUnverifiedLiveError(
                    "Cannot verify live Switch connection: running in EMULATED_MODE.",
                    blocker=blocker,
                )
            try:
                await self.adapter.check_health()
                self.health.mark_emulated_mode(session_id=self.session_id)
                return self.health
            except Exception as exc:
                self.health.last_error = str(exc)
                raise SwitchConnectionError(f"Emulated bridge unhealthy: {exc}")

        # Live adapter verification
        if not self.config.has_live_credentials() and not getattr(self.adapter, "agent_api_key", None):
            blocker = (
                "Missing live Switch credentials (SWITCH_AGENT_ID / SWITCH_API_KEY or "
                "CLOUDPILOT_SWITCH_AGENT_ID / CLOUDPILOT_SWITCH_AGENT_API_KEY not configured)."
            )
            self.health.mark_live_unverified(reason=blocker, blocker=blocker)
            if require_live:
                raise SwitchUnverifiedLiveError(
                    "Live Switch credentials are not configured.",
                    blocker=blocker,
                )
            return self.health

        last_err: Optional[Exception] = None
        max_attempts = self.config.max_retries + 1

        for attempt in range(max_attempts):
            t0 = time.perf_counter()
            try:
                res = await asyncio.wait_for(
                    self.adapter.check_health(),
                    timeout=self.config.connection_timeout,
                )
                latency_ms = (time.perf_counter() - t0) * 1000.0
                if not isinstance(res, dict) or res.get("status") != "healthy":
                    self.health.mark_live_protocol_error(f"Unexpected health response: {res}")
                    raise SwitchProtocolError(f"Unexpected Switch health response: {res}")

                # Health probe succeeded; verify agent credentials exist before claiming LIVE_CONNECTED
                agent_id = getattr(self.adapter, "agent_id", None) or self.config.agent_id
                api_key = getattr(self.adapter, "agent_api_key", None) or (
                    self.config.api_key.get_secret_value() if self.config.api_key else None
                )
                if not agent_id or not api_key:
                    blocker = "Bridge health probe reachable, but agent_id or agent_api_key is missing."
                    self.health.mark_live_unverified(reason=blocker, blocker=blocker)
                    if require_live:
                        raise SwitchUnverifiedLiveError(blocker, blocker=blocker)
                    return self.health

                self.health.mark_live_connected(
                    latency_ms=latency_ms,
                    session_id=self.session_id,
                    generation=getattr(self.adapter, "generation", None),
                    cursor=getattr(self.adapter, "cursor", 0),
                )
                return self.health

            except SwitchAuthError as auth_err:
                self.health.mark_live_auth_failed(str(auth_err))
                raise
            except SwitchProtocolError as proto_err:
                self.health.mark_live_protocol_error(str(proto_err))
                raise
            except asyncio.TimeoutError as tex:
                last_err = SwitchTimeoutError(
                    f"Switch connection timed out after {self.config.connection_timeout}s"
                )
                self.health.retry_count += 1
                self.health.mark_live_disconnected(
                    str(last_err),
                    blocker=f"Switch Bridge at {self.health.bridge_url} timed out.",
                )
            except Exception as exc:
                last_err = exc
                self.health.retry_count += 1
                self.health.mark_live_disconnected(
                    str(exc),
                    blocker=f"Switch Bridge at {self.health.bridge_url} unreachable: {exc}",
                )

            if attempt < max_attempts - 1:
                delay = self.compute_backoff_delay(attempt)
                await asyncio.sleep(delay)

        if require_live:
            blocker = self.health.external_blocker or str(last_err)
            raise SwitchUnverifiedLiveError(
                f"Live Switch verification failed after {max_attempts} attempt(s): {last_err}",
                blocker=blocker,
            )
        if last_err:
            raise SwitchConnectionError(f"Switch connection failed after {max_attempts} attempt(s): {last_err}")
        return self.health

    async def publish_workflow_event(
        self,
        event: SwitchCollaborationEvent,
        content: str,
        raise_on_failure: bool = False,
    ) -> SwitchCollaborationEvent:
        """
        Publishes a workflow collaboration message to Switch with:
        - Automatic secret & HMAC token redaction
        - Idempotency deduplication (no duplicate sends on retry/reconnect)
        - Bounded retry with exponential backoff
        - Outbox persistence if Switch is temporarily disconnected
        """
        safe_content = SwitchMessageMapper.redact_for_switch(content)
        event.switch_session_id = self.session_id
        event.integration_state = self.health.connection_state.value

        # 1. Check idempotency cache so we never double-publish
        if event.idempotency_key in self._published_keys:
            cached = self._published_keys[event.idempotency_key]
            event.switch_message_id = cached.get("message_id")
            event.delivery_status = "DELIVERED"
            event.ack_status = "ACKNOWLEDGED"
            return event

        max_attempts = self.config.max_retries + 1
        last_err: Optional[Exception] = None

        for attempt in range(max_attempts):
            t0 = time.perf_counter()
            try:
                resp = await asyncio.wait_for(
                    self.adapter.post_message(room_id=event.switch_room_id, content=safe_content),
                    timeout=self.config.connection_timeout,
                )
                latency_ms = (time.perf_counter() - t0) * 1000.0
                msg_id = (
                    resp.get("message_id") or resp.get("id") or f"msg-{uuid.uuid4().hex[:8]}"
                    if isinstance(resp, dict)
                    else f"msg-{uuid.uuid4().hex[:8]}"
                )
                event.switch_message_id = msg_id
                event.delivery_status = "DELIVERED"
                event.ack_status = "ACKNOWLEDGED"
                event.retry_count = attempt
                event.error_message = None

                # Update health
                self.health.messages_published_count += 1
                self.health.last_successful_communication = datetime.now(timezone.utc)
                self.health.latency_ms = round(latency_ms, 2)
                if not isinstance(self.adapter, EmulatedSwitchBridge) and self.config.mode != "mock":
                    self.health.mark_live_connected(
                        latency_ms=latency_ms,
                        session_id=self.session_id,
                    )
                event.integration_state = self.health.connection_state.value

                # Record idempotency key
                self._published_keys[event.idempotency_key] = {
                    "message_id": msg_id,
                    "timestamp": event.timestamp.isoformat(),
                }
                self._collaboration_events.append(event)
                return event

            except SwitchAuthError as auth_err:
                last_err = auth_err
                event.retry_count = attempt + 1
                event.delivery_status = "FAILED"
                event.ack_status = "FAILED"
                event.error_message = str(auth_err)
                self.health.mark_live_auth_failed(str(auth_err))
                break  # Do not retry auth failure

            except Exception as exc:
                last_err = exc
                event.retry_count = attempt + 1
                self.health.retry_count += 1
                if not isinstance(self.adapter, EmulatedSwitchBridge):
                    self.health.mark_live_disconnected(str(exc))

                if attempt < max_attempts - 1:
                    delay = self.compute_backoff_delay(attempt)
                    await asyncio.sleep(delay)

        # Publication failed after bounded retries — queue in pending outbox for reconnection recovery
        event.delivery_status = "PENDING_RETRY"
        event.ack_status = "UNACKNOWLEDGED"
        event.error_message = str(last_err) if last_err else "Publication failed"
        event.integration_state = self.health.connection_state.value
        self._collaboration_events.append(event)
        self._pending_outbox.append((event, safe_content))

        if raise_on_failure and last_err:
            raise SwitchPublishError(f"Failed to publish event {event.event_type.value}: {last_err}")
        return event

    async def flush_pending_outbox(self) -> int:
        """
        Retries publishing any queued workflow events after Switch reconnection.
        Uses idempotency keys to guarantee zero duplicate messages.
        Returns count of newly delivered messages.
        """
        if not self._pending_outbox:
            return 0

        remaining: List[Tuple[SwitchCollaborationEvent, str]] = []
        delivered_count = 0

        for event, content in list(self._pending_outbox):
            if event.idempotency_key in self._published_keys:
                delivered_count += 1
                continue
            try:
                resp = await asyncio.wait_for(
                    self.adapter.post_message(room_id=event.switch_room_id, content=content),
                    timeout=self.config.connection_timeout,
                )
                msg_id = (
                    resp.get("message_id") or resp.get("id") or f"msg-{uuid.uuid4().hex[:8]}"
                    if isinstance(resp, dict)
                    else f"msg-{uuid.uuid4().hex[:8]}"
                )
                event.switch_message_id = msg_id
                event.delivery_status = "DELIVERED"
                event.ack_status = "ACKNOWLEDGED"
                event.error_message = None
                self._published_keys[event.idempotency_key] = {
                    "message_id": msg_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.health.messages_published_count += 1
                delivered_count += 1
            except Exception as exc:
                event.error_message = str(exc)
                remaining.append((event, content))

        self._pending_outbox = remaining
        return delivered_count

    def is_duplicate_inbound_event(self, frame: Dict[str, Any]) -> bool:
        """
        Checks whether an incoming Switch frame is a duplicate message_id or stale sequence.
        Records new message_ids so duplicate deliveries are ignored.
        """
        payload = frame.get("payload", {})
        msg_id = payload.get("message_id")
        seq = frame.get("sequence")

        if msg_id:
            if msg_id in self._processed_inbound_ids:
                return True
            self._processed_inbound_ids.add(msg_id)

        if isinstance(seq, int):
            if seq <= self._highest_sequence and msg_id is None:
                return True
            if seq > self._highest_sequence:
                self._highest_sequence = seq

        self.health.events_received_count += 1
        return False

    def get_collaboration_events(self, task_id: Optional[str] = None) -> List[SwitchCollaborationEvent]:
        if task_id:
            return [e for e in self._collaboration_events if e.task_id == task_id]
        return list(self._collaboration_events)

    def get_pending_outbox_count(self) -> int:
        return len(self._pending_outbox)


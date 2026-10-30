"""
CloudPilot SwitchOps — Emulated Switch Agent Bridge & Wire Contract Mock

Provides a fully compliant in-memory simulation of the Switch Agent Bridge wire contract.
Enables deterministic local testing, contract verification, and standalone development
without requiring an external Docker container or live Switch server.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.core.errors import (
    SwitchAuthError,
    SwitchConnectionError,
    SwitchIntegrationError,
)
from app.integrations.switch.client import SwitchAdapterInterface

logger = logging.getLogger("cloudpilot.integrations.switch.mock")


class EmulatedSwitchBridge(SwitchAdapterInterface):
    """
    In-memory simulation of Switch Agent Bridge implementing the exact wire protocol:
    - Maintains agent registry and registration keys
    - Maintains room message history
    - Simulates WebSocket streaming, pings (every 2s), and cursor checks
    """

    def __init__(self, bootstrap_key: str = "switch-test-bootstrap-key") -> None:
        self.bootstrap_key = bootstrap_key
        self.agents: dict[str, dict[str, Any]] = {}
        self.rooms: dict[str, list[dict[str, Any]]] = {}
        self.active_connections: dict[str, dict[str, Any]] = {}
        self.is_healthy: bool = True
        self.sequence: int = 100
        self._event_queues: dict[str, asyncio.Queue] = {}
        self._running: bool = False

    async def check_health(self) -> dict[str, Any]:
        if not self.is_healthy:
            raise SwitchConnectionError("Emulated Switch bridge is set to unhealthy state.")
        return {"status": "healthy", "bridge_url": "mock://switch-bridge"}

    async def register_agent(
        self,
        name: str,
        description: str,
        registration_key: str,
        connector_type: str = "custom",
    ) -> dict[str, str]:
        if registration_key != self.bootstrap_key:
            raise SwitchAuthError("Unauthorized registration token.")

        for data in self.agents.values():
            if data["name"] == name:
                raise SwitchIntegrationError(f"Agent '{name}' already exists.", status_code=409)

        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        api_key = f"swak-{uuid.uuid4().hex[:24]}"

        self.agents[agent_id] = {
            "id": agent_id,
            "name": name,
            "description": description,
            "connector_type": connector_type,
            "api_key": api_key,
            "addressing": "owner_only",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"id": agent_id, "api_key": api_key}

    async def update_addressing(self, agent_id: str, addressing: str) -> dict[str, Any]:
        if agent_id not in self.agents:
            raise SwitchIntegrationError("Agent not found", status_code=404)
        self.agents[agent_id]["addressing"] = addressing
        return {"status": "updated", "addressing": addressing}

    async def post_message(self, room_id: str, content: str) -> dict[str, Any]:
        if room_id not in self.rooms:
            self.rooms[room_id] = []

        message_id = f"msg-{uuid.uuid4().hex[:8]}"
        msg_record = {
            "message_id": message_id,
            "room_id": room_id,
            "sender": "@cloudpilot-ops-agent:switch",
            "sender_name": "CloudPilot Ops Agent",
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.rooms[room_id].append(msg_record)
        return {"message_id": message_id, "status": "sent"}

    def get_room_messages(self, room_id: str) -> list[dict[str, Any]]:
        """Inspection helper for test assertions."""
        return list(self.rooms.get(room_id, []))

    async def inject_human_message(
        self,
        room_id: str,
        text: str,
        sender: str = "@operator:switch",
        sender_name: str = "Human Operator",
    ) -> dict[str, Any]:
        """
        Simulate a human typing a message into the Switch room.
        Dispatches to active WebSocket queues if addressed to CloudPilot.
        """
        self.sequence += 1
        is_addressed = "@cloudpilot" in text.lower() or "@cloudpilot-ops" in text.lower()

        event_payload = {
            "type": "event",
            "sequence": self.sequence,
            "event": "message",
            "payload": {
                "addressed": is_addressed,
                "sender": sender,
                "sender_name": sender_name,
                "message_id": f"msg-{uuid.uuid4().hex[:8]}",
                "body": text,
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                "thread_id": None,
                "attachments": [],
            },
        }

        if room_id not in self.rooms:
            self.rooms[room_id] = []
        self.rooms[room_id].append({
            "message_id": event_payload["payload"]["message_id"],
            "room_id": room_id,
            "sender": sender,
            "sender_name": sender_name,
            "content": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if room_id in self._event_queues:
            await self._event_queues[room_id].put(event_payload)

        return event_payload

    async def listen_events(
        self,
        room_id: str,
        on_event: Callable[[dict[str, Any]], Any],
    ) -> None:
        """Emulate the persistent WebSocket connection with pings and events."""
        q: asyncio.Queue = asyncio.Queue()
        self._event_queues[room_id] = q
        self._running = True

        # Send connection_state frame
        conn_state = {
            "type": "connection_state",
            "connection_id": str(uuid.uuid4()),
            "generation": "gen-1",
            "cursor": self.sequence,
            "rooms": [room_id],
        }
        res = on_event(conn_state)
        if asyncio.iscoroutine(res):
            await res

        while self._running:
            try:
                # Wait for next event or inject ping
                try:
                    frame = await asyncio.wait_for(q.get(), timeout=1.0)
                    res = on_event(frame)
                    if asyncio.iscoroutine(res):
                        await res
                except asyncio.TimeoutError:
                    # Emulate server ping every 1-2s
                    ping_frame = {"type": "ping"}
                    res = on_event(ping_frame)
                    if asyncio.iscoroutine(res):
                        await res
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("Error in mock listen_events: %s", err)
                break

    def stop(self) -> None:
        self._running = False

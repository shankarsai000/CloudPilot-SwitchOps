"""
CloudPilot SwitchOps — Switch Agent Bridge Integration Interface & Wire Client

Implements the official Switch Agent Protocol (wire contract):
- Health probe (`GET /health`)
- Out-of-band registration (`POST /agents`)
- Addressing rule updates (`POST /agents/{agent_id}/ops/update_agent_detail`)
- Room outbound messaging (`POST /agents/{agent_id}/message`)
- Bidirectional WebSocket streaming (`GET /agents/{agent_id}/connection/ws`) with:
    * Immediate heartbeat/pong responses (`{"type": "pong", "cursor": <cursor>}`)
    * Addressed message filtering
    * Reconnection with generation & cursor fencing
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import httpx

try:
    import websockets
except ImportError:
    websockets = None

from app.core.errors import (
    SwitchAuthError,
    SwitchConnectionError,
    SwitchIntegrationError,
)

logger = logging.getLogger("cloudpilot.integrations.switch")


class SwitchAdapterInterface(ABC):
    """Abstract interface decoupling CloudPilot domain from Switch transport details."""

    @abstractmethod
    async def check_health(self) -> dict[str, Any]:
        """Verify reachability of Switch Bridge."""

    @abstractmethod
    async def register_agent(
        self,
        name: str,
        description: str,
        registration_key: str,
        connector_type: str = "custom",
    ) -> dict[str, str]:
        """Register agent with Switch and return {'id': ..., 'api_key': ...}."""

    @abstractmethod
    async def post_message(self, room_id: str, content: str) -> dict[str, Any]:
        """Post a message to a Switch room."""

    @abstractmethod
    async def listen_events(
        self,
        room_id: str,
        on_event: Callable[[dict[str, Any]], Any],
    ) -> None:
        """Stream room events and handle pings."""


class SwitchWireClient(SwitchAdapterInterface):
    """
    Official Switch wire-protocol client adhering strictly to Switch documentation.
    """

    def __init__(
        self,
        bridge_url: str = "http://localhost:8080",
        agent_id: str | None = None,
        agent_api_key: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self.agent_id = agent_id
        self.agent_api_key = agent_api_key
        self.timeout = timeout_seconds
        self.connection_id = str(uuid.uuid4())
        self.cursor: int = 0
        self.generation: str | None = None
        self._running = False

    def _get_auth_headers(self) -> dict[str, str]:
        if not self.agent_api_key:
            raise SwitchAuthError("Agent API key is not configured.")
        return {
            "Authorization": f"Bearer {self.agent_api_key}",
            "Content-Type": "application/json",
        }

    async def check_health(self) -> dict[str, Any]:
        """
        Probe bridge health via public GET /health.
        Does not require authentication.
        """
        url = f"{self.bridge_url}/health"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return {"status": "healthy", "bridge_url": self.bridge_url}
                if resp.status_code == 401:
                    raise SwitchConnectionError(
                        f"Bridge endpoint '{url}' returned 401. This URL points to Gateway or a protected host, not the bridge base URL."
                    )
                raise SwitchConnectionError(
                    f"Bridge health probe failed with status {resp.status_code}: {resp.text}"
                )
        except httpx.RequestError as exc:
            raise SwitchConnectionError(
                f"Failed to reach Switch Bridge at {url}: {exc!s}"
            )

    async def register_agent(
        self,
        name: str,
        description: str,
        registration_key: str,
        connector_type: str = "custom",
    ) -> dict[str, str]:
        """
        Out-of-band agent registration: POST /agents
        """
        url = f"{self.bridge_url}/agents"
        headers = {
            "Authorization": f"Bearer {registration_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "name": name,
            "description": description,
            "connector_type": connector_type,
            "integration_profile": {
                "connection_model": "always_on",
                "message_exchange": True,
                "pre_invocation_mediation": [],
                "post_invocation_mediation": [],
                "event_reporting": [],
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    self.agent_id = data["id"]
                    self.agent_api_key = data["api_key"]
                    return {"id": data["id"], "api_key": data["api_key"]}
                if resp.status_code == 401:
                    raise SwitchAuthError("Invalid registration token provided to Switch Bridge.")
                if resp.status_code == 409:
                    raise SwitchIntegrationError(
                        f"Agent with name '{name}' already exists in Switch.",
                        status_code=409,
                    )
                raise SwitchIntegrationError(
                    f"Agent registration failed ({resp.status_code}): {resp.text}",
                    status_code=resp.status_code,
                )
        except httpx.RequestError as exc:
            raise SwitchConnectionError(f"Connection error during agent registration: {exc!s}")

    async def update_addressing(self, addressing: str = "owner_and_owner_agents") -> dict[str, Any]:
        """
        Update addressing permission so participants can instruct the agent.
        POST /agents/{agent_id}/ops/update_agent_detail
        """
        if not self.agent_id:
            raise SwitchIntegrationError("Agent ID is required before updating detail.")
        url = f"{self.bridge_url}/agents/{self.agent_id}/ops/update_agent_detail"
        payload = {
            "agent_id": self.agent_id,
            "addressing": addressing,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=self._get_auth_headers())
            if resp.status_code == 200:
                return resp.json()
            raise SwitchIntegrationError(
                f"Failed to update addressing ({resp.status_code}): {resp.text}",
                status_code=resp.status_code,
            )

    async def post_message(self, room_id: str, content: str) -> dict[str, Any]:
        """
        Send an outbound message to a Switch room:
        POST /agents/{agent_id}/message with {room_id, content}
        Does not require an active WebSocket connection.
        """
        if not self.agent_id:
            raise SwitchIntegrationError("Cannot post message: agent_id is not set.")

        url = f"{self.bridge_url}/agents/{self.agent_id}/message"
        payload = {
            "room_id": room_id,
            "content": content,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=self._get_auth_headers())
                if resp.status_code in (200, 201):
                    return resp.json()
                if resp.status_code == 401:
                    raise SwitchAuthError("Agent API key unauthorized on Switch Bridge.")
                raise SwitchIntegrationError(
                    f"Failed to post message to Switch room '{room_id}' ({resp.status_code}): {resp.text}",
                    status_code=resp.status_code,
                )
        except httpx.RequestError as exc:
            raise SwitchConnectionError(f"Network error posting to Switch room: {exc!s}")

    async def listen_events(
        self,
        room_id: str,
        on_event: Callable[[dict[str, Any]], Any],
    ) -> None:
        """
        Maintain persistent WebSocket connection to Switch Agent Bridge.
        Responds to pings within 2s with {"type": "pong", "cursor": cursor}.
        Dispatches addressed messages to on_event callback.
        """
        if websockets is None:
            raise SwitchIntegrationError("websockets library is not available.")
        if not self.agent_id or not self.agent_api_key:
            raise SwitchAuthError("Cannot open WebSocket: agent_id or agent_api_key missing.")

        ws_scheme = "wss" if self.bridge_url.startswith("https") else "ws"
        host_and_port = self.bridge_url.split("://", 1)[-1]
        ws_url = (
            f"{ws_scheme}://{host_and_port}/agents/{self.agent_id}/connection/ws"
            f"?connection_id={self.connection_id}&rooms={room_id}&filter=addressed&scope=single"
        )
        if self.cursor > 0:
            ws_url += f"&start_from={self.cursor}"
        if self.generation:
            ws_url += f"&expected_generation={self.generation}"

        headers = {"Authorization": f"Bearer {self.agent_api_key}"}
        self._running = True

        logger.info("Connecting to Switch WebSocket: %s (room: %s)", ws_url, room_id)
        try:
            # Modern websockets (v14+) uses additional_headers, older versions use extra_headers
            connect_kwargs: dict[str, Any] = {}
            import inspect
            sig = inspect.signature(websockets.connect)
            if "additional_headers" in sig.parameters:
                connect_kwargs["additional_headers"] = headers
            elif "extra_headers" in sig.parameters:
                connect_kwargs["extra_headers"] = headers

            async with websockets.connect(ws_url, **connect_kwargs) as ws:
                async for raw_message in ws:
                    if not self._running:
                        break
                    frame = json.loads(raw_message)
                    frame_type = frame.get("type")

                    if frame_type == "connection_state":
                        self.generation = frame.get("generation")
                        self.cursor = frame.get("cursor", self.cursor)
                        logger.info("Switch connection established: generation=%s", self.generation)

                    elif frame_type == "ping":
                        # CRITICAL: Liveness protocol requires immediate pong reply with cursor
                        pong_frame = {"type": "pong", "cursor": self.cursor}
                        await ws.send(json.dumps(pong_frame))

                    elif frame_type == "event":
                        seq = frame.get("sequence", self.cursor)
                        if isinstance(seq, int) and seq > self.cursor:
                            self.cursor = seq

                        event_kind = frame.get("event")
                        payload = frame.get("payload", {})
                        if event_kind == "message" and payload.get("addressed", False):
                            try:
                                res = on_event(frame)
                                if asyncio.iscoroutine(res):
                                    await res
                            except Exception as err:
                                logger.exception("Error in Switch event handler: %s", err)

                    elif frame_type == "evicted":
                        code = frame.get("code")
                        logger.warning("Evicted from Switch Bridge: code=%s", code)
                        self._running = False
                        break

        except Exception as exc:
            self._running = False
            raise SwitchConnectionError(f"Switch WebSocket connection failure: {exc!s}")

    def stop(self) -> None:
        """Signal listener loop to stop."""
        self._running = False

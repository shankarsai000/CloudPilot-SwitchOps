"""
CloudPilot SwitchOps — Wire Contract Test: Real WebSocket Transport, Pings & Frames
"""

import asyncio
import json
import socket
from datetime import datetime, timezone
from typing import Any

import pytest
import websockets

from app.integrations.switch.client import SwitchWireClient


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_real_websocket_wire_protocol_exchange() -> None:
    """
    Spins up a lightweight in-process WebSocket server speaking the exact
    Switch wire protocol. Verifies that SwitchWireClient:
    1. Authenticates with Bearer token.
    2. Receives connection_state frame and saves generation.
    3. Receives ping frame and sends pong with cursor within 2 seconds.
    4. Receives event frame and dispatches to handler.
    """
    port = get_free_port()
    received_pongs: list[dict[str, Any]] = []
    received_auth_headers: list[str] = []

    async def mock_switch_server_handler(websocket):
        # Extract headers
        for k, v in websocket.request.headers.items():
            if k.lower() == "authorization":
                received_auth_headers.append(v)

        # 1. Send connection_state frame
        conn_state = {
            "type": "connection_state",
            "connection_id": "conn-123",
            "agent_id": "agent-test",
            "generation": "gen-alpha-1",
            "cursor": 42,
            "rooms": ["cloudpilot-ops"],
        }
        await websocket.send(json.dumps(conn_state))

        # 2. Send ping frame
        await asyncio.sleep(0.05)
        await websocket.send(json.dumps({"type": "ping"}))

        # 3. Read pong from client
        msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
        pong_data = json.loads(msg)
        received_pongs.append(pong_data)

        # 4. Send addressed message event
        msg_event = {
            "type": "event",
            "sequence": 43,
            "event": "message",
            "rooms": ["cloudpilot-ops"],
            "payload": {
                "addressed": True,
                "sender": "@lead:switch",
                "sender_name": "Lead Architect",
                "message_id": "msg-999",
                "body": "@CloudPilot review the staging infrastructure",
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            },
        }
        await websocket.send(json.dumps(msg_event))
        await asyncio.sleep(0.1)

    # Start mock server
    server = await websockets.serve(mock_switch_server_handler, "127.0.0.1", port)

    dispatched_events: list[dict[str, Any]] = []

    client = SwitchWireClient(
        bridge_url=f"http://127.0.0.1:{port}",
        agent_id="agent-test",
        agent_api_key="swak-secret-token-xyz",
    )

    async def on_event(frame: dict[str, Any]) -> None:
        dispatched_events.append(frame)
        # Stop client once event is received
        client.stop()

    try:
        # Run listen_events with a timeout
        await asyncio.wait_for(
            client.listen_events(room_id="cloudpilot-ops", on_event=on_event),
            timeout=3.0,
        )
    except asyncio.TimeoutError:
        pass
    finally:
        client.stop()
        server.close()
        await server.wait_closed()

    # Assertions on wire contract
    assert len(received_auth_headers) == 1
    assert received_auth_headers[0] == "Bearer swak-secret-token-xyz"
    assert len(received_pongs) >= 1
    assert received_pongs[0]["type"] == "pong"
    assert received_pongs[0]["cursor"] == 42
    assert client.generation == "gen-alpha-1"
    assert len(dispatched_events) == 1
    assert dispatched_events[0]["payload"]["body"] == "@CloudPilot review the staging infrastructure"

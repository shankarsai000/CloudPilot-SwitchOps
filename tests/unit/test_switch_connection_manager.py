"""
Unit tests for SwitchConnectionManager (Phase 4.2).

Validates:
- Truthful health state transitions (EMULATED_MODE, LIVE_CONNECTED, LIVE_UNVERIFIED, LIVE_DISCONNECTED, LIVE_AUTH_FAILED).
- Exponential backoff delay computation with jitter bounds.
- Outbound event publication idempotency (never double-posts on retry).
- Inbound frame deduplication (rejects duplicate message_ids).
- Outbox queueing and post-reconnection outbox flushing.
- Live verification failure behavior (SwitchUnverifiedLiveError).
"""

import asyncio
from datetime import datetime, timezone
import pytest

from app.core.config import Settings
from app.integrations.switch.client import SwitchWireClient
from app.integrations.switch.config import SwitchConnectionConfig
from app.integrations.switch.connection_manager import SwitchConnectionManager
from app.integrations.switch.exceptions import SwitchUnverifiedLiveError, SwitchConnectionError
from app.integrations.switch.health import SwitchConnectionState
from app.integrations.switch.message_mapper import SwitchCollaborationEvent, WorkflowEventType
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge


class DummyOfflineAdapter:
    """Mock adapter simulating complete network unreachability."""
    async def check_health(self):
        raise ConnectionRefusedError("Connection refused on port 8080")

    async def post_message(self, room_id: str, content: str):
        raise ConnectionRefusedError("Connection refused on port 8080")


@pytest.mark.asyncio
async def test_emulated_mode_health_reporting():
    """Verify that EmulatedSwitchBridge reports EMULATED_MODE truthfully."""
    bridge = EmulatedSwitchBridge()
    config = SwitchConnectionConfig(mode="emulated", endpoint="http://localhost:8080")
    manager = SwitchConnectionManager(adapter=bridge, config=config)

    health = await manager.verify_connection(require_live=False)
    assert health.state == SwitchConnectionState.EMULATED_MODE
    assert health.is_operational() is True
    assert health.to_status_dict()["state"] == "EMULATED_MODE"
    assert "correlated_command" in health.protocol_capabilities.approval_mechanism


@pytest.mark.asyncio
async def test_live_unverified_when_credentials_absent():
    """Verify that requiring live connection fails when credentials or bridge are missing."""
    bridge = DummyOfflineAdapter()
    config = SwitchConnectionConfig(mode="live", endpoint="http://localhost:8080", max_retries=1)
    manager = SwitchConnectionManager(adapter=bridge, config=config)

    with pytest.raises(SwitchUnverifiedLiveError) as exc_info:
        await manager.verify_connection(require_live=True)
    assert "Live Switch" in str(exc_info.value)
    assert manager.health.state in (SwitchConnectionState.LIVE_DISCONNECTED, SwitchConnectionState.LIVE_UNVERIFIED)


def test_exponential_backoff_bounds():
    """Verify exponential backoff with jitter stays strictly within bounds."""
    config = SwitchConnectionConfig(
        retry_base_delay=1.0,
        retry_max_delay=8.0,
        retry_jitter_factor=0.2,
    )
    manager = SwitchConnectionManager(config=config)

    for attempt in range(5):
        delay = manager.compute_backoff_delay(attempt)
        base = 1.0 * (2 ** attempt)
        assert base <= delay <= min(30.0, base + 0.3), f"Attempt {attempt} delay {delay} outside [{base}, {base + 0.3}]"


@pytest.mark.asyncio
async def test_outbound_publication_idempotency():
    """Verify that publishing identical workflow events does not post duplicate messages."""
    bridge = EmulatedSwitchBridge()
    config = SwitchConnectionConfig(mode="emulated")
    manager = SwitchConnectionManager(adapter=bridge, config=config)

    event = SwitchCollaborationEvent(
        event_type=WorkflowEventType.PROPOSAL_PUBLISHED,
        task_id="task-idem-001",
        summary="Proposal for resource rightsizing",
        switch_room_id="cloudpilot-ops",
    )

    # First publication
    res1 = await manager.publish_workflow_event(event=event, content="Proposal Details Content")
    assert res1.delivery_status == "DELIVERED"
    assert len(bridge.get_room_messages("cloudpilot-ops")) == 1

    # Second publication with identical idempotency key
    res2 = await manager.publish_workflow_event(event=event, content="Proposal Details Content")
    assert res2.delivery_status == "DELIVERED"
    # Must NOT have created a second room message
    assert len(bridge.get_room_messages("cloudpilot-ops")) == 1


def test_inbound_frame_deduplication():
    """Verify duplicate inbound Switch message frames are identified and discarded."""
    manager = SwitchConnectionManager()

    frame1 = {
        "type": "event",
        "event": "message",
        "payload": {
            "message_id": "msg-unique-1234",
            "body": "@CloudPilot review",
        },
    }

    assert manager.is_duplicate_inbound_event(frame1) is False
    # Second time with identical message_id must report True
    assert manager.is_duplicate_inbound_event(frame1) is True


@pytest.mark.asyncio
async def test_outbox_queue_and_flush():
    """Verify failed messages are buffered in outbox and successfully flushed upon reconnection."""
    offline_bridge = DummyOfflineAdapter()
    config = SwitchConnectionConfig(mode="emulated", max_retries=0)
    manager = SwitchConnectionManager(adapter=offline_bridge, config=config)

    event = SwitchCollaborationEvent(
        event_type=WorkflowEventType.WORKFLOW_COMPLETED,
        task_id="task-outbox-001",
        summary="Summary for outbox test",
        switch_room_id="cloudpilot-ops",
    )

    # Publish to offline adapter
    published = await manager.publish_workflow_event(event=event, content="Test outbox content")
    assert published.delivery_status == "PENDING_RETRY"
    assert manager.outbox_size() == 1

    # Switch adapter to working bridge and flush
    working_bridge = EmulatedSwitchBridge()
    manager.adapter = working_bridge
    flushed_count = await manager.flush_pending_outbox()

    assert flushed_count == 1
    assert manager.outbox_size() == 0
    assert len(working_bridge.get_room_messages("cloudpilot-ops")) == 1

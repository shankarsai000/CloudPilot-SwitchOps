"""
CloudPilot SwitchOps — Contract Tests: Switch Wire Protocol & Message Handling
"""

import pytest

from app.core.errors import SwitchAuthError
from app.domain.models import TaskStatus
from app.integrations.switch.mock_bridge import EmulatedSwitchBridge
from app.persistence.repository import InMemoryTaskRepository
from app.services.task_service import TaskService


class TestSwitchProtocolContracts:
    """Validate protocol frames, registration schemas, and error behavior."""

    @pytest.mark.asyncio
    async def test_agent_registration_contract(self) -> None:
        bridge = EmulatedSwitchBridge(bootstrap_key="valid-bootstrap-token")

        # Invalid token rejected
        with pytest.raises(SwitchAuthError):
            await bridge.register_agent(
                name="cloudpilot-agent",
                description="CloudPilot Ops Agent",
                registration_key="wrong-token",
            )

        # Valid registration returns id and api_key
        res = await bridge.register_agent(
            name="cloudpilot-agent",
            description="CloudPilot Ops Agent",
            registration_key="valid-bootstrap-token",
        )
        assert "id" in res
        assert "api_key" in res
        assert res["id"].startswith("agent-")
        assert res["api_key"].startswith("swak-")

    @pytest.mark.asyncio
    async def test_addressing_rule_update(self) -> None:
        bridge = EmulatedSwitchBridge(bootstrap_key="token")
        reg = await bridge.register_agent("cloudpilot-agent", "desc", "token")
        agent_id = reg["id"]

        update_res = await bridge.update_addressing(agent_id, "owner_and_owner_agents")
        assert update_res["status"] == "updated"
        assert update_res["addressing"] == "owner_and_owner_agents"

    @pytest.mark.asyncio
    async def test_outbound_room_message_contract(self) -> None:
        bridge = EmulatedSwitchBridge()
        msg_resp = await bridge.post_message(
            room_id="cloudpilot-ops",
            content="Hello from CloudPilot Ops Agent!",
        )
        assert msg_resp["status"] == "sent"
        assert "message_id" in msg_resp

        messages = bridge.get_room_messages("cloudpilot-ops")
        assert len(messages) == 1
        assert messages[0]["content"] == "Hello from CloudPilot Ops Agent!"

    @pytest.mark.asyncio
    async def test_unaddressed_message_ignored(self) -> None:
        repo = InMemoryTaskRepository()
        bridge = EmulatedSwitchBridge()
        service = TaskService(repository=repo, switch_adapter=bridge)

        # Frame where addressed is False
        frame = {
            "type": "event",
            "event": "message",
            "rooms": ["cloudpilot-ops"],
            "payload": {
                "addressed": False,
                "sender": "@user:switch",
                "body": "General conversation between teammates.",
            },
        }
        task = await service.handle_switch_event(frame)
        assert task is None
        assert len(repo.list_tasks()) == 0

    @pytest.mark.asyncio
    async def test_non_message_event_ignored(self) -> None:
        repo = InMemoryTaskRepository()
        bridge = EmulatedSwitchBridge()
        service = TaskService(repository=repo, switch_adapter=bridge)

        # Frame for room_join or presence
        frame = {
            "type": "event",
            "event": "room_join",
            "rooms": ["cloudpilot-ops"],
            "payload": {"member": "@user:switch"},
        }
        task = await service.handle_switch_event(frame)
        assert task is None

    @pytest.mark.asyncio
    async def test_full_human_agent_workflow(self) -> None:
        """
        Exercise the full human-agent interaction through the Switch room:
        Human sends: '@CloudPilot review the staging infrastructure for a cost and security assessment. Do not modify any files or infrastructure.'
        Agent receives, acknowledges, records lifecycle events, reports status, and completes.
        """
        repo = InMemoryTaskRepository()
        bridge = EmulatedSwitchBridge()
        service = TaskService(repository=repo, switch_adapter=bridge)

        prompt_text = (
            "@CloudPilot review the staging infrastructure for a cost and security assessment. "
            "Do not modify any files or infrastructure."
        )

        # Human sends message into room
        human_event = await bridge.inject_human_message(
            room_id="cloudpilot-ops",
            text=prompt_text,
            sender="@platform-engineer:switch",
            sender_name="Platform Engineer",
        )

        # Service handles event
        task = await service.handle_switch_event(human_event)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED

        # Check room history
        room_msgs = bridge.get_room_messages("cloudpilot-ops")
        # 1 human message + 1 acknowledgment + 1 completion report = 3 messages
        assert len(room_msgs) == 3
        assert room_msgs[0]["content"] == prompt_text
        assert "Acknowledged request" in room_msgs[1]["content"]
        assert "Task Execution Report" in room_msgs[2]["content"]

        # Check append-only event trail
        events = repo.get_events_for_task(task.task_id)
        assert len(events) == 4
        assert [e.event_type.value for e in events] == [
            "TASK_RECEIVED",
            "TASK_ACKNOWLEDGED",
            "TASK_STARTED",
            "TASK_COMPLETED",
        ]

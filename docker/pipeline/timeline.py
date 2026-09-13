"""
Event-Driven Execution Timeline & Auditing Recorder.
Integrates with the platform EventBus to emit auditable lifecycle events.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.models import TimelineEvent
from core.events.bus import get_event_bus
from core.events.models import BaseEvent, EventType

logger = logging.getLogger("cloudpilot.pipeline.timeline")


class TimelineRecorder:
    """
    Records microsecond-precision auditable events during pipeline execution.
    Publishes corresponding events to the centralized platform EventBus.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._events: List[TimelineEvent] = []

    @property
    def events(self) -> List[TimelineEvent]:
        return list(self._events)

    def record(
        self,
        agent_name: str,
        action: str,
        status: str = "INFO",
        stage_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> TimelineEvent:
        """
        Record an auditable timeline event and publish to the EventBus.
        """
        evt = TimelineEvent(
            stage_id=stage_id,
            agent_name=agent_name,
            action=action,
            status=status,
            details=details or {},
            timestamp=datetime.now(timezone.utc),
        )
        self._events.append(evt)

        # Publish to EventBus asynchronously without blocking execution
        try:
            bus = get_event_bus()
            event_type = EventType.DISCOVERY_COMPLETED if "DISCOVERY" in action else EventType.EXECUTION_STARTED
            base_event = BaseEvent(
                event_type=event_type.value,
                source_module=f"pipeline.{agent_name.lower()}",
                payload={
                    "run_id": self.run_id,
                    "stage_id": stage_id,
                    "action": action,
                    "status": status,
                    "details": details or {},
                },
            )
            # Safe fire-and-forget publish
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(bus.publish(base_event))
            except RuntimeError:
                # Outside active asyncio event loop, run in background thread or pass
                pass
        except Exception as e:
            logger.debug("Could not publish timeline event to EventBus: %s", e)

        return evt

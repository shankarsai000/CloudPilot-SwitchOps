"""
Asynchronous Publish-Subscribe Event Bus.
"""

import asyncio
import inspect
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Union

from core.events.models import BaseEvent, EventType

logger = logging.getLogger("cloudpilot.events")

EventHandler = Callable[[BaseEvent], Union[None, Awaitable[None]]]


class EventBus:
    """
    Decoupled publish-subscribe event dispatcher supporting async and sync handlers.
    Allows modules M1 through M10 to react to changes without direct tight coupling.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._wildcard_subscribers: List[EventHandler] = []
        self._published_history: List[BaseEvent] = []

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register an event handler for a specific event_type or wildcard '*'."""
        if event_type == "*":
            self._wildcard_subscribers.append(handler)
        else:
            self._subscribers[event_type].append(handler)
        logger.debug("Subscribed %s to event '%s'", handler.__name__, event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a subscriber."""
        if event_type == "*" and handler in self._wildcard_subscribers:
            self._wildcard_subscribers.remove(handler)
        elif handler in self._subscribers.get(event_type, []):
            self._subscribers[event_type].remove(handler)

    async def publish(self, event: BaseEvent) -> None:
        """
        Dispatch an event to all registered subscribers.
        Executes handlers safely, logging any exceptions without interrupting other handlers.
        """
        self._published_history.append(event)
        # Cap memory history to last 500 events
        if len(self._published_history) > 500:
            self._published_history.pop(0)

        handlers = list(self._subscribers.get(event.event_type, [])) + self._wildcard_subscribers
        logger.info(
            "Publishing event [%s] from %s (subscribers: %d)",
            event.event_type,
            event.source_module,
            len(handlers),
        )

        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as exc:
                logger.error(
                    "Error in event handler %s processing %s: %s",
                    getattr(handler, "__name__", str(handler)),
                    event.event_type,
                    exc,
                )

    def publish_sync(self, event: BaseEvent) -> None:
        """Synchronous publish helper for synchronous call sites."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.publish(event))
            else:
                loop.run_until_complete(self.publish(event))
        except RuntimeError:
            asyncio.run(self.publish(event))

    def clear(self) -> None:
        """Clear all subscribers and history (useful for test teardown)."""
        self._subscribers.clear()
        self._wildcard_subscribers.clear()
        self._published_history.clear()


_event_bus = EventBus()


def get_event_bus() -> EventBus:
    """Return the platform event bus singleton."""
    return _event_bus

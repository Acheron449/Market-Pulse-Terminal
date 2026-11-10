"""In-process fan-out for Server-Sent Events (FR-14).

Each subscriber gets a small bounded queue: a browser that stops reading must not slow the
refresh loop, so the oldest pending snapshot is dropped in favour of the newest one.
"""

from __future__ import annotations

import asyncio

from app.models import MarketSnapshot

QUEUE_SIZE = 4


class EventBus:
    """Publishes each new snapshot to every connected stream."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[MarketSnapshot]] = set()

    def subscribe(self) -> asyncio.Queue[MarketSnapshot]:
        queue: asyncio.Queue[MarketSnapshot] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[MarketSnapshot]) -> None:
        self._subscribers.discard(queue)

    def publish(self, snapshot: MarketSnapshot) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - race with the consumer
                    pass
            try:
                queue.put_nowait(snapshot)
            except asyncio.QueueFull:  # pragma: no cover - bounded above
                pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

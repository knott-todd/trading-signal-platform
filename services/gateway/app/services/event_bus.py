"""
In-process event bus. Module 01 backend events are polled/pushed here,
then broadcast to all connected SSE clients.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Set

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._queues: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)

    async def publish(self, event_type: str, module: str, payload: dict) -> None:
        event = {
            "type": event_type,
            "module": module,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "payload": payload,
        }
        data = json.dumps(event)
        dead = set()
        for q in self._queues:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                dead.add(q)
        for q in dead:
            self._queues.discard(q)

    async def stream(self, q: asyncio.Queue, keepalive_seconds: int = 30) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted strings for a single client."""
        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=keepalive_seconds)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # SSE keepalive comment
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(q)


bus = EventBus()

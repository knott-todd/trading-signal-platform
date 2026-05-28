"""
Background task that polls Module 01 health every 10 seconds.
Publishes ingestion.health_change events when state changes.
"""
import asyncio
import logging
from typing import Optional

from services.gateway.app.services import ingestion_client
from services.gateway.app.services.event_bus import bus

log = logging.getLogger(__name__)

_last_status: Optional[str] = None


async def poll_loop() -> None:
    global _last_status
    while True:
        try:
            data = await ingestion_client.get("/health")
            new_status = data.get("status", "unknown")
            if new_status != _last_status:
                await bus.publish(
                    "ingestion.health_change",
                    "ingestion",
                    {
                        "subsystem": "overall",
                        "previous_state": _last_status,
                        "new_state": new_status,
                        "detail": data,
                    },
                )
                _last_status = new_status
        except Exception as exc:
            if _last_status != "unreachable":
                await bus.publish(
                    "ingestion.health_change",
                    "ingestion",
                    {
                        "subsystem": "overall",
                        "previous_state": _last_status,
                        "new_state": "unreachable",
                        "error": str(exc),
                    },
                )
                _last_status = "unreachable"
        await asyncio.sleep(10)

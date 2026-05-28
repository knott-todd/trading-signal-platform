import asyncio
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.services import ingestion_client
from app.services.event_bus import bus
from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

MODULE_REGISTRY = [
    {
        "id": "ingestion",
        "label": "Data Ingestion",
        "version": "0.2.0",
        "healthEndpoint": "/api/ingestion/health",
        "views": [
            {"id": "health", "label": "Pipeline Health", "icon": "Activity", "verificationView": True},
            {"id": "coverage", "label": "Watchlist & Coverage", "icon": "LayoutGrid", "verificationView": True},
            {"id": "barviewer", "label": "Bar Viewer", "icon": "CandlestickChart", "verificationView": True},
            {"id": "livefeed", "label": "Live Feed", "icon": "Radio", "verificationView": True},
        ],
    }
]


@router.get("/api/health")
async def aggregated_health():
    """Aggregated health across all registered modules."""
    results = []
    overall = "healthy"

    try:
        m01 = await ingestion_client.get("/health")
        results.append({"module": "ingestion", **m01})
        if m01.get("status") == "unhealthy":
            overall = "unhealthy"
        elif m01.get("status") == "degraded" and overall != "unhealthy":
            overall = "degraded"
    except Exception as exc:
        results.append({"module": "ingestion", "status": "unreachable", "error": str(exc)})
        overall = "unhealthy"

    return {"status": overall, "modules": results}


@router.get("/api/modules")
async def list_modules():
    """Registered modules with versions and health."""
    modules = []
    for m in MODULE_REGISTRY:
        try:
            health = await ingestion_client.get("/health") if m["id"] == "ingestion" else {}
            status = health.get("status", "unknown")
        except Exception:
            status = "unreachable"
        modules.append({**m, "health": status})
    return {"modules": modules}


@router.get("/api/events")
async def sse_stream(request: Request):
    """SSE stream — all real-time events from all modules."""
    q = bus.subscribe()

    async def generator():
        try:
            async for chunk in bus.stream(q, settings.sse_keepalive_seconds):
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

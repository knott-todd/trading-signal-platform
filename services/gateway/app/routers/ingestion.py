"""
Gateway routes for Module 01 (Ingestion).
Thin translation layer — no business logic.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services import ingestion_client

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@router.get("/health")
async def ingestion_health():
    """Subsystem health cards for View 1."""
    health = await ingestion_client.get("/health")
    scheduler = await ingestion_client.get("/scheduler/jobs")
    stream = await ingestion_client.get("/stream/status")

    # Compose into subsystem cards
    db_ok = health.get("db", False)
    stream_state = health.get("stream", "disconnected")

    cards = [
        {
            "subsystem": "database",
            "status": "healthy" if db_ok else "unhealthy",
            "detail": {"connected": db_ok},
        },
        {
            "subsystem": "finnhub_connection",
            "status": "healthy" if health.get("status") != "unreachable" else "unhealthy",
            "detail": {"last_check": health.get("ts")},
        },
        {
            "subsystem": "websocket_stream",
            "status": "healthy" if stream_state == "connected"
                      else "degraded" if stream_state in ("fallback", "reconnecting")
                      else "offline",
            "detail": stream,
        },
        {
            "subsystem": "scheduler",
            "status": "healthy" if scheduler.get("jobs") else "degraded",
            "detail": {"jobs": scheduler.get("jobs", [])},
        },
    ]

    return {
        "overall": health.get("status"),
        "cards": cards,
    }


# ------------------------------------------------------------------
# Watchlist
# ------------------------------------------------------------------

class TickerCreate(BaseModel):
    symbol: str
    name: Optional[str] = None
    active: bool = True
    stream_live: bool = False
    notes: Optional[str] = None


class TickerUpdate(BaseModel):
    active: Optional[bool] = None
    stream_live: Optional[bool] = None
    notes: Optional[str] = None


@router.get("/tickers")
async def list_tickers():
    tickers = await ingestion_client.get("/tickers")
    # Attach coverage summary stub — full coverage from /coverage endpoint
    return {"tickers": tickers}


@router.post("/tickers", status_code=201)
async def add_ticker(body: TickerCreate):
    return await ingestion_client.post("/tickers", body.model_dump(exclude_none=True))


@router.patch("/tickers/{symbol}")
async def update_ticker(symbol: str, body: TickerUpdate):
    return await ingestion_client.patch(f"/tickers/{symbol}", body.model_dump(exclude_none=True))


@router.delete("/tickers/{symbol}", status_code=204)
async def remove_ticker(symbol: str):
    await ingestion_client.delete(f"/tickers/{symbol}")


# ------------------------------------------------------------------
# Coverage
# ------------------------------------------------------------------

@router.get("/coverage")
async def coverage(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    """
    Coverage heatmap data.
    Returns per-ticker, per-date, per-resolution bar counts.
    """
    tickers_resp = await ingestion_client.get("/tickers")
    tickers = tickers_resp if isinstance(tickers_resp, list) else tickers_resp.get("tickers", [])
    symbols = [t["symbol"] for t in tickers]

    coverage_data = []
    for symbol in symbols:
        resolutions = await ingestion_client.get(f"/bars/{symbol}/resolutions")
        coverage_data.append({
            "symbol": symbol,
            "resolutions": resolutions,
        })

    return {
        "symbols": symbols,
        "coverage": coverage_data,
        "start": start,
        "end": end,
    }


# ------------------------------------------------------------------
# Bars
# ------------------------------------------------------------------

@router.get("/bars/{symbol}")
async def get_bars(
    symbol: str,
    resolution: str = Query(...),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    params = {"resolution": resolution}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    return await ingestion_client.get(f"/bars/{symbol}", params=params)


# ------------------------------------------------------------------
# Backfill
# ------------------------------------------------------------------

class BackfillRequest(BaseModel):
    symbol: str
    resolution: str
    start: str
    end: str


@router.post("/backfill")
async def trigger_backfill(body: BackfillRequest):
    return await ingestion_client.post("/ingest/backfill", body.model_dump())


# ------------------------------------------------------------------
# Stream status
# ------------------------------------------------------------------

@router.get("/stream/status")
async def stream_status():
    return await ingestion_client.get("/stream/status")

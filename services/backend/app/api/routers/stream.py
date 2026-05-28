from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.stream.manager import stream_manager

router = APIRouter(prefix="/stream", tags=["stream"])


class SubscribeRequest(BaseModel):
    symbols: List[str]


@router.get("/status")
async def stream_status():
    """Current WebSocket connection state and active subscriptions."""
    return {
        "state": stream_manager.state.value,
        "subscribed_symbols": stream_manager.subscribed_symbols,
        "session_started_at": stream_manager.session_started_at,
        "symbol_count": len(stream_manager.subscribed_symbols),
    }


@router.post("/subscribe")
async def subscribe(body: SubscribeRequest):
    """Add tickers to live stream without restarting the connection."""
    symbols = [s.upper() for s in body.symbols]
    try:
        await stream_manager.subscribe(symbols)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"subscribed": symbols, "state": stream_manager.state.value}


@router.post("/unsubscribe")
async def unsubscribe(body: SubscribeRequest):
    """Remove tickers from live stream."""
    symbols = [s.upper() for s in body.symbols]
    await stream_manager.unsubscribe(symbols)
    return {"unsubscribed": symbols, "state": stream_manager.state.value}

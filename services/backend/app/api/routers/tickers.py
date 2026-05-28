from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.backend.app.config import settings
from services.backend.app.db.session import get_db
from services.backend.app.db.models import Ticker

router = APIRouter(prefix="/tickers", tags=["watchlist"])


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


class TickerOut(BaseModel):
    symbol: str
    name: Optional[str]
    active: bool
    stream_live: bool
    added_at: datetime
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=List[TickerOut])
async def list_tickers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT * FROM tickers ORDER BY symbol"))
    rows = result.mappings().fetchall()
    return [dict(r) for r in rows]


@router.post("", response_model=TickerOut, status_code=201)
async def add_ticker(
    body: TickerCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    symbol = body.symbol.upper().strip()

    # Check watchlist cap
    result = await db.execute(text("SELECT COUNT(*) FROM tickers"))
    count = result.scalar()
    if count >= settings.max_watchlist_size:
        raise HTTPException(
            status_code=422,
            detail=f"Watchlist cap reached ({settings.max_watchlist_size}). Remove a ticker first.",
        )

    # Check duplicate
    existing = await db.execute(
        text("SELECT symbol FROM tickers WHERE symbol = :sym"), {"sym": symbol}
    )
    if existing.fetchone():
        raise HTTPException(status_code=409, detail=f"{symbol} already in watchlist.")

    ticker = Ticker(
        symbol=symbol,
        name=body.name,
        active=body.active,
        stream_live=body.stream_live,
        added_at=datetime.now(tz=timezone.utc),
        notes=body.notes,
    )
    db.add(ticker)
    await db.commit()
    await db.refresh(ticker)

    # Trigger automatic historical backfill in background
    from app.services.fetch_jobs import run_initial_backfill
    background_tasks.add_task(run_initial_backfill, symbol)

    return ticker


@router.patch("/{symbol}", response_model=TickerOut)
async def update_ticker(
    symbol: str,
    body: TickerUpdate,
    db: AsyncSession = Depends(get_db),
):
    symbol = symbol.upper()
    result = await db.execute(
        text("SELECT * FROM tickers WHERE symbol = :sym"), {"sym": symbol}
    )
    row = result.mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"{symbol} not found.")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return dict(row)

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    updates["sym"] = symbol
    await db.execute(
        text(f"UPDATE tickers SET {set_clauses} WHERE symbol = :sym"), updates
    )
    await db.commit()

    result = await db.execute(
        text("SELECT * FROM tickers WHERE symbol = :sym"), {"sym": symbol}
    )
    return dict(result.mappings().fetchone())


@router.delete("/{symbol}", status_code=204)
async def remove_ticker(symbol: str, db: AsyncSession = Depends(get_db)):
    """Remove from watchlist. Historical bars are NOT deleted per spec."""
    symbol = symbol.upper()
    result = await db.execute(
        text("DELETE FROM tickers WHERE symbol = :sym"), {"sym": symbol}
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"{symbol} not found.")

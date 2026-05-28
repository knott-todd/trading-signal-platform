from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.backend.app.db.session import get_db

router = APIRouter(prefix="/bars", tags=["data"])

VALID_RESOLUTIONS = {"1m", "5m", "15m", "1h", "1d"}


class BarOut(BaseModel):
    symbol: str
    ts: datetime
    resolution: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    flagged: bool
    source: str
    ingested_at: datetime

    class Config:
        from_attributes = True


@router.get("/{symbol}", response_model=List[BarOut])
async def get_bars(
    symbol: str,
    resolution: str = Query(..., description="1m | 5m | 15m | 1h | 1d"),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    symbol = symbol.upper()
    if resolution not in VALID_RESOLUTIONS:
        raise HTTPException(status_code=422, detail=f"Invalid resolution: {resolution}")

    query = """
        SELECT * FROM bars
        WHERE symbol = :symbol AND resolution = :resolution
    """
    params = {"symbol": symbol, "resolution": resolution}

    if start:
        query += " AND ts >= :start"
        params["start"] = start
    if end:
        query += " AND ts <= :end"
        params["end"] = end

    query += " ORDER BY ts ASC"

    result = await db.execute(text(query), params)
    rows = result.mappings().fetchall()
    return [dict(r) for r in rows]


@router.get("/{symbol}/latest", response_model=Optional[BarOut])
async def get_latest_bar(
    symbol: str,
    resolution: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    symbol = symbol.upper()
    if resolution not in VALID_RESOLUTIONS:
        raise HTTPException(status_code=422, detail=f"Invalid resolution: {resolution}")

    result = await db.execute(
        text("""
            SELECT * FROM bars
            WHERE symbol = :symbol AND resolution = :resolution
            ORDER BY ts DESC LIMIT 1
        """),
        {"symbol": symbol, "resolution": resolution},
    )
    row = result.mappings().fetchone()
    if not row:
        return None
    return dict(row)


@router.get("/{symbol}/resolutions")
async def get_available_resolutions(
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    """List resolutions available for a symbol within retention window."""
    symbol = symbol.upper()
    result = await db.execute(
        text("""
            SELECT DISTINCT resolution, MIN(ts) as oldest, MAX(ts) as newest, COUNT(*) as bar_count
            FROM bars
            WHERE symbol = :symbol
            GROUP BY resolution
            ORDER BY resolution
        """),
        {"symbol": symbol},
    )
    rows = result.mappings().fetchall()
    return [dict(r) for r in rows]

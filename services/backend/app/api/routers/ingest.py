from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(prefix="/ingest", tags=["operations"])

VALID_RESOLUTIONS = {"1m", "5m", "15m", "1h", "1d"}


class BackfillRequest(BaseModel):
    symbol: str
    resolution: str
    start: date
    end: date


class BackfillResponse(BaseModel):
    symbol: str
    resolution: str
    start: date
    end: date
    rows_written: int


@router.post("/backfill", response_model=BackfillResponse)
async def manual_backfill(body: BackfillRequest):
    from app.services.fetch_jobs import run_backfill

    symbol = body.symbol.upper()
    if body.resolution not in VALID_RESOLUTIONS:
        raise HTTPException(status_code=422, detail=f"Invalid resolution: {body.resolution}")
    if body.end < body.start:
        raise HTTPException(status_code=422, detail="end must be >= start")

    rows_written = await run_backfill(symbol, body.resolution, body.start, body.end)
    return BackfillResponse(
        symbol=symbol,
        resolution=body.resolution,
        start=body.start,
        end=body.end,
        rows_written=rows_written,
    )


@router.get("/status")
async def ingest_status(db: AsyncSession = Depends(get_db)):
    """Last fetch job result per ticker."""
    result = await db.execute(text("""
        SELECT DISTINCT ON (symbol)
            symbol, mode, job_type, source, status, rows_written, error_msg, started_at, ended_at
        FROM ingestion_log
        WHERE symbol IS NOT NULL
        ORDER BY symbol, started_at DESC
    """))
    rows = result.mappings().fetchall()
    return [dict(r) for r in rows]


@router.get("/log")
async def ingest_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    symbol: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Paginated ingestion audit log."""
    offset = (page - 1) * page_size
    params = {"limit": page_size, "offset": offset}
    where = ""
    if symbol:
        where = "WHERE symbol = :symbol"
        params["symbol"] = symbol.upper()

    result = await db.execute(
        text(f"""
            SELECT * FROM ingestion_log
            {where}
            ORDER BY started_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM ingestion_log {where}"),
        {"symbol": symbol.upper()} if symbol else {},
    )
    total = count_result.scalar()

    rows = result.mappings().fetchall()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [dict(r) for r in rows],
    }

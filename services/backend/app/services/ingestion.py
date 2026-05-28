"""
Ingestion service.
Handles converting validated bar dicts into DB rows, upsert logic, and log writing.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.backend.app.db.models import Bar, IngestionLog
from services.backend.app.services.validation import validate_batch, validate_bar

log = logging.getLogger(__name__)


async def ingest_bars(
    db: AsyncSession,
    bars: List[Dict],
    symbol: str,
    resolution: str,
    source: str,
    mode: str,
    job_type: str,
    previous_close: Optional[float] = None,
) -> int:
    """
    Validate and write a batch of bars.
    Returns number of rows successfully written.
    Writes an ingestion_log entry on completion.
    """
    started_at = datetime.now(tz=timezone.utc)
    valid_bars, flagged_list, rejected = validate_batch(bars, symbol, resolution, previous_close)

    rows_written = 0
    error_msg = None

    try:
        for bar, flagged in zip(valid_bars, flagged_list):
            await _upsert_bar(db, symbol, resolution, bar, flagged, source)
            rows_written += 1

        status = "ok" if rejected == 0 else "partial"
        if rows_written == 0 and len(bars) > 0:
            status = "failed"
            error_msg = f"All {len(bars)} bars rejected by validation."

    except Exception as exc:
        status = "failed"
        error_msg = str(exc)
        log.error("Ingestion error for %s %s: %s", symbol, resolution, exc)

    await _write_log(
        db=db,
        symbol=symbol,
        mode=mode,
        job_type=job_type,
        source=source,
        status=status,
        rows_written=rows_written,
        error_msg=error_msg,
        started_at=started_at,
    )

    return rows_written


async def ingest_single_bar(
    db: AsyncSession,
    symbol: str,
    resolution: str,
    bar: Dict,
    source: str,
    previous_close: Optional[float] = None,
) -> bool:
    """
    Validate and write a single bar (stream mode hot path).
    Returns True if written, False if rejected.
    """
    result, flagged = validate_bar(bar, symbol, resolution, previous_close)
    if result is None:
        return False

    result["flagged"] = flagged
    try:
        await _upsert_bar(db, symbol, resolution, result, flagged, source)
        return True
    except Exception as exc:
        log.error("Failed to write bar %s %s: %s", symbol, resolution, exc)
        return False


async def _upsert_bar(
    db: AsyncSession,
    symbol: str,
    resolution: str,
    bar: Dict,
    flagged: bool,
    source: str,
) -> None:
    """
    INSERT ... ON CONFLICT DO NOTHING.
    Spec: skip on duplicate, no error.
    """
    stmt = text("""
        INSERT INTO bars (symbol, ts, resolution, open, high, low, close, volume, flagged, source, ingested_at)
        VALUES (:symbol, :ts, :resolution, :open, :high, :low, :close, :volume, :flagged, :source, NOW())
        ON CONFLICT (symbol, ts, resolution) DO NOTHING
    """)
    await db.execute(stmt, {
        "symbol":     symbol,
        "ts":         bar["ts"],
        "resolution": resolution,
        "open":       float(bar["open"]),
        "high":       float(bar["high"]),
        "low":        float(bar["low"]),
        "close":      float(bar["close"]),
        "volume":     int(bar["volume"]),
        "flagged":    bool(flagged),
        "source":     source,
    })


async def _write_log(
    db: AsyncSession,
    symbol: Optional[str],
    mode: str,
    job_type: str,
    source: Optional[str],
    status: str,
    rows_written: int,
    error_msg: Optional[str],
    started_at: datetime,
) -> None:
    entry = IngestionLog(
        symbol=symbol,
        mode=mode,
        job_type=job_type,
        source=source,
        status=status,
        rows_written=rows_written,
        error_msg=error_msg,
        started_at=started_at,
        ended_at=datetime.now(tz=timezone.utc),
    )
    db.add(entry)
    await db.commit()


async def get_latest_close(db: AsyncSession, symbol: str, resolution: str) -> Optional[float]:
    """Retrieve the most recent close for spike detection context."""
    result = await db.execute(
        text("""
            SELECT close FROM bars
            WHERE symbol = :symbol AND resolution = :resolution
            ORDER BY ts DESC LIMIT 1
        """),
        {"symbol": symbol, "resolution": resolution},
    )
    row = result.fetchone()
    return float(row[0]) if row else None
